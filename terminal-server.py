#!/usr/bin/env python3
"""
WebSocket Terminal Server v2
Features:
- Direct xterm.js integration via WebSocket
- Session output buffer for reconnection (1000 lines)
- Multi-client support per session
- Persistent dtach sessions
"""

import asyncio
import fcntl
import json
import logging
import os
import pty
import re
import signal
import struct
import subprocess
import sys
import termios
import weakref
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from time import time
from typing import Dict, Set

from aiohttp import web, WSMsgType

# Configuration
PORT = 7681
SOCKET_DIR = Path("/tmp/dtach-sessions")
LOG_DIR = Path("/tmp/terminal-logs")
PROJECT_BASE = Path("/home/cactus/claude")
BUFFER_MAX_LINES = 1000  # Lines to keep for reconnection
BUFFER_MAX_BYTES = 512 * 1024  # Max 512KB per session buffer

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============ Session Buffer ============
@dataclass
class SessionBuffer:
    """Circular buffer for session output, supports reconnection replay."""
    data: deque = field(default_factory=lambda: deque(maxlen=BUFFER_MAX_LINES))
    total_bytes: int = 0

    def append(self, chunk: bytes):
        """Add output chunk to buffer."""
        self.data.append(chunk)
        self.total_bytes += len(chunk)
        # Trim if exceeds max bytes
        while self.total_bytes > BUFFER_MAX_BYTES and len(self.data) > 1:
            removed = self.data.popleft()
            self.total_bytes -= len(removed)

    def get_all(self) -> bytes:
        """Get all buffered output for replay."""
        return b''.join(self.data)

    def clear(self):
        """Clear the buffer."""
        self.data.clear()
        self.total_bytes = 0


class EventDetector:
    """Analyzes PTY output stream for notable events."""

    DEBOUNCE_SECS = 5
    MAX_LINES = 10

    PERMISSION_PATTERNS = [
        re.compile(r'\[Y/n\]\s*$', re.MULTILINE),
        re.compile(r'\[y/N\]\s*$', re.MULTILINE),
        re.compile(r'\(y/n\)\s*$', re.MULTILINE),
        re.compile(r'Continue\?\s*$', re.MULTILINE),
        re.compile(r'Proceed\?\s*$', re.MULTILINE),
        re.compile(r'Are you sure\?\s*$', re.MULTILINE),
        re.compile(r'Password:\s*$', re.IGNORECASE | re.MULTILINE),
        re.compile(r'\[sudo\] password', re.IGNORECASE),
        re.compile(r'Do you want to proceed\?', re.IGNORECASE),
        re.compile(r'Press Enter to run'),
    ]

    ERROR_PATTERNS = [
        re.compile(r'(?:^|\n)\s*Error:', re.IGNORECASE),
        re.compile(r'(?:^|\n)\s*FATAL:', re.IGNORECASE),
        re.compile(r'Traceback \(most recent call last\)'),
        re.compile(r'panic:'),
        re.compile(r'Unhandled exception'),
    ]

    TASK_COMPLETE_PATTERNS = [
        re.compile(r'Task completed'),
        re.compile(r'✓.*completed', re.IGNORECASE),
    ]

    def __init__(self):
        self.line_buffers = {}    # session_name -> list of lines
        self.last_events = {}     # session_name -> {event_type: timestamp}

    def strip_ansi(self, text):
        text = re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', text)
        text = re.sub(r'\x1B\][^\x07]*\x07', '', text)
        return text

    def feed(self, session_name, raw_data):
        text = raw_data.decode('utf-8', errors='ignore')
        clean = self.strip_ansi(text)

        buf = self.line_buffers.get(session_name, [])
        buf.extend(clean.split('\n'))
        self.line_buffers[session_name] = buf[-self.MAX_LINES:]

        context = '\n'.join(self.line_buffers[session_name])
        events = []
        now = time()

        for event_type, patterns, severity in [
            ('permission_request', self.PERMISSION_PATTERNS, 'high'),
            ('error', self.ERROR_PATTERNS, 'high'),
            ('task_complete', self.TASK_COMPLETE_PATTERNS, 'medium'),
        ]:
            last = self.last_events.get(session_name, {}).get(event_type, 0)
            if now - last < self.DEBOUNCE_SECS:
                continue

            for pattern in patterns:
                if pattern.search(context):
                    if session_name not in self.last_events:
                        self.last_events[session_name] = {}
                    self.last_events[session_name][event_type] = now
                    events.append({
                        'type': 'event',
                        'event': event_type,
                        'session': session_name,
                        'timestamp': now,
                        'context': context[-300:],
                        'severity': severity
                    })
                    break

        return events


@dataclass
class SharedSession:
    """A terminal session that can be shared by multiple WebSocket clients."""
    session_name: str
    project: str
    command: str
    master_fd: int = None
    pid: int = None
    running: bool = False
    buffer: SessionBuffer = field(default_factory=SessionBuffer)
    clients: Set = field(default_factory=set)  # Set of WebSocketResponse
    read_task: asyncio.Task = None
    state: str = "normal"        # normal, waiting_input, idle, error
    created_at: float = field(default_factory=time)
    last_output: float = 0
    last_cols: int = 200
    last_rows: int = 50

    def client_count(self) -> int:
        return len(self.clients)


# Global session registry: session_name -> SharedSession
active_sessions: Dict[str, SharedSession] = {}

event_detector = EventDetector()


def ensure_directories():
    """Create required directories with proper permissions."""
    SOCKET_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(SOCKET_DIR, 0o777)
        os.chmod(LOG_DIR, 0o777)
    except PermissionError:
        pass


def sanitize_session_name(name: str) -> str:
    """Sanitize session name for use in file paths."""
    return ''.join(c if c.isalnum() or c == '_' else '_' for c in name)


def get_session_socket(session_name: str) -> Path:
    """Get the dtach socket path for a session."""
    return SOCKET_DIR / f"{session_name}.sock"


def get_session_log(session_name: str) -> Path:
    """Get the log file path for a session."""
    return LOG_DIR / f"{session_name}.log"


def session_exists(session_name: str) -> bool:
    """Check if a dtach session already exists."""
    socket_path = get_session_socket(session_name)
    return socket_path.exists() and socket_path.is_socket()


def create_dtach_session(session_name: str, project: str, command: str):
    """Create a new dtach session in the background."""
    socket_path = get_session_socket(session_name)
    log_path = get_session_log(session_name)

    # Determine project path
    project_path = PROJECT_BASE / project
    if not project_path.is_dir():
        project_path = Path.home()

    # Build the command to run inside dtach
    if command == "bash":
        inner_cmd = f"cd '{project_path}' && exec script -f -q '{log_path}' -c 'bash -l'"
    elif command == "claude":
        inner_cmd = f"cd '{project_path}' && exec script -f -q '{log_path}' -c 'claude'"
    else:
        # Use bash -l to source profile (for env vars like ANTHROPIC_API_KEY)
        inner_cmd = f"cd '{project_path}' && exec script -f -q '{log_path}' -c 'bash -l -c \"{command}\"'"

    # Create empty log file
    log_path.touch()
    try:
        os.chmod(log_path, 0o666)
    except PermissionError:
        pass

    # Create dtach session in background (-n = no attach)
    dtach_cmd = ["dtach", "-n", str(socket_path), "-z", "bash", "-c", inner_cmd]

    try:
        subprocess.run(dtach_cmd, check=True, capture_output=True)
        logger.info(f"Created dtach session: {session_name}")
        # Give dtach time to create the socket
        import time
        time.sleep(0.3)
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to create dtach session: {e}")
        raise


# ============ Shared Session Management ============

def get_or_create_shared_session(session_name: str, project: str, command: str) -> SharedSession:
    """Get existing session or create a new one."""
    if session_name in active_sessions:
        session = active_sessions[session_name]
        # Check if the dtach socket still exists - if not, the session is dead
        if session_exists(session_name):
            logger.info(f"Reusing existing session: {session_name} (clients: {session.client_count()})")
            return session
        else:
            logger.warning(f"Session {session_name} found in memory but dtach socket is gone, recreating")
            # Clean up the dead session
            if session.master_fd is not None:
                try:
                    os.close(session.master_fd)
                except OSError:
                    pass
            del active_sessions[session_name]

    # Create new shared session
    session = SharedSession(
        session_name=session_name,
        project=project,
        command=command
    )
    active_sessions[session_name] = session

    # Start PTY connection
    start_session_pty(session)

    return session


def start_session_pty(session: SharedSession):
    """Start the PTY connection for a shared session."""
    socket_path = get_session_socket(session.session_name)

    # Create dtach session if it doesn't exist
    if not session_exists(session.session_name):
        create_dtach_session(session.session_name, session.project, session.command)

    # Fork a PTY and attach to dtach
    pid, master_fd = pty.fork()

    if pid == 0:
        # Child process: exec dtach -a (attach to existing session)
        os.execlp("dtach", "dtach", "-a", str(socket_path), "-z")
    else:
        # Parent process
        session.pid = pid
        session.master_fd = master_fd
        session.running = True

        # Set initial PTY size to something large so apps render correctly
        # before the client sends its actual dimensions
        try:
            winsize = struct.pack('HHHH', 50, 200, 0, 0)
            fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)
        except Exception:
            pass

        # Set non-blocking mode
        flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
        fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

        logger.info(f"Started PTY for session: {session.session_name}")


def session_resize(session: SharedSession, rows: int, cols: int):
    """Resize the PTY for a shared session."""
    if session.master_fd is not None:
        try:
            winsize = struct.pack('HHHH', rows, cols, 0, 0)
            fcntl.ioctl(session.master_fd, termios.TIOCSWINSZ, winsize)
            session.last_cols = cols
            session.last_rows = rows
        except Exception as e:
            logger.warning(f"Failed to resize PTY: {e}")


def session_write(session: SharedSession, data: bytes):
    """Write data to the PTY."""
    if session.master_fd is not None:
        try:
            os.write(session.master_fd, data)
        except Exception as e:
            logger.warning(f"Failed to write to PTY: {e}")


def session_read(session: SharedSession) -> bytes | None:
    """Read data from the PTY (non-blocking)."""
    if session.master_fd is None:
        return None
    try:
        return os.read(session.master_fd, 4096)
    except BlockingIOError:
        return None
    except OSError:
        return None


def stop_session(session: SharedSession):
    """Stop the PTY connection and clean up."""
    session.running = False

    if session.read_task:
        session.read_task.cancel()
        session.read_task = None

    if session.master_fd is not None:
        try:
            os.close(session.master_fd)
        except OSError:
            pass
        session.master_fd = None

    if session.pid is not None:
        try:
            os.kill(session.pid, signal.SIGTERM)
            os.waitpid(session.pid, os.WNOHANG)
        except (OSError, ChildProcessError):
            pass
        session.pid = None

    # Remove from active sessions
    if session.session_name in active_sessions:
        del active_sessions[session.session_name]

    logger.info(f"Stopped session: {session.session_name}")


async def read_and_broadcast(session: SharedSession):
    """Background task to read PTY output and broadcast to all connected clients."""
    loop = asyncio.get_event_loop()

    while session.running:
        try:
            # Use run_in_executor for non-blocking read
            data = await loop.run_in_executor(None, lambda: session_read(session))
            if data:
                # Add to buffer for reconnection
                session.buffer.append(data)

                # Update last_output timestamp
                session.last_output = time()

                # Detect events in the stream
                events = event_detector.feed(session.session_name, data)

                # Update session state based on events
                for evt in events:
                    if evt['event'] == 'permission_request':
                        session.state = 'waiting_input'
                    elif evt['event'] == 'error':
                        session.state = 'error'
                    elif evt['event'] == 'task_complete':
                        session.state = 'normal'

                # Broadcast to all connected clients
                dead_clients = []
                for ws in session.clients:
                    try:
                        if not ws.closed:
                            await asyncio.wait_for(ws.send_bytes(data), timeout=1.0)
                        else:
                            dead_clients.append(ws)
                    except (asyncio.TimeoutError, Exception):
                        dead_clients.append(ws)

                # Send events as JSON text messages
                for evt in events:
                    for ws in session.clients:
                        try:
                            if not ws.closed:
                                await asyncio.wait_for(ws.send_str(json.dumps(evt)), timeout=1.0)
                        except Exception:
                            pass

                # Remove dead clients
                for ws in dead_clients:
                    session.clients.discard(ws)

                # If no clients left, keep running (session stays alive for reconnection)
            else:
                await asyncio.sleep(0.01)  # Small delay to prevent busy-waiting
        except asyncio.CancelledError:
            break
        except Exception as e:
            if session.running:
                logger.warning(f"Error reading PTY for {session.session_name}: {e}")
            break

    logger.info(f"Read task ended for session: {session.session_name}")


async def websocket_handler(request: web.Request) -> web.WebSocketResponse:
    """Handle WebSocket connections for terminal sessions."""

    # Parse query parameters
    session_name = request.query.get('session', '')
    project = request.query.get('project', '')
    command = request.query.get('command', 'bash')

    if not session_name or not project:
        return web.Response(status=400, text="Missing session or project parameter")

    # Sanitize session name
    session_name = sanitize_session_name(session_name)

    logger.info(f"WebSocket connection: session={session_name}, project={project}, command={command}")

    # Accept WebSocket connection
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    # Get or create shared session
    session = get_or_create_shared_session(session_name, project, command)

    try:
        # Add this client to the session
        session.clients.add(ws)
        logger.info(f"Client joined session {session_name} (total clients: {session.client_count()})")

        # Send buffered output for reconnection (replay history)
        buffered_data = session.buffer.get_all()
        if buffered_data:
            logger.info(f"Sending {len(buffered_data)} bytes of buffered output to reconnecting client")
            await ws.send_bytes(buffered_data)

        # Start read task if not already running
        if session.read_task is None or session.read_task.done():
            session.read_task = asyncio.create_task(read_and_broadcast(session))

        # Handle incoming WebSocket messages
        async for msg in ws:
            if msg.type == WSMsgType.BINARY:
                # Binary data = keyboard input
                session_write(session, msg.data)

            elif msg.type == WSMsgType.TEXT:
                # Text data = JSON control messages
                try:
                    data = json.loads(msg.data)
                    if data.get('type') == 'resize':
                        cols = data.get('cols', 80)
                        rows = data.get('rows', 24)
                        session_resize(session, rows, cols)
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON message: {msg.data}")

            elif msg.type == WSMsgType.ERROR:
                logger.error(f"WebSocket error: {ws.exception()}")
                break

    except Exception as e:
        logger.error(f"Session error: {e}")

    finally:
        # Remove this client from the session
        session.clients.discard(ws)
        logger.info(f"Client left session {session_name} (remaining clients: {session.client_count()})")

        # Don't stop the session - keep it alive for potential reconnection
        # Session will be stopped manually or when server shuts down

    return ws


async def health_handler(request: web.Request) -> web.Response:
    """Health check endpoint."""
    return web.json_response({"status": "ok", "service": "terminal-server"})


async def sessions_handler(request: web.Request) -> web.Response:
    """List active sessions with details."""
    sessions = []

    # List dtach sockets
    dtach_sessions = set()
    if SOCKET_DIR.exists():
        for socket_file in SOCKET_DIR.glob("*.sock"):
            if socket_file.is_socket():
                dtach_sessions.add(socket_file.stem)

    # Combine with active server sessions
    for session_name in dtach_sessions | set(active_sessions.keys()):
        session_info = {
            "name": session_name,
            "dtach_exists": session_name in dtach_sessions,
            "server_active": session_name in active_sessions,
        }
        if session_name in active_sessions:
            session = active_sessions[session_name]
            session_info["clients"] = session.client_count()
            session_info["buffer_size"] = session.buffer.total_bytes
            session_info["project"] = session.project
            session_info["command"] = session.command
            session_info["state"] = session.state
            session_info["created_at"] = session.created_at
            session_info["last_output"] = session.last_output
        sessions.append(session_info)

    return web.json_response({"sessions": sessions})


async def session_stop_handler(request: web.Request) -> web.Response:
    """Stop a specific session."""
    session_name = request.match_info.get('name', '')
    if not session_name:
        return web.json_response({"error": "Missing session name"}, status=400)

    session_name = sanitize_session_name(session_name)

    if session_name in active_sessions:
        stop_session(active_sessions[session_name])
        return web.json_response({"status": "stopped", "session": session_name})
    else:
        return web.json_response({"error": "Session not found"}, status=404)


async def send_input_handler(request: web.Request) -> web.Response:
    """Send input to a specific session via HTTP."""
    name = sanitize_session_name(request.match_info['name'])
    if name not in active_sessions:
        return web.json_response({"error": "Session not found"}, status=404)
    body = await request.json()
    text = body.get('input', '')
    if text:
        session_write(active_sessions[name], text.encode())
    return web.json_response({"status": "sent"})


async def delete_session_handler(request: web.Request) -> web.Response:
    """Delete (stop) a specific session."""
    name = sanitize_session_name(request.match_info['name'])
    if name not in active_sessions:
        return web.json_response({"error": "Session not found"}, status=404)
    stop_session(active_sessions[name])
    return web.json_response({"status": "deleted"})


def create_app() -> web.Application:
    """Create the aiohttp application."""
    app = web.Application()

    # Enable CORS for all routes
    async def cors_middleware(app, handler):
        async def middleware_handler(request):
            if request.method == 'OPTIONS':
                response = web.Response()
            else:
                response = await handler(request)

            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Access-Control-Allow-Methods'] = 'GET, POST, DELETE, OPTIONS'
            response.headers['Access-Control-Allow-Headers'] = '*'
            return response
        return middleware_handler

    app.middlewares.append(cors_middleware)

    # Routes
    app.router.add_get('/ws', websocket_handler)
    app.router.add_get('/health', health_handler)
    app.router.add_get('/sessions', sessions_handler)
    app.router.add_post('/sessions/{name}/stop', session_stop_handler)
    app.router.add_post('/sessions/{name}/input', send_input_handler)
    app.router.add_delete('/sessions/{name}', delete_session_handler)

    return app


def main():
    """Main entry point."""
    ensure_directories()

    app = create_app()

    logger.info(f"Starting Terminal Server on port {PORT}")
    web.run_app(app, host='0.0.0.0', port=PORT, print=None)


if __name__ == '__main__':
    main()
