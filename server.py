#!/usr/bin/env python3
"""Terminal Launcher - Flask Server"""

from flask import Flask, jsonify, request, send_from_directory, make_response, session
from flask_cors import CORS
import json
import os
import re
import glob
import time
import secrets
import shutil
from datetime import datetime, timedelta
from functools import wraps
import bcrypt
import subprocess
import ipaddress

try:
    from config import (
        DATA_DIR, PREFERENCES_FILE, APPS_FILE, ERP_REQUESTS_FILE,
        PROJECTS_DIR, CLAUDE_CONFIG_DIR, LOG_DIR, SOCKET_DIR,
        TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_API_URL,
        HOST_IP, BUGS_API_URL, BUGS_API_KEY,
        TERMINAL_WS_PORT, TERMINAL_SERVER_HOST,
        SECRET_KEY, USERS_FILE, USERS_DATA_DIR,
        GITHUB_USER,
        ensure_data_dir, get_base_url,
    )
    TERMINAL_LOG_DIR = str(LOG_DIR)
except ImportError:
    from pathlib import Path
    DATA_DIR = Path('/data')
    PREFERENCES_FILE = DATA_DIR / 'preferences.json'
    APPS_FILE = DATA_DIR / 'apps.json'
    ERP_REQUESTS_FILE = DATA_DIR / 'erp_requests.json'
    PROJECTS_DIR = Path('/home/cactus/claude')
    CLAUDE_CONFIG_DIR = Path('/home/cactus/.claude/projects')
    TERMINAL_LOG_DIR = '/tmp/terminal-logs'
    SOCKET_DIR = Path('/tmp/dtach-sessions')
    HOST_IP = os.environ.get('HOST_IP')
    if not HOST_IP:
        raise RuntimeError("HOST_IP must be set in environment or .env file")
    TERMINAL_WS_PORT = int(os.environ.get('TERMINAL_WS_PORT', 7681))
    TERMINAL_SERVER_HOST = os.environ.get('TERMINAL_SERVER_HOST', HOST_IP)
    TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
    TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')
    TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}" if TELEGRAM_BOT_TOKEN else ''
    BUGS_API_URL = os.environ.get('BUGS_API_URL', '')
    BUGS_API_KEY = os.environ.get('BUGS_API_KEY', '')
    SECRET_KEY = os.environ.get('SECRET_KEY', '')
    USERS_FILE = DATA_DIR / 'users.json'
    USERS_DATA_DIR = DATA_DIR / 'users'
    GITHUB_USER = os.environ.get('GITHUB_USER', 'Cactusrad')
    def ensure_data_dir():
        DATA_DIR.mkdir(parents=True, exist_ok=True)
    def get_base_url(port, path=''):
        return f"http://{HOST_IP}:{port}{path}"

try:
    import requests as http_requests
except ImportError:
    http_requests = None

app = Flask(__name__, static_folder=None)

# ============ Secret Key Setup ============
def get_or_create_secret_key():
    """Get secret key from env, or generate and persist one"""
    if SECRET_KEY:
        return SECRET_KEY
    secret_file = os.path.join(DATA_DIR, '.secret_key')
    if os.path.exists(secret_file):
        with open(secret_file, 'r') as f:
            return f.read().strip()
    key = secrets.token_hex(32)
    ensure_data_dir()
    with open(secret_file, 'w') as f:
        f.write(key)
    return key

_secret = get_or_create_secret_key()
app.secret_key = _secret
app.config['SESSION_COOKIE_NAME'] = 'cactus_session'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)
import sys
print(f"[AUTH] Worker PID={os.getpid()} secret_key hash: {hash(_secret)}", file=sys.stderr, flush=True)

# ============ User Management ============
def load_users():
    """Load users from users.json"""
    return load_json_file(str(USERS_FILE), lambda: {"users": {}})

def save_users(data):
    """Save users to users.json"""
    return save_json_file(str(USERS_FILE), data)

def hash_password(password):
    """Hash a password with bcrypt"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def check_password(password, password_hash):
    """Verify a password against its hash"""
    return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))

def create_initial_users():
    """Create default users if users.json doesn't exist or is empty"""
    data = load_users()
    if data.get('users'):
        return
    now = datetime.now().isoformat()
    data['users'] = {
        'pierre': {
            'username': 'pierre',
            'password_hash': hash_password('12345'),
            'display_name': 'Pierre',
            'role': 'admin',
            'created_at': now
        },
        'mohamed': {
            'username': 'mohamed',
            'password_hash': hash_password('12345'),
            'display_name': 'Mohamed',
            'role': 'user',
            'created_at': now
        }
    }
    save_users(data)
    print("Created initial users: pierre (admin), mohamed (user)")

# ============ Auth Helpers ============
def get_current_user():
    """Get the currently logged-in username from session"""
    return session.get('username')

def get_effective_user():
    """Get the effective user (respects admin 'view as' feature)"""
    username = get_current_user()
    if not username:
        return None
    if is_admin(username):
        view_as = session.get('admin_view_as')
        if view_as:
            return view_as
    return username

def is_admin(username=None):
    """Check if a user has admin role"""
    if username is None:
        username = get_current_user()
    if not username:
        return False
    data = load_users()
    user = data.get('users', {}).get(username)
    return user and user.get('role') == 'admin'

# ============ User-scoped Data ============
def get_user_data_dir(username):
    """Get or create the data directory for a user"""
    user_dir = os.path.join(str(USERS_DATA_DIR), username)
    os.makedirs(user_dir, exist_ok=True)
    return user_dir

def load_user_preferences(username):
    """Load preferences for a specific user"""
    user_dir = get_user_data_dir(username)
    filepath = os.path.join(user_dir, 'preferences.json')
    return load_json_file(filepath, get_default_preferences)

def save_user_preferences(username, prefs):
    """Save preferences for a specific user"""
    user_dir = get_user_data_dir(username)
    filepath = os.path.join(user_dir, 'preferences.json')
    return save_json_file(filepath, prefs)

def load_user_apps(username):
    """Load apps for a specific user"""
    user_dir = get_user_data_dir(username)
    filepath = os.path.join(user_dir, 'apps.json')
    return load_json_file(filepath, lambda: {"apps": {}})

def save_user_apps(username, data):
    """Save apps for a specific user"""
    user_dir = get_user_data_dir(username)
    filepath = os.path.join(user_dir, 'apps.json')
    return save_json_file(filepath, data)

def send_telegram(message, parse_mode="HTML"):
    """Envoie un message via Telegram"""
    if http_requests is None:
        print("Module requests non disponible")
        return False
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram non configuré (variables d'environnement manquantes)")
        return False
    try:
        http_requests.post(f"{TELEGRAM_API_URL}/sendMessage", data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": parse_mode
        }, timeout=10)
        return True
    except Exception as e:
        print(f"Erreur Telegram: {e}")
        return False

def notify_claude_request(req_data):
    """Envoie une notification Telegram quand une nouvelle demande est soumise"""
    type_emojis = {"feature": "✨", "bug": "🐛", "improvement": "🔧"}
    type_labels = {"feature": "Fonctionnalité", "bug": "Bug", "improvement": "Amélioration"}
    priority_emojis = {"normal": "📋", "high": "⚠️", "urgent": "🔴"}

    emoji = type_emojis.get(req_data['type'], '📋')
    priority = priority_emojis.get(req_data['priority'], '📋')
    type_label = type_labels.get(req_data['type'], req_data['type'])

    message = f"""{priority} <b>Nouvelle demande ERP #{req_data['id']}</b>

{emoji} <b>Type:</b> {type_label}
📝 <b>Titre:</b> {req_data['title']}

<i>Réponds à ce message pour me donner des instructions.</i>"""

    send_telegram(message)

CORS(app, supports_credentials=True)

def get_default_preferences():
    """Préférences par défaut si le fichier n'existe pas"""
    return {
        "pages": [
            {
                "id": "main",
                "name": "Accueil",
                "apps": []
            }
        ],
        "currentPage": "main"
    }

def load_json_file(filepath, default_func):
    """Generic JSON file loader with fallback to default"""
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
    return default_func()

def save_json_file(filepath, data):
    """Generic JSON file saver"""
    try:
        ensure_data_dir()
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Error writing {filepath}: {type(e).__name__}: {e}", file=sys.stderr)
        return False

def load_preferences():
    return load_json_file(PREFERENCES_FILE, get_default_preferences)

def save_preferences(prefs):
    return save_json_file(PREFERENCES_FILE, prefs)

def load_apps():
    return load_json_file(APPS_FILE, lambda: {"apps": {}})

def save_apps(data):
    return save_json_file(APPS_FILE, data)

def migrate_custom_apps():
    """Migrate customApps from preferences.json to apps.json if needed"""
    prefs = load_preferences()
    custom_apps = prefs.get('customApps', {})
    if not custom_apps:
        return

    apps_data = load_apps()
    from datetime import datetime
    now = datetime.now().isoformat()

    for app_id, app in custom_apps.items():
        if app_id not in apps_data['apps']:
            app_entry = dict(app)
            app_entry.setdefault('created_at', now)
            app_entry.setdefault('updated_at', now)
            apps_data['apps'][app_id] = app_entry

    save_apps(apps_data)

    # Remove customApps from preferences
    del prefs['customApps']
    save_preferences(prefs)
    print(f"Migrated {len(custom_apps)} custom apps to apps.json")

# ============ Startup: Migration & User Init ============
def migrate_to_multi_user():
    """Migrate global data to per-user directories if needed"""
    users_dir = str(USERS_DATA_DIR)
    prefs_file = str(PREFERENCES_FILE)
    apps_file = str(APPS_FILE)

    if os.path.exists(prefs_file) and not os.path.exists(users_dir):
        print("Migrating to multi-user data structure...")
        for username in ['pierre', 'mohamed']:
            user_dir = get_user_data_dir(username)
            # Copy preferences
            if os.path.exists(prefs_file):
                shutil.copy2(prefs_file, os.path.join(user_dir, 'preferences.json'))
            # Copy apps
            if os.path.exists(apps_file):
                shutil.copy2(apps_file, os.path.join(user_dir, 'apps.json'))
            # Run custom apps migration for this user
            user_prefs_file = os.path.join(user_dir, 'preferences.json')
            user_apps_file = os.path.join(user_dir, 'apps.json')
            try:
                with open(user_prefs_file, 'r', encoding='utf-8') as f:
                    prefs = json.load(f)
                custom_apps = prefs.get('customApps', {})
                if custom_apps:
                    apps_data = {"apps": {}}
                    if os.path.exists(user_apps_file):
                        with open(user_apps_file, 'r', encoding='utf-8') as f:
                            apps_data = json.load(f)
                    now = datetime.now().isoformat()
                    for app_id, app_val in custom_apps.items():
                        if app_id not in apps_data.get('apps', {}):
                            entry = dict(app_val)
                            entry.setdefault('created_at', now)
                            entry.setdefault('updated_at', now)
                            apps_data.setdefault('apps', {})[app_id] = entry
                    with open(user_apps_file, 'w', encoding='utf-8') as f:
                        json.dump(apps_data, f, indent=2, ensure_ascii=False)
                    del prefs['customApps']
                    with open(user_prefs_file, 'w', encoding='utf-8') as f:
                        json.dump(prefs, f, indent=2, ensure_ascii=False)
            except Exception as e:
                print(f"Error migrating custom apps for {username}: {e}")
            print(f"  Migrated data for {username}")
        # Rename old files as backup
        if os.path.exists(prefs_file):
            os.rename(prefs_file, prefs_file + '.bak')
        if os.path.exists(apps_file):
            os.rename(apps_file, apps_file + '.bak')
        print("Migration complete. Old files renamed to .bak")
    else:
        # Still run customApps migration for existing per-user data
        migrate_custom_apps()

# Run startup tasks
create_initial_users()
migrate_to_multi_user()

# ============ Auth Middleware ============
LOCAL_SUBNET = ipaddress.ip_network('192.168.1.0/24')
LOCAL_DEFAULT_USER = 'pierre'
PUBLIC_ROUTES = {'/', '/health', '/api/auth/login', '/api/auth/me'}
PUBLIC_PREFIXES = ('/chromium/',)

def is_local_network():
    """Check if request comes from the local subnet"""
    ip_str = request.headers.get('X-Forwarded-For', request.remote_addr)
    # X-Forwarded-For may contain multiple IPs, take the first
    ip_str = ip_str.split(',')[0].strip()
    try:
        return ipaddress.ip_address(ip_str) in LOCAL_SUBNET
    except ValueError:
        return False

@app.before_request
def require_auth():
    """Require authentication for all API routes except public ones"""
    # Always allow CORS preflight (OPTIONS) requests
    if request.method == 'OPTIONS':
        return None
    if request.path in PUBLIC_ROUTES:
        return None
    for prefix in PUBLIC_PREFIXES:
        if request.path.startswith(prefix):
            return None
    # Static files / non-API routes
    if not request.path.startswith('/api/'):
        return None
    user = get_current_user()
    if not user and is_local_network():
        # Auto-login for local network requests
        session.permanent = True
        session['username'] = LOCAL_DEFAULT_USER
        return None
    if not user:
        cookie_val = request.cookies.get('session', 'NONE')
        print(f"[AUTH 401] {request.method} {request.path} | Cookie present: {cookie_val != 'NONE'} | Cookie[:30]: {cookie_val[:30]} | Session keys: {list(session.keys())} | PID: {os.getpid()} | IP: {request.remote_addr}")
        return jsonify({"status": "error", "message": "Authentication required"}), 401

# ============ Auth Endpoints ============
@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    """Login and create session"""
    try:
        data = request.get_json()
        username = data.get('username', '').strip().lower()
        password = data.get('password', '')

        users = load_users()
        user = users.get('users', {}).get(username)
        if not user or not check_password(password, user['password_hash']):
            return jsonify({"status": "error", "message": "Identifiants incorrects"}), 401

        session.permanent = True
        session['username'] = username
        session.pop('admin_view_as', None)

        return jsonify({
            "status": "ok",
            "user": {
                "username": username,
                "display_name": user['display_name'],
                "role": user['role']
            }
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/auth/logout', methods=['POST'])
def auth_logout():
    """Logout and destroy session"""
    session.clear()
    return jsonify({"status": "ok"})

@app.route('/api/auth/me', methods=['GET'])
def auth_me():
    """Get current user info"""
    username = get_current_user()
    if not username and is_local_network():
        session.permanent = True
        session['username'] = LOCAL_DEFAULT_USER
        username = LOCAL_DEFAULT_USER
    if not username:
        return jsonify({"status": "error", "message": "Not authenticated"}), 401

    users = load_users()
    user = users.get('users', {}).get(username)
    if not user:
        session.clear()
        return jsonify({"status": "error", "message": "User not found"}), 401

    result = {
        "username": username,
        "display_name": user['display_name'],
        "role": user['role'],
        "is_admin": user['role'] == 'admin',
        "viewing_as": session.get('admin_view_as', username)
    }

    if user['role'] == 'admin':
        result['all_users'] = [
            {"username": u, "display_name": d['display_name'], "role": d['role']}
            for u, d in users.get('users', {}).items()
        ]

    return jsonify(result)

@app.route('/api/auth/password', methods=['POST'])
def auth_change_password():
    """Change current user's password"""
    username = get_current_user()
    if not username:
        return jsonify({"status": "error", "message": "Not authenticated"}), 401

    try:
        data = request.get_json()
        current_password = data.get('current_password', '')
        new_password = data.get('new_password', '')

        if not new_password or len(new_password) < 4:
            return jsonify({"status": "error", "message": "Le mot de passe doit faire au moins 4 caractères"}), 400

        users = load_users()
        user = users.get('users', {}).get(username)
        if not user or not check_password(current_password, user['password_hash']):
            return jsonify({"status": "error", "message": "Mot de passe actuel incorrect"}), 401

        user['password_hash'] = hash_password(new_password)
        save_users(users)
        return jsonify({"status": "ok", "message": "Mot de passe modifié"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/auth/switch-user', methods=['POST'])
def auth_switch_user():
    """Admin: switch effective user (view as)"""
    username = get_current_user()
    if not username or not is_admin(username):
        return jsonify({"status": "error", "message": "Admin required"}), 403

    try:
        data = request.get_json()
        target = data.get('username', '').strip().lower()

        users = load_users()
        if target not in users.get('users', {}):
            return jsonify({"status": "error", "message": "User not found"}), 404

        if target == username:
            session.pop('admin_view_as', None)
        else:
            session['admin_view_as'] = target

        return jsonify({"status": "ok", "viewing_as": target})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/')
def index():
    """Sert la page principale - read fresh each time"""
    with open('/app/index.html', 'r', encoding='utf-8') as f:
        content = f.read()
    response = make_response(content)
    response.headers['Content-Type'] = 'text/html; charset=utf-8'
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response

@app.route('/chromium/')
@app.route('/chromium/<path:filename>')
def chromium_files(filename='autologin.html'):
    """Sert les fichiers du dossier chromium"""
    return send_from_directory('chromium', filename)

@app.route('/api/preferences', methods=['GET'])
def get_preferences():
    """Récupère les préférences (user-scoped)"""
    username = get_effective_user()
    prefs = load_user_preferences(username)
    apps_data = load_user_apps(username)
    prefs['customApps'] = apps_data.get('apps', {})
    return jsonify(prefs)

@app.route('/api/preferences', methods=['POST'])
def update_preferences():
    """Met à jour les préférences (user-scoped)"""
    try:
        username = get_effective_user()
        prefs = request.get_json()
        if save_user_preferences(username, prefs):
            return jsonify({"status": "ok"})
        else:
            return jsonify({"status": "error", "message": "Erreur de sauvegarde"}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/preferences/pages', methods=['POST'])
def update_pages():
    """Met à jour uniquement les pages (user-scoped)"""
    try:
        username = get_effective_user()
        pages = request.get_json()
        prefs = load_user_preferences(username)
        prefs['pages'] = pages
        if save_user_preferences(username, prefs):
            return jsonify({"status": "ok"})
        else:
            return jsonify({"status": "error", "message": "Erreur de sauvegarde"}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/preferences/current-page', methods=['POST'])
def update_current_page():
    """Met à jour la page courante (user-scoped)"""
    try:
        username = get_effective_user()
        data = request.get_json()
        prefs = load_user_preferences(username)
        prefs['currentPage'] = data.get('currentPage', 'main')
        if save_user_preferences(username, prefs):
            return jsonify({"status": "ok"})
        else:
            return jsonify({"status": "error", "message": "Erreur de sauvegarde"}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/preferences/custom-apps', methods=['POST'])
def update_custom_apps():
    """Legacy endpoint - proxies to user apps.json"""
    try:
        username = get_effective_user()
        req_data = request.get_json()
        incoming_apps = req_data.get('customApps', {})
        now = datetime.now().isoformat()

        data = load_user_apps(username)

        for app_id, app_val in incoming_apps.items():
            app_entry = dict(app_val)
            app_entry.setdefault('created_at', now)
            app_entry['updated_at'] = now
            data['apps'][app_id] = app_entry

        current_ids = set(data['apps'].keys())
        incoming_ids = set(incoming_apps.keys())
        for removed_id in current_ids - incoming_ids:
            del data['apps'][removed_id]

        if save_user_apps(username, data):
            return jsonify({"status": "ok"})
        else:
            return jsonify({"status": "error", "message": "Save failed"}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/preferences/app-overrides', methods=['POST'])
def update_app_overrides():
    """Met à jour les overrides d'applications (user-scoped)"""
    try:
        username = get_effective_user()
        data = request.get_json()
        prefs = load_user_preferences(username)
        prefs['appOverrides'] = data.get('appOverrides', {})
        if save_user_preferences(username, prefs):
            return jsonify({"status": "ok"})
        else:
            return jsonify({"status": "error", "message": "Erreur de sauvegarde"}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ============ Apps CRUD (separate file) ============

@app.route('/api/apps', methods=['GET'])
def get_apps():
    """List all custom apps (user-scoped)"""
    username = get_effective_user()
    data = load_user_apps(username)
    return jsonify(data)

@app.route('/api/apps', methods=['POST'])
def create_app():
    """Create a new custom app (user-scoped)"""
    try:
        username = get_effective_user()
        req_data = request.get_json()

        app_id = req_data.get('id', 'custom_' + str(int(datetime.now().timestamp() * 1000)))
        now = datetime.now().isoformat()

        new_app = {
            'id': app_id,
            'name': req_data.get('name', ''),
            'url': req_data.get('url', ''),
            'desc': req_data.get('desc', ''),
            'port': req_data.get('port', ''),
            'icon': req_data.get('icon', 'globe'),
            'gradient': req_data.get('gradient', 'linear-gradient(135deg, #3b82f6, #1d4ed8)'),
            'created_at': now,
            'updated_at': now
        }

        data = load_user_apps(username)
        data['apps'][app_id] = new_app

        if save_user_apps(username, data):
            return jsonify({"status": "ok", "app": new_app}), 201
        else:
            return jsonify({"status": "error", "message": "Save failed"}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/apps/<app_id>', methods=['GET'])
def get_app(app_id):
    """Get a single app by ID (user-scoped)"""
    username = get_effective_user()
    data = load_user_apps(username)
    app_data = data['apps'].get(app_id)
    if not app_data:
        return jsonify({"status": "error", "message": "App not found"}), 404
    return jsonify(app_data)

@app.route('/api/apps/<app_id>', methods=['PUT'])
def update_app(app_id):
    """Update an existing app (user-scoped)"""
    try:
        username = get_effective_user()
        req_data = request.get_json()

        data = load_user_apps(username)
        if app_id not in data['apps']:
            return jsonify({"status": "error", "message": "App not found"}), 404

        app_data = data['apps'][app_id]

        for field in ['name', 'url', 'desc', 'port', 'icon', 'gradient']:
            if field in req_data:
                app_data[field] = req_data[field]

        app_data['updated_at'] = datetime.now().isoformat()
        data['apps'][app_id] = app_data

        if save_user_apps(username, data):
            return jsonify({"status": "ok", "app": app_data})
        else:
            return jsonify({"status": "error", "message": "Save failed"}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/apps/<app_id>', methods=['DELETE'])
def delete_app(app_id):
    """Delete an app and remove from all pages (user-scoped)"""
    try:
        username = get_effective_user()
        data = load_user_apps(username)
        if app_id not in data['apps']:
            return jsonify({"status": "error", "message": "App not found"}), 404

        del data['apps'][app_id]
        save_user_apps(username, data)

        prefs = load_user_preferences(username)
        for page in prefs.get('pages', []):
            if app_id in page.get('apps', []):
                page['apps'] = [a for a in page['apps'] if a != app_id]
        save_user_preferences(username, prefs)

        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ============ Terminal State (for multi-device sync) ============

@app.route('/api/terminal/state', methods=['GET'])
def get_terminal_state():
    """Récupère l'état des terminaux (user-scoped)"""
    try:
        username = get_effective_user()
        prefs = load_user_preferences(username)
        terminal_state = prefs.get('terminalState', {
            'tabs': [],
            'activeTabId': None,
            'viewMode': 'tabs'
        })
        return jsonify(terminal_state)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/terminal/state', methods=['POST'])
def update_terminal_state():
    """Sauvegarde l'état des terminaux (user-scoped)"""
    try:
        username = get_effective_user()
        data = request.get_json()
        prefs = load_user_preferences(username)
        prefs['terminalState'] = {
            'tabs': data.get('tabs', []),
            'activeTabId': data.get('activeTabId'),
            'viewMode': data.get('viewMode', 'tabs')
        }
        if save_user_preferences(username, prefs):
            return jsonify({"status": "ok"})
        else:
            return jsonify({"status": "error", "message": "Erreur de sauvegarde"}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/health')
def health():
    """Endpoint de santé"""
    return jsonify({"status": "healthy"})

# ============ Projects/Folders Management ============
CLAUDE_PROJECTS_DIR = PROJECTS_DIR

# --- Git helpers ---

def get_project_path(name):
    """Validate project name and return absolute path. Blocks path traversal."""
    if not name or '..' in name or '/' in name or '\\' in name:
        return None
    return os.path.join(str(CLAUDE_PROJECTS_DIR), name)

def is_git_repo(path):
    """Check if path is a git repo (regular or worktree)."""
    git_path = os.path.join(path, '.git')
    return os.path.isdir(git_path) or os.path.isfile(git_path)

def run_git(path, args, timeout=10):
    """Run a git command safely. Returns (success, stdout, stderr)."""
    try:
        env = os.environ.copy()
        env['GIT_SSH_COMMAND'] = 'ssh -i /root/.ssh/github_key -o StrictHostKeyChecking=accept-new'
        result = subprocess.run(
            ['git', '-C', path] + args,
            capture_output=True, text=True, timeout=timeout, env=env
        )
        return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return False, '', 'Command timed out'
    except Exception as e:
        return False, '', str(e)

def get_main_project(name):
    """If name contains '--', return the parent project name."""
    if '--' in name:
        return name.split('--')[0]
    return None

def sanitize_branch_for_dirname(branch):
    """Convert branch name to safe dirname: feat/login -> feat-login"""
    return re.sub(r'[^a-zA-Z0-9._-]', '-', branch)

def detect_default_branch(project_path):
    """Detect the repo's default branch (main/master), not the currently checked-out one."""
    ok, out, _ = run_git(project_path, ['symbolic-ref', '--short', 'refs/remotes/origin/HEAD'])
    if ok and out:
        # e.g. "origin/main" -> "main"
        return out.split('/', 1)[1] if '/' in out else out
    for candidate in ('main', 'master'):
        ok, _, _ = run_git(project_path, ['show-ref', '--verify', '--quiet', f'refs/heads/{candidate}'])
        if ok:
            return candidate
    return ''

def get_git_info(project_path):
    """Get git status info for a project."""
    if not is_git_repo(project_path):
        return None

    info = {'is_repo': True, 'branch': '', 'default_branch': '', 'dirty': False, 'worktrees': [], 'branches': []}

    # Current branch
    ok, branch, _ = run_git(project_path, ['rev-parse', '--abbrev-ref', 'HEAD'])
    if ok:
        info['branch'] = branch

    # Default branch (main/master) — reference for behind/merged calculations
    info['default_branch'] = detect_default_branch(project_path)

    # Dirty check
    ok, status, _ = run_git(project_path, ['status', '--porcelain'])
    if ok:
        info['dirty'] = len(status) > 0

    # Worktrees
    worktree_branches = set()
    if branch:
        worktree_branches.add(branch)  # current branch is in main worktree

    ok, output, _ = run_git(project_path, ['worktree', 'list', '--porcelain'])
    if ok and output:
        worktrees = []
        current_wt = {}
        for line in output.split('\n'):
            if line.startswith('worktree '):
                if current_wt and current_wt.get('path') != project_path:
                    worktrees.append(current_wt)
                current_wt = {'path': line[9:]}
            elif line.startswith('branch '):
                ref = line[7:]  # refs/heads/feat/login
                current_wt['branch'] = ref.replace('refs/heads/', '')
            elif line.startswith('HEAD '):
                current_wt['head'] = line[5:]
        if current_wt and current_wt.get('path') != project_path:
            worktrees.append(current_wt)

        # Track ALL worktree branches (including agent ones) to hide from branch list
        for wt in worktrees:
            wt_branch = wt.get('branch', '')
            if wt_branch:
                worktree_branches.add(wt_branch)
        # Filter out Claude Code agent worktrees from display
        worktrees = [wt for wt in worktrees if '/.claude/worktrees/' not in wt.get('path', '')]

        # Use the repo's default branch (main/master) for behind-main detection
        main_branch = info['default_branch'] or info['branch']

        for wt in worktrees:
            dirname = os.path.basename(wt.get('path', ''))
            wt_branch = wt.get('branch', '')
            # Check if worktree is dirty
            wt_dirty = False
            wt_path = wt.get('path', '')
            if os.path.isdir(wt_path):
                ok2, wt_status, _ = run_git(wt_path, ['status', '--porcelain'])
                if ok2:
                    wt_dirty = len(wt_status) > 0
            # Check how many commits behind main
            behind_main = 0
            if wt_branch and main_branch and wt_branch != main_branch:
                ok3, count, _ = run_git(project_path, ['rev-list', '--count', f'{wt_branch}..{main_branch}'])
                if ok3 and count.strip().isdigit():
                    behind_main = int(count.strip())
            info['worktrees'].append({
                'branch': wt_branch,
                'dirname': dirname,
                'dirty': wt_dirty,
                'behind_main': behind_main
            })

    # Detect merged branches (merged into default branch — main/master)
    merged_branches = set()
    main_branch = info.get('default_branch', '') or info.get('branch', '')
    if main_branch:
        ok, merged_output, _ = run_git(project_path, ['branch', '--merged', main_branch, '--format=%(refname:short)'])
        if ok and merged_output:
            merged_branches = set(merged_output.split('\n'))

    # Local branches (excluding worktree branches and agent branches)
    ok, br_output, _ = run_git(project_path, ['branch', '--format=%(refname:short)'])
    if ok and br_output:
        for b in br_output.split('\n'):
            if not b or b in worktree_branches:
                continue
            # Skip agent branches (created by Claude Code worktree isolation)
            if b.startswith('worktree-agent-'):
                continue
            is_merged = b in merged_branches and b != main_branch
            behind_main = 0
            # Skip behind_main calc for merged branches (they're cleanup candidates)
            if not is_merged and main_branch and b != main_branch:
                ok3, count, _ = run_git(project_path, ['rev-list', '--count', f'{b}..{main_branch}'])
                if ok3 and count.strip().isdigit():
                    behind_main = int(count.strip())
            info['branches'].append({'name': b, 'behind_main': behind_main, 'merged': is_merged})

    return info


@app.route('/api/projects/folders', methods=['GET'])
def get_project_folders():
    """Retourne la liste des dossiers projet en scannant le volume monté localement"""
    try:
        folders = []
        skip = {'.', '..', '__pycache__', 'node_modules'}
        if os.path.exists(CLAUDE_PROJECTS_DIR):
            for item in os.listdir(CLAUDE_PROJECTS_DIR):
                item_path = os.path.join(CLAUDE_PROJECTS_DIR, item)
                if os.path.isdir(item_path) and not item.startswith('.') and item not in skip:
                    folders.append(item)
        folders.sort(key=str.lower)

        # Identify worktree folders (contain '--') and group them
        worktree_dirs = set()
        for f in folders:
            parent = get_main_project(f)
            if parent and parent in folders:
                worktree_dirs.add(f)

        # Main folders = exclude worktree subdirs
        main_folders = [f for f in folders if f not in worktree_dirs]

        # Filtrer les dossiers cachés (user-scoped)
        username = get_effective_user()
        prefs = load_user_preferences(username)
        hidden = prefs.get('hiddenFolders', [])
        visible_folders = [f for f in main_folders if f not in hidden]

        result = {
            "folders": visible_folders,
            "hidden": hidden
        }

        # If ?git=1, enrich with git info
        if request.args.get('git') == '1':
            git_info = {}
            for folder in visible_folders:
                folder_path = os.path.join(str(CLAUDE_PROJECTS_DIR), folder)
                info = get_git_info(folder_path)
                if info:
                    git_info[folder] = info
            result['git'] = git_info

        return jsonify(result)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/projects/hidden', methods=['POST'])
def update_hidden_folders():
    """Met à jour la liste des dossiers cachés (user-scoped)"""
    try:
        username = get_effective_user()
        data = request.get_json()
        hidden = data.get('hidden', [])

        prefs = load_user_preferences(username)
        prefs['hiddenFolders'] = hidden

        if save_user_preferences(username, prefs):
            return jsonify({"status": "ok"})
        else:
            return jsonify({"status": "error", "message": "Erreur de sauvegarde"}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/projects/create', methods=['POST'])
def create_project_folder():
    """Crée un nouveau dossier projet dans CLAUDE_PROJECTS_DIR"""
    try:
        data = request.get_json()
        name = data.get('name', '').strip()

        if not name:
            return jsonify({"status": "error", "message": "Nom requis"}), 400
        if name.startswith('.') or '/' in name or '\\' in name:
            return jsonify({"status": "error", "message": "Nom invalide"}), 400

        folder_path = os.path.join(CLAUDE_PROJECTS_DIR, name)
        if os.path.exists(folder_path):
            return jsonify({"status": "error", "message": "Ce dossier existe déjà"}), 409

        os.makedirs(folder_path)
        return jsonify({"status": "ok", "folder": name})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ============ Git Integration ============

BRANCH_NAME_RE = re.compile(r'^[a-zA-Z0-9._/\-]+$')

@app.route('/api/projects/<project>/git/status', methods=['GET'])
def get_git_status(project):
    """Get git status: branch, dirty, ahead/behind, last commit"""
    path = get_project_path(project)
    if not path or not os.path.isdir(path):
        return jsonify({"status": "error", "message": "Projet introuvable"}), 404
    if not is_git_repo(path):
        return jsonify({"status": "error", "message": "Pas un dépôt git"}), 400

    info = {'branch': '', 'dirty': False, 'ahead': 0, 'behind': 0, 'last_commit': ''}

    ok, branch, _ = run_git(path, ['rev-parse', '--abbrev-ref', 'HEAD'])
    if ok:
        info['branch'] = branch

    ok, status, _ = run_git(path, ['status', '--porcelain'])
    if ok:
        info['dirty'] = len(status) > 0

    # Ahead/behind
    ok, ab, _ = run_git(path, ['rev-list', '--left-right', '--count', f'{branch}...@{{u}}'])
    if ok and '\t' in ab:
        parts = ab.split('\t')
        info['ahead'] = int(parts[0])
        info['behind'] = int(parts[1])

    # Last commit
    ok, log, _ = run_git(path, ['log', '-1', '--format=%h %s'])
    if ok:
        info['last_commit'] = log

    return jsonify(info)

@app.route('/api/projects/<project>/git/branches', methods=['GET'])
def get_git_branches(project):
    """List local and remote branches"""
    path = get_project_path(project)
    if not path or not os.path.isdir(path):
        return jsonify({"status": "error", "message": "Projet introuvable"}), 404
    if not is_git_repo(path):
        return jsonify({"status": "error", "message": "Pas un dépôt git"}), 400

    # Fetch prune (best effort)
    run_git(path, ['fetch', '--prune'], timeout=15)

    branches = {'local': [], 'remote': [], 'current': ''}

    ok, current, _ = run_git(path, ['rev-parse', '--abbrev-ref', 'HEAD'])
    if ok:
        branches['current'] = current

    ok, output, _ = run_git(path, ['branch', '--format=%(refname:short)'])
    if ok:
        branches['local'] = [b for b in output.split('\n') if b]

    ok, output, _ = run_git(path, ['branch', '-r', '--format=%(refname:short)'])
    if ok:
        branches['remote'] = [b for b in output.split('\n') if b and 'HEAD' not in b]

    return jsonify(branches)

@app.route('/api/projects/<project>/git/branches/<path:branch>', methods=['DELETE'])
def delete_git_branch(project, branch):
    """Delete a local git branch"""
    path = get_project_path(project)
    if not path or not os.path.isdir(path):
        return jsonify({"status": "error", "message": "Projet introuvable"}), 404
    if not is_git_repo(path):
        return jsonify({"status": "error", "message": "Pas un dépôt git"}), 400

    # Validate branch name (no path traversal, no spaces)
    if not branch or '..' in branch or branch.startswith('-'):
        return jsonify({"status": "error", "message": "Nom de branche invalide"}), 400

    # Cannot delete current branch
    ok, current, _ = run_git(path, ['rev-parse', '--abbrev-ref', 'HEAD'])
    if ok and current == branch:
        return jsonify({"status": "error", "message": "Impossible de supprimer la branche courante"}), 400

    # Try safe delete first (-d), force with ?force=1 (-D)
    force = request.args.get('force') == '1'
    flag = '-D' if force else '-d'
    ok, out, err = run_git(path, ['branch', flag, branch])

    if not ok:
        if 'not fully merged' in err:
            return jsonify({"status": "error", "message": f"La branche '{branch}' n'est pas entièrement mergée. Utilisez ?force=1 pour forcer."}), 409
        return jsonify({"status": "error", "message": err}), 500

    return jsonify({"status": "ok"})

@app.route('/api/projects/<project>/git/worktrees', methods=['GET'])
def get_git_worktrees(project):
    """List active worktrees"""
    path = get_project_path(project)
    if not path or not os.path.isdir(path):
        return jsonify({"status": "error", "message": "Projet introuvable"}), 404
    if not is_git_repo(path):
        return jsonify({"status": "error", "message": "Pas un dépôt git"}), 400

    info = get_git_info(path)
    return jsonify({"worktrees": info.get('worktrees', []) if info else []})

@app.route('/api/projects/<project>/git/worktrees', methods=['POST'])
def create_git_worktree(project):
    """Create a new worktree with a branch"""
    path = get_project_path(project)
    if not path or not os.path.isdir(path):
        return jsonify({"status": "error", "message": "Projet introuvable"}), 404
    if not is_git_repo(path):
        return jsonify({"status": "error", "message": "Pas un dépôt git"}), 400

    data = request.get_json()
    branch = data.get('branch', '').strip()
    new_branch = data.get('new', True)

    if not branch or not BRANCH_NAME_RE.match(branch):
        return jsonify({"status": "error", "message": "Nom de branche invalide"}), 400

    dirname = f"{project}--{sanitize_branch_for_dirname(branch)}"
    wt_path = os.path.join(str(CLAUDE_PROJECTS_DIR), dirname)

    if os.path.exists(wt_path):
        return jsonify({"status": "error", "message": f"Le dossier {dirname} existe déjà"}), 409

    if new_branch:
        ok, out, err = run_git(path, ['worktree', 'add', '-b', branch, wt_path])
    else:
        ok, out, err = run_git(path, ['worktree', 'add', wt_path, branch])

    if not ok:
        return jsonify({"status": "error", "message": err}), 500

    return jsonify({"status": "ok", "dirname": dirname, "branch": branch})

@app.route('/api/projects/<project>/git/worktrees/<dirname>', methods=['DELETE'])
def delete_git_worktree(project, dirname):
    """Remove a worktree"""
    path = get_project_path(project)
    if not path or not os.path.isdir(path):
        return jsonify({"status": "error", "message": "Projet introuvable"}), 404

    # Validate dirname
    if '..' in dirname or '/' in dirname or '\\' in dirname:
        return jsonify({"status": "error", "message": "Nom invalide"}), 400

    wt_path = os.path.join(str(CLAUDE_PROJECTS_DIR), dirname)
    if not os.path.isdir(wt_path):
        return jsonify({"status": "error", "message": "Worktree introuvable"}), 404

    # Check if dirty (unless force)
    force = request.args.get('force') == '1'
    if not force:
        ok, status, _ = run_git(wt_path, ['status', '--porcelain'])
        if ok and len(status) > 0:
            return jsonify({"status": "error", "message": "Worktree contient des modifications non commités. Utilisez ?force=1 pour forcer."}), 409

    args = ['worktree', 'remove', wt_path]
    if force:
        args.append('--force')
    ok, out, err = run_git(path, args)

    if not ok:
        return jsonify({"status": "error", "message": err}), 500

    return jsonify({"status": "ok"})

@app.route('/api/projects/<project>/git/remotes', methods=['GET'])
def get_git_remotes(project):
    """Get remotes and auto-detect GitHub"""
    path = get_project_path(project)
    if not path or not os.path.isdir(path):
        return jsonify({"status": "error", "message": "Projet introuvable"}), 404
    if not is_git_repo(path):
        return jsonify({"status": "error", "message": "Pas un dépôt git"}), 400

    ok, output, _ = run_git(path, ['remote', '-v'])
    remotes = []
    if ok:
        seen = set()
        for line in output.split('\n'):
            parts = line.split()
            if len(parts) >= 2:
                name = parts[0]
                url = parts[1]
                if name not in seen:
                    seen.add(name)
                    remotes.append({'name': name, 'url': url})

    return jsonify({"remotes": remotes})

@app.route('/api/projects/<project>/git/link', methods=['POST'])
def link_git_repo(project):
    """Init git and/or add remote origin"""
    path = get_project_path(project)
    if not path or not os.path.isdir(path):
        return jsonify({"status": "error", "message": "Projet introuvable"}), 404

    data = request.get_json()
    url = data.get('url', '').strip()

    if not url:
        # Auto-detect: git@github.com:GITHUB_USER/project.git
        url = f"git@github.com:{GITHUB_USER}/{project}.git"

    # Init if not a git repo
    if not is_git_repo(path):
        ok, _, err = run_git(path, ['init'])
        if not ok:
            return jsonify({"status": "error", "message": f"git init failed: {err}"}), 500

    # Check if origin already exists
    ok, existing, _ = run_git(path, ['remote', 'get-url', 'origin'])
    if ok:
        # Update existing remote
        run_git(path, ['remote', 'set-url', 'origin', url])
    else:
        ok, _, err = run_git(path, ['remote', 'add', 'origin', url])
        if not ok:
            return jsonify({"status": "error", "message": f"remote add failed: {err}"}), 500

    return jsonify({"status": "ok", "url": url})

# ============ ERP Requests Management ============

def load_erp_requests():
    return load_json_file(ERP_REQUESTS_FILE, lambda: {"requests": [], "progress": []})

def save_erp_requests(data):
    return save_json_file(ERP_REQUESTS_FILE, data)

@app.route('/api/erp/requests', methods=['GET'])
def get_erp_requests():
    """Récupère les demandes ERP"""
    data = load_erp_requests()
    return jsonify(data)

@app.route('/api/erp/requests', methods=['POST'])
def add_erp_request():
    """Ajoute une nouvelle demande ERP"""
    try:
        from datetime import datetime
        req_data = request.get_json()
        data = load_erp_requests()

        new_request = {
            "id": len(data.get("requests", [])) + 1,
            "type": req_data.get("type", "feature"),  # feature, bug, improvement
            "title": req_data.get("title", ""),
            "description": req_data.get("description", ""),
            "priority": req_data.get("priority", "normal"),
            "status": "pending",  # pending, in_progress, done
            "created_at": datetime.now().isoformat(),
            "completed_at": None
        }

        if "requests" not in data:
            data["requests"] = []
        data["requests"].insert(0, new_request)

        if save_erp_requests(data):
            # Envoyer notification Pushover
            notify_claude_request(new_request)
            return jsonify({"status": "ok", "request": new_request})
        else:
            return jsonify({"status": "error", "message": "Erreur de sauvegarde"}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/erp/requests/<int:request_id>', methods=['PATCH'])
def update_erp_request(request_id):
    """Met à jour une demande ERP"""
    try:
        from datetime import datetime
        req_data = request.get_json()
        data = load_erp_requests()

        for req in data.get("requests", []):
            if req["id"] == request_id:
                if "status" in req_data:
                    req["status"] = req_data["status"]
                    if req_data["status"] == "done":
                        req["completed_at"] = datetime.now().isoformat()
                if "title" in req_data:
                    req["title"] = req_data["title"]
                if "priority" in req_data:
                    req["priority"] = req_data["priority"]
                break

        if save_erp_requests(data):
            return jsonify({"status": "ok"})
        else:
            return jsonify({"status": "error", "message": "Erreur de sauvegarde"}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/erp/requests/<int:request_id>', methods=['DELETE'])
def delete_erp_request(request_id):
    """Supprime une demande ERP"""
    try:
        data = load_erp_requests()
        data["requests"] = [r for r in data.get("requests", []) if r["id"] != request_id]

        if save_erp_requests(data):
            return jsonify({"status": "ok"})
        else:
            return jsonify({"status": "error", "message": "Erreur de sauvegarde"}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/erp/progress', methods=['GET', 'POST'])
def erp_progress():
    """Gère le résumé de progression"""
    data = load_erp_requests()

    if request.method == 'GET':
        return jsonify({"progress": data.get("progress", [])})

    try:
        from datetime import datetime
        progress_data = request.get_json()

        new_entry = {
            "id": len(data.get("progress", [])) + 1,
            "text": progress_data.get("text", ""),
            "type": progress_data.get("type", "done"),  # done, in_progress
            "created_at": datetime.now().isoformat()
        }

        if "progress" not in data:
            data["progress"] = []
        data["progress"].insert(0, new_entry)

        # Garder seulement les 10 dernières entrées
        data["progress"] = data["progress"][:10]

        if save_erp_requests(data):
            return jsonify({"status": "ok", "entry": new_entry})
        else:
            return jsonify({"status": "error", "message": "Erreur de sauvegarde"}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ============ Terminal Activity Detection ============

# Patterns that indicate terminal is waiting for input
# Be careful not to match status bars or regular output
INPUT_PATTERNS = [
    # Standard interactive prompts (very specific, end of line)
    r'\[Y/n\]\s*$',
    r'\[y/N\]\s*$',
    r'\[yes/no\]\s*$',
    r'\(y/n\)\s*$',
    r'\(yes/no\)\s*$',
    r'Continue\?\s*$',
    r'Proceed\?\s*$',
    r'Overwrite\?\s*$',
    r'Delete\?\s*$',
    r'Are you sure\?\s*$',
    r'Press Enter to continue',
    r'Press any key to continue',
    r'Password:\s*$',
    r'password:\s*$',
    # Package manager prompts (apt, dnf, pacman)
    r'Do you want to continue\?\s*\[Y/n\]',
    r'Is this ok \[y/N\]',
    r'Proceed with installation\?',
    # Git prompts
    r'Stage this hunk',
    r'\(y,n,q,a,d',
    # rm/cp interactive prompts
    r"remove.*\?\s*$",
    r"overwrite.*\?\s*$",
    # sudo prompts
    r'\[sudo\] password',
    # SSH prompts
    r'Are you sure you want to continue connecting',
    r"fingerprint is.*\n.*\(yes/no",
]

def strip_ansi(text):
    """Remove ANSI escape codes and OSC sequences from text"""
    # Standard CSI sequences
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    text = ansi_escape.sub('', text)
    # OSC sequences (title changes, etc.)
    osc_escape = re.compile(r'\x1B\][^\x07]*\x07')
    text = osc_escape.sub('', text)
    # Other escape sequences
    other_escape = re.compile(r'\x1B[^[\]](.|$)')
    text = other_escape.sub('', text)
    return text

def check_terminal_activity(session_name):
    """Check if a terminal session is waiting for input"""
    log_file = os.path.join(TERMINAL_LOG_DIR, f'{session_name}.log')

    if not os.path.exists(log_file):
        return {'waiting': False, 'session': session_name, 'reason': 'no_log'}

    try:
        # Read last 8KB of log (Claude Code outputs a lot)
        with open(log_file, 'rb') as f:
            f.seek(0, 2)  # End of file
            size = f.tell()
            f.seek(max(0, size - 8192))
            content = f.read().decode('utf-8', errors='ignore')

        # Strip ANSI codes
        clean_content = strip_ansi(content)

        # Get last 20 lines (Claude Code has verbose output)
        lines = clean_content.strip().split('\n')
        last_lines = '\n'.join(lines[-20:])

        # Check for input prompts
        for pattern in INPUT_PATTERNS:
            if re.search(pattern, last_lines, re.IGNORECASE):
                return {
                    'waiting': True,
                    'session': session_name,
                    'pattern': pattern,
                    'preview': last_lines[-500:] if len(last_lines) > 500 else last_lines
                }

        return {'waiting': False, 'session': session_name}

    except Exception as e:
        return {'waiting': False, 'session': session_name, 'error': str(e)}

@app.route('/api/terminal/activity', methods=['GET'])
def get_terminal_activity():
    """Check activity status of all or specific terminals"""
    session = request.args.get('session')

    if session:
        return jsonify(check_terminal_activity(session))

    # Check all sessions
    results = {}
    if os.path.exists(TERMINAL_LOG_DIR):
        for log_file in glob.glob(os.path.join(TERMINAL_LOG_DIR, '*.log')):
            session_name = os.path.basename(log_file).replace('.log', '')
            results[session_name] = check_terminal_activity(session_name)

    return jsonify(results)

@app.route('/api/terminal/sessions', methods=['GET'])
def get_terminal_sessions():
    """List active dtach sessions"""
    sessions = []
    socket_dir = SOCKET_DIR

    if os.path.exists(socket_dir):
        for item in os.listdir(socket_dir):
            if item.endswith('.sock'):
                socket_path = os.path.join(socket_dir, item)
                if os.path.exists(socket_path):
                    session_name = item.replace('.sock', '')
                    sessions.append({
                        'name': session_name,
                        'socket': socket_path,
                        'mtime': os.path.getmtime(socket_path)
                    })

    return jsonify({'sessions': sessions})

# ============ Subagents API ============

CLAUDE_PROJECTS_BASE = CLAUDE_CONFIG_DIR

def get_claude_project_path(project_name):
    """Convert project name (e.g., 'guillevin') to Claude project path"""
    # Format: -home-cactus-claude-{project_name}
    project_dir_name = f'-home-cactus-claude-{project_name}'
    project_path = os.path.join(CLAUDE_PROJECTS_BASE, project_dir_name)
    if os.path.exists(project_path):
        return project_path
    return None

def get_active_session(project_path):
    """Find the most recent session with subagents in the project"""
    if not project_path or not os.path.exists(project_path):
        return None

    best_session = None
    best_mtime = 0

    for item in os.listdir(project_path):
        item_path = os.path.join(project_path, item)
        # Session directories are UUIDs (with dashes)
        if os.path.isdir(item_path) and '-' in item and len(item) == 36:
            subagents_path = os.path.join(item_path, 'subagents')
            if os.path.exists(subagents_path):
                # Get the most recently modified session
                mtime = os.path.getmtime(subagents_path)
                if mtime > best_mtime:
                    best_mtime = mtime
                    best_session = item_path

    return best_session

def parse_agent_status(jsonl_path):
    """Parse agent info from JSONL file (reads from end for efficiency)"""
    try:
        mtime = os.path.getmtime(jsonl_path)
        now = time.time()
        age_seconds = now - mtime

        # Read the entire file to get first and last lines
        with open(jsonl_path, 'r', encoding='utf-8', errors='ignore') as f:
            all_lines = [l.strip() for l in f if l.strip()]

        if not all_lines:
            return None

        message_count = len(all_lines)

        # Parse first line to get task description
        import json
        first_data = json.loads(all_lines[0])
        first_msg = first_data.get('message', {})
        first_content = first_msg.get('content', '')

        # Extract task description from first user message
        task_description = ''
        if isinstance(first_content, str) and first_content:
            # Take first line, limit to 80 chars
            first_line = first_content.split('\n')[0].strip()
            task_description = first_line[:80]
            if len(first_line) > 80:
                task_description += '...'

        # Parse last line for status
        last_line = all_lines[-1]
        data = json.loads(last_line)

        agent_id = data.get('agentId', os.path.basename(jsonl_path).replace('agent-', '').replace('.jsonl', ''))
        slug = data.get('slug', 'unknown')
        message = data.get('message', {})
        role = message.get('role', 'unknown')
        stop_reason = message.get('stop_reason')
        timestamp = data.get('timestamp', '')

        # Determine status based on file age
        if age_seconds < 30:
            status = 'running'
        elif age_seconds < 120:
            status = 'idle'
        else:
            status = 'completed'

        # If stop_reason is explicitly set to end_turn, mark as completed
        if stop_reason == 'end_turn':
            status = 'completed'

        return {
            'agentId': agent_id,
            'slug': slug,
            'taskDescription': task_description,
            'status': status,
            'messageCount': message_count,
            'lastActivity': mtime,
            'ageSeconds': int(age_seconds),
            'lastRole': role,
            'stopReason': stop_reason,
            'timestamp': timestamp
        }
    except Exception as e:
        print(f"Error parsing agent {jsonl_path}: {e}")
        return None

@app.route('/api/subagents/<project>')
def get_subagents(project):
    """Get list of subagents for a project"""
    project_path = get_claude_project_path(project)
    if not project_path:
        return jsonify({'agents': [], 'error': 'Project not found'})

    session_path = get_active_session(project_path)
    if not session_path:
        return jsonify({'agents': [], 'sessionId': None})

    subagents_path = os.path.join(session_path, 'subagents')
    agents = []

    if os.path.exists(subagents_path):
        for filename in os.listdir(subagents_path):
            if filename.startswith('agent-') and filename.endswith('.jsonl'):
                filepath = os.path.join(subagents_path, filename)
                agent_info = parse_agent_status(filepath)
                if agent_info:
                    agents.append(agent_info)

    # Sort by last activity (most recent first)
    agents.sort(key=lambda x: x['lastActivity'], reverse=True)

    return jsonify({
        'agents': agents,
        'sessionId': os.path.basename(session_path),
        'sessionPath': session_path
    })

@app.route('/api/subagents/<project>/stats')
def get_subagents_stats(project):
    """Get subagent statistics for a project"""
    project_path = get_claude_project_path(project)
    if not project_path:
        return jsonify({'total': 0, 'running': 0, 'completed': 0, 'idle': 0})

    session_path = get_active_session(project_path)
    if not session_path:
        return jsonify({'total': 0, 'running': 0, 'completed': 0, 'idle': 0, 'sessionId': None})

    subagents_path = os.path.join(session_path, 'subagents')
    stats = {'total': 0, 'running': 0, 'completed': 0, 'idle': 0}

    if os.path.exists(subagents_path):
        for filename in os.listdir(subagents_path):
            if filename.startswith('agent-') and filename.endswith('.jsonl'):
                filepath = os.path.join(subagents_path, filename)
                agent_info = parse_agent_status(filepath)
                if agent_info:
                    stats['total'] += 1
                    status = agent_info['status']
                    if status in stats:
                        stats[status] += 1

    stats['sessionId'] = os.path.basename(session_path)
    return jsonify(stats)

@app.route('/api/subagents/<project>/<agent_id>/logs')
def get_agent_logs(project, agent_id):
    """Get formatted messages from an agent's JSONL file"""
    lines_param = request.args.get('lines', 50, type=int)
    lines_param = min(lines_param, 200)  # Cap at 200 lines

    project_path = get_claude_project_path(project)
    if not project_path:
        return jsonify({'messages': [], 'error': 'Project not found'})

    session_path = get_active_session(project_path)
    if not session_path:
        return jsonify({'messages': [], 'error': 'No active session'})

    # Find the agent file
    subagents_path = os.path.join(session_path, 'subagents')
    agent_file = None

    for filename in os.listdir(subagents_path):
        if filename.startswith(f'agent-{agent_id}') and filename.endswith('.jsonl'):
            agent_file = os.path.join(subagents_path, filename)
            break

    if not agent_file or not os.path.exists(agent_file):
        return jsonify({'messages': [], 'error': 'Agent not found'})

    try:
        import json
        messages = []

        # Read from end for efficiency (most recent messages)
        with open(agent_file, 'rb') as f:
            f.seek(0, 2)
            size = f.tell()
            # Read enough to get requested lines (estimate ~2KB per message)
            read_size = min(size, lines_param * 3000)
            f.seek(max(0, size - read_size))
            content = f.read().decode('utf-8', errors='ignore')

        lines = content.strip().split('\n')

        for line in lines:
            if not line.strip() or not line.startswith('{'):
                continue
            try:
                data = json.loads(line)
                msg = data.get('message', {})

                # Extract text content
                content_text = ''
                if isinstance(msg.get('content'), str):
                    content_text = msg['content']
                elif isinstance(msg.get('content'), list):
                    for block in msg['content']:
                        if isinstance(block, dict) and block.get('type') == 'text':
                            content_text += block.get('text', '')

                if content_text:
                    messages.append({
                        'role': msg.get('role', 'unknown'),
                        'content': content_text[:5000],  # Truncate long messages
                        'timestamp': data.get('timestamp', ''),
                        'uuid': data.get('uuid', '')
                    })
            except json.JSONDecodeError:
                continue

        # Return last N messages
        return jsonify({
            'messages': messages[-lines_param:],
            'total': len(messages),
            'agentId': agent_id
        })

    except Exception as e:
        return jsonify({'messages': [], 'error': str(e)})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80, debug=False)
