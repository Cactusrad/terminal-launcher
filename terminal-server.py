#!/usr/bin/env python3
"""
WebSocket Terminal Server
Replaces ttyd + iframe with direct xterm.js integration.
Connects to dtach sessions via PTY.
"""

import asyncio
import fcntl
import json
import logging
import os
import pty
import signal
import struct
import subprocess
import sys
import termios
from pathlib import Path

from aiohttp import web, WSMsgType

# Configuration
PORT = 7681
SOCKET_DIR = Path("/tmp/dtach-sessions")
LOG_DIR = Path("/tmp/terminal-logs")
PROJECT_BASE = Path("/home/cactus/claude")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


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
        inner_cmd = f"cd '{project_path}' && exec script -f -q '{log_path}' -c '{command}'"

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


class TerminalSession:
    """Manages a PTY connection to a dtach session."""

    def __init__(self, session_name: str, project: str, command: str):
        self.session_name = session_name
        self.project = project
        self.command = command
        self.master_fd = None
        self.pid = None
        self.running = False

    def start(self):
        """Start the PTY connection to dtach."""
        socket_path = get_session_socket(self.session_name)

        # Create dtach session if it doesn't exist
        if not session_exists(self.session_name):
            create_dtach_session(self.session_name, self.project, self.command)

        # Fork a PTY and attach to dtach
        pid, master_fd = pty.fork()

        if pid == 0:
            # Child process: exec dtach -a (attach to existing session)
            os.execlp("dtach", "dtach", "-a", str(socket_path), "-z")
        else:
            # Parent process
            self.pid = pid
            self.master_fd = master_fd
            self.running = True

            # Set non-blocking mode
            flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
            fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

            logger.info(f"Attached to session: {self.session_name}")

    def resize(self, rows: int, cols: int):
        """Resize the PTY."""
        if self.master_fd is not None:
            try:
                winsize = struct.pack('HHHH', rows, cols, 0, 0)
                fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, winsize)
            except Exception as e:
                logger.warning(f"Failed to resize PTY: {e}")

    def write(self, data: bytes):
        """Write data to the PTY."""
        if self.master_fd is not None:
            try:
                os.write(self.master_fd, data)
            except Exception as e:
                logger.warning(f"Failed to write to PTY: {e}")

    def read(self) -> bytes | None:
        """Read data from the PTY (non-blocking)."""
        if self.master_fd is None:
            return None
        try:
            return os.read(self.master_fd, 4096)
        except BlockingIOError:
            return None
        except OSError:
            return None

    def stop(self):
        """Stop the PTY connection."""
        self.running = False
        if self.master_fd is not None:
            try:
                os.close(self.master_fd)
            except OSError:
                pass
            self.master_fd = None

        if self.pid is not None:
            try:
                os.kill(self.pid, signal.SIGTERM)
                os.waitpid(self.pid, os.WNOHANG)
            except (OSError, ChildProcessError):
                pass
            self.pid = None

        logger.info(f"Disconnected from session: {self.session_name}")


async def read_pty_output(session: TerminalSession, ws: web.WebSocketResponse):
    """Background task to read PTY output and send to WebSocket."""
    loop = asyncio.get_event_loop()

    while session.running and not ws.closed:
        try:
            # Use run_in_executor for non-blocking read
            data = await loop.run_in_executor(None, session.read)
            if data:
                await ws.send_bytes(data)
            else:
                await asyncio.sleep(0.01)  # Small delay to prevent busy-waiting
        except Exception as e:
            if session.running:
                logger.warning(f"Error reading PTY: {e}")
            break


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

    # Start terminal session
    session = TerminalSession(session_name, project, command)

    try:
        session.start()

        # Start background task to read PTY output
        read_task = asyncio.create_task(read_pty_output(session, ws))

        # Handle incoming WebSocket messages
        async for msg in ws:
            if msg.type == WSMsgType.BINARY:
                # Binary data = keyboard input
                session.write(msg.data)

            elif msg.type == WSMsgType.TEXT:
                # Text data = JSON control messages
                try:
                    data = json.loads(msg.data)
                    if data.get('type') == 'resize':
                        cols = data.get('cols', 80)
                        rows = data.get('rows', 24)
                        session.resize(rows, cols)
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON message: {msg.data}")

            elif msg.type == WSMsgType.ERROR:
                logger.error(f"WebSocket error: {ws.exception()}")
                break

        # Cancel the read task
        read_task.cancel()
        try:
            await read_task
        except asyncio.CancelledError:
            pass

    except Exception as e:
        logger.error(f"Session error: {e}")

    finally:
        session.stop()

    return ws


async def health_handler(request: web.Request) -> web.Response:
    """Health check endpoint."""
    return web.json_response({"status": "ok", "service": "terminal-server"})


async def sessions_handler(request: web.Request) -> web.Response:
    """List active dtach sessions."""
    sessions = []
    if SOCKET_DIR.exists():
        for socket_file in SOCKET_DIR.glob("*.sock"):
            if socket_file.is_socket():
                sessions.append(socket_file.stem)
    return web.json_response({"sessions": sessions})


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
            response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
            response.headers['Access-Control-Allow-Headers'] = '*'
            return response
        return middleware_handler

    app.middlewares.append(cors_middleware)

    # Routes
    app.router.add_get('/ws', websocket_handler)
    app.router.add_get('/health', health_handler)
    app.router.add_get('/sessions', sessions_handler)

    return app


def main():
    """Main entry point."""
    ensure_directories()

    app = create_app()

    logger.info(f"Starting Terminal Server on port {PORT}")
    web.run_app(app, host='0.0.0.0', port=PORT, print=None)


if __name__ == '__main__':
    main()
