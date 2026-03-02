"""Centralized configuration for Homepage Cactus"""
import os

# Data persistence
DATA_DIR = os.environ.get('DATA_DIR', '/data')
PREFERENCES_FILE = os.path.join(DATA_DIR, 'preferences.json')
APPS_FILE = os.path.join(DATA_DIR, 'apps.json')
ERP_REQUESTS_FILE = os.path.join(DATA_DIR, 'erp_requests.json')

# Projects
PROJECTS_DIR = os.environ.get('PROJECTS_DIR', '/home/cactus/claude')
CLAUDE_CONFIG_DIR = os.environ.get('CLAUDE_CONFIG_DIR', '/home/cactus/.claude/projects')

# Terminal
TERMINAL_LOG_DIR = os.environ.get('TERMINAL_LOG_DIR', '/tmp/terminal-logs')
SOCKET_DIR = os.environ.get('SOCKET_DIR', '/tmp/dtach-sessions')

# Telegram
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}" if TELEGRAM_BOT_TOKEN else ''

def ensure_data_dir():
    """Create data directory if it doesn't exist"""
    os.makedirs(DATA_DIR, exist_ok=True)
