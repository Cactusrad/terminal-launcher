#!/usr/bin/env python3
"""
Serveur Flask pour Homepage Cactus
Fournit une API pour sauvegarder les préférences globalement
"""

from flask import Flask, jsonify, request, send_from_directory, make_response
from flask_cors import CORS
import json
import os
import re
import glob
import time

try:
    from config import *
except ImportError:
    DATA_DIR = '/data'
    PREFERENCES_FILE = '/data/preferences.json'
    APPS_FILE = '/data/apps.json'
    ERP_REQUESTS_FILE = '/data/erp_requests.json'
    PROJECTS_DIR = '/home/cactus/claude'
    CLAUDE_CONFIG_DIR = '/home/cactus/.claude/projects'
    TERMINAL_LOG_DIR = '/tmp/terminal-logs'
    SOCKET_DIR = '/tmp/dtach-sessions'
    TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
    TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')
    TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}" if TELEGRAM_BOT_TOKEN else ''
    def ensure_data_dir():
        os.makedirs(DATA_DIR, exist_ok=True)

try:
    import requests as http_requests
except ImportError:
    http_requests = None

app = Flask(__name__, static_folder=None)

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

CORS(app)

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
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Error writing {filepath}: {e}")
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

# Run migration on startup
migrate_custom_apps()

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
    """Récupère les préférences"""
    prefs = load_preferences()
    # Merge apps from apps.json for backward compatibility
    apps_data = load_apps()
    prefs['customApps'] = apps_data.get('apps', {})
    return jsonify(prefs)

@app.route('/api/preferences', methods=['POST'])
def update_preferences():
    """Met à jour les préférences"""
    try:
        prefs = request.get_json()
        if save_preferences(prefs):
            return jsonify({"status": "ok"})
        else:
            return jsonify({"status": "error", "message": "Erreur de sauvegarde"}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/preferences/pages', methods=['POST'])
def update_pages():
    """Met à jour uniquement les pages"""
    try:
        pages = request.get_json()
        prefs = load_preferences()
        prefs['pages'] = pages
        if save_preferences(prefs):
            return jsonify({"status": "ok"})
        else:
            return jsonify({"status": "error", "message": "Erreur de sauvegarde"}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/preferences/current-page', methods=['POST'])
def update_current_page():
    """Met à jour la page courante"""
    try:
        data = request.get_json()
        prefs = load_preferences()
        prefs['currentPage'] = data.get('currentPage', 'main')
        if save_preferences(prefs):
            return jsonify({"status": "ok"})
        else:
            return jsonify({"status": "error", "message": "Erreur de sauvegarde"}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/preferences/custom-apps', methods=['POST'])
def update_custom_apps():
    """Legacy endpoint - proxies to apps.json"""
    try:
        from datetime import datetime
        req_data = request.get_json()
        incoming_apps = req_data.get('customApps', {})
        now = datetime.now().isoformat()

        data = load_apps()

        # Sync: add/update incoming apps
        for app_id, app in incoming_apps.items():
            app_entry = dict(app)
            app_entry.setdefault('created_at', now)
            app_entry['updated_at'] = now
            data['apps'][app_id] = app_entry

        # Remove apps not in incoming set
        current_ids = set(data['apps'].keys())
        incoming_ids = set(incoming_apps.keys())
        for removed_id in current_ids - incoming_ids:
            del data['apps'][removed_id]

        if save_apps(data):
            return jsonify({"status": "ok"})
        else:
            return jsonify({"status": "error", "message": "Save failed"}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/preferences/app-overrides', methods=['POST'])
def update_app_overrides():
    """Met à jour les overrides d'applications (URL, nom, description, port personnalisés)"""
    try:
        data = request.get_json()
        prefs = load_preferences()
        prefs['appOverrides'] = data.get('appOverrides', {})
        if save_preferences(prefs):
            return jsonify({"status": "ok"})
        else:
            return jsonify({"status": "error", "message": "Erreur de sauvegarde"}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ============ Apps CRUD (separate file) ============

@app.route('/api/apps', methods=['GET'])
def get_apps():
    """List all custom apps"""
    data = load_apps()
    return jsonify(data)

@app.route('/api/apps', methods=['POST'])
def create_app():
    """Create a new custom app"""
    try:
        from datetime import datetime
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

        data = load_apps()
        data['apps'][app_id] = new_app

        if save_apps(data):
            return jsonify({"status": "ok", "app": new_app}), 201
        else:
            return jsonify({"status": "error", "message": "Save failed"}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/apps/<app_id>', methods=['GET'])
def get_app(app_id):
    """Get a single app by ID"""
    data = load_apps()
    app = data['apps'].get(app_id)
    if not app:
        return jsonify({"status": "error", "message": "App not found"}), 404
    return jsonify(app)

@app.route('/api/apps/<app_id>', methods=['PUT'])
def update_app(app_id):
    """Update an existing app"""
    try:
        from datetime import datetime
        req_data = request.get_json()

        data = load_apps()
        if app_id not in data['apps']:
            return jsonify({"status": "error", "message": "App not found"}), 404

        app = data['apps'][app_id]

        # Update only provided fields
        for field in ['name', 'url', 'desc', 'port', 'icon', 'gradient']:
            if field in req_data:
                app[field] = req_data[field]

        app['updated_at'] = datetime.now().isoformat()
        data['apps'][app_id] = app

        if save_apps(data):
            return jsonify({"status": "ok", "app": app})
        else:
            return jsonify({"status": "error", "message": "Save failed"}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/apps/<app_id>', methods=['DELETE'])
def delete_app(app_id):
    """Delete an app and remove from all pages"""
    try:
        data = load_apps()
        if app_id not in data['apps']:
            return jsonify({"status": "error", "message": "App not found"}), 404

        del data['apps'][app_id]
        save_apps(data)

        # Also remove from all pages in preferences
        prefs = load_preferences()
        for page in prefs.get('pages', []):
            if app_id in page.get('apps', []):
                page['apps'] = [a for a in page['apps'] if a != app_id]
        save_preferences(prefs)

        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ============ Terminal State (for multi-device sync) ============

@app.route('/api/terminal/state', methods=['GET'])
def get_terminal_state():
    """Récupère l'état des terminaux (onglets ouverts, mode de vue)"""
    try:
        prefs = load_preferences()
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
    """Sauvegarde l'état des terminaux"""
    try:
        data = request.get_json()
        prefs = load_preferences()
        prefs['terminalState'] = {
            'tabs': data.get('tabs', []),
            'activeTabId': data.get('activeTabId'),
            'viewMode': data.get('viewMode', 'tabs')
        }
        if save_preferences(prefs):
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

@app.route('/api/projects/folders', methods=['GET'])
def get_project_folders():
    """Scanne et retourne la liste des dossiers projet"""
    try:
        folders = []
        if os.path.exists(CLAUDE_PROJECTS_DIR):
            for item in os.listdir(CLAUDE_PROJECTS_DIR):
                item_path = os.path.join(CLAUDE_PROJECTS_DIR, item)
                if os.path.isdir(item_path) and not item.startswith('.'):
                    folders.append(item)
        folders.sort(key=str.lower)

        # Charger les dossiers cachés et les filtrer
        prefs = load_preferences()
        hidden = prefs.get('hiddenFolders', [])
        visible_folders = [f for f in folders if f not in hidden]

        return jsonify({
            "folders": visible_folders,
            "hidden": hidden
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/projects/hidden', methods=['POST'])
def update_hidden_folders():
    """Met à jour la liste des dossiers cachés"""
    try:
        data = request.get_json()
        hidden = data.get('hidden', [])

        prefs = load_preferences()
        prefs['hiddenFolders'] = hidden

        if save_preferences(prefs):
            return jsonify({"status": "ok"})
        else:
            return jsonify({"status": "error", "message": "Erreur de sauvegarde"}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

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
