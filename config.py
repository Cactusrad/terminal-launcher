"""
Configuration module for Terminal Launcher
Loads settings from environment variables or .env file
"""

import os
from pathlib import Path

# Try to load .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed, use system env vars

# Server Configuration
HOST_IP = os.environ.get('HOST_IP')
if not HOST_IP:
    raise RuntimeError("HOST_IP must be set in environment or .env file")
DEFAULT_PORT = int(os.environ.get('DEFAULT_PORT', 80))

# Bug Reporting (optional)
BUGS_API_URL = os.environ.get('BUGS_API_URL', '')
BUGS_API_KEY = os.environ.get('BUGS_API_KEY', '')

# Telegram Notifications (optional)
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}" if TELEGRAM_BOT_TOKEN else ''

# Paths
PROJECTS_DIR = Path(os.environ.get('PROJECTS_DIR', '/home/cactus/claude'))
CLAUDE_CONFIG_DIR = Path(os.environ.get('CLAUDE_CONFIG_DIR', '/home/cactus/.claude/projects'))
DATA_DIR = Path(os.environ.get('DATA_DIR', '/data'))

# Terminal Server
TERMINAL_WS_PORT = int(os.environ.get('TERMINAL_WS_PORT', 7681))
TERMINAL_SERVER_HOST = os.environ.get('TERMINAL_SERVER_HOST', HOST_IP)
SOCKET_DIR = Path(os.environ.get('SOCKET_DIR', '/tmp/dtach-sessions'))
LOG_DIR = Path(os.environ.get('LOG_DIR', '/tmp/terminal-logs'))

# Data files
PREFERENCES_FILE = DATA_DIR / 'preferences.json'
APPS_FILE = DATA_DIR / 'apps.json'
ERP_REQUESTS_FILE = DATA_DIR / 'erp_requests.json'

# Auth / Multi-user
SECRET_KEY = os.environ.get('SECRET_KEY', '')
USERS_FILE = DATA_DIR / 'users.json'
USERS_DATA_DIR = DATA_DIR / 'users'

# GitHub
GITHUB_USER = os.environ.get('GITHUB_USER', 'Cactusrad')

# Legacy aliases
TERMINAL_LOG_DIR = str(LOG_DIR)

def ensure_data_dir():
    """Create data directory if it doesn't exist"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

def get_base_url(port: int, path: str = '') -> str:
    """Generate a base URL for a service"""
    return f"http://{HOST_IP}:{port}{path}"

def get_base_url_https(port: int, path: str = '') -> str:
    """Generate a base URL with HTTPS for a service"""
    return f"https://{HOST_IP}:{port}{path}"
