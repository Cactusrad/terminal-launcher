#!/usr/bin/env python3
"""
Serveur Flask pour Homepage Cactus
Fournit une API pour sauvegarder les préférences globalement
"""

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import json
import os
import requests as http_requests

app = Flask(__name__, static_folder='.')

# Telegram Bot Configuration (from environment variables)
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}" if TELEGRAM_BOT_TOKEN else ''

def send_telegram(message, parse_mode="HTML"):
    """Envoie un message via Telegram"""
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

PREFERENCES_FILE = '/data/preferences.json'

def get_default_preferences():
    """Préférences par défaut si le fichier n'existe pas"""
    return {
        "pages": [
            {
                "id": "main",
                "name": "Accueil",
                "apps": ["ha", "grafana", "portainer", "influxdb", "neviweb", "n8n", "notify", "mcp-manager", "serial-numbers", "opermax-quote", "trading-bot", "guillevin"]
            },
            {
                "id": "terminals",
                "name": "Terminaux",
                "apps": ["terminal", "claude", "sudo-claude"]
            }
        ],
        "currentPage": "main"
    }

def load_preferences():
    """Charge les préférences depuis le fichier JSON"""
    try:
        if os.path.exists(PREFERENCES_FILE):
            with open(PREFERENCES_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"Erreur lecture préférences: {e}")
    return get_default_preferences()

def save_preferences(prefs):
    """Sauvegarde les préférences dans le fichier JSON"""
    try:
        os.makedirs(os.path.dirname(PREFERENCES_FILE), exist_ok=True)
        with open(PREFERENCES_FILE, 'w', encoding='utf-8') as f:
            json.dump(prefs, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Erreur sauvegarde préférences: {e}")
        return False

@app.route('/')
def index():
    """Sert la page principale"""
    return send_from_directory('.', 'index.html')

@app.route('/chromium/')
@app.route('/chromium/<path:filename>')
def chromium_files(filename='autologin.html'):
    """Sert les fichiers du dossier chromium"""
    return send_from_directory('chromium', filename)

@app.route('/api/preferences', methods=['GET'])
def get_preferences():
    """Récupère les préférences"""
    prefs = load_preferences()
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

@app.route('/health')
def health():
    """Endpoint de santé"""
    return jsonify({"status": "healthy"})

# ============ Projects/Folders Management ============
CLAUDE_PROJECTS_DIR = '/home/cactus/claude'

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

        # Charger les dossiers cachés
        prefs = load_preferences()
        hidden = prefs.get('hiddenFolders', [])

        return jsonify({
            "folders": folders,
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
ERP_REQUESTS_FILE = '/data/erp_requests.json'

def load_erp_requests():
    """Charge les demandes ERP"""
    try:
        if os.path.exists(ERP_REQUESTS_FILE):
            with open(ERP_REQUESTS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"Erreur lecture demandes ERP: {e}")
    return {"requests": [], "progress": []}

def save_erp_requests(data):
    """Sauvegarde les demandes ERP"""
    try:
        os.makedirs(os.path.dirname(ERP_REQUESTS_FILE), exist_ok=True)
        with open(ERP_REQUESTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Erreur sauvegarde demandes ERP: {e}")
        return False

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
import re
import glob

TERMINAL_LOG_DIR = '/tmp/terminal-logs'

# Patterns that indicate terminal is waiting for input
INPUT_PATTERNS = [
    r'\[Y/n\]',
    r'\[y/N\]',
    r'\[yes/no\]',
    r'\(y/n\)',
    r'\? \[Y/n\]',
    r'Press Enter',
    r'Press any key',
    r'Continue\?',
    r'Proceed\?',
    r'Do you want to proceed',
    r'Are you sure',
    r'Overwrite\?',
    r'Delete\?',
    r'Password:',
    r'password:',
    r': $',  # Generic prompt ending with colon
]

def strip_ansi(text):
    """Remove ANSI escape codes from text"""
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

def check_terminal_activity(session_name):
    """Check if a terminal session is waiting for input"""
    log_file = os.path.join(TERMINAL_LOG_DIR, f'{session_name}.log')

    if not os.path.exists(log_file):
        return {'waiting': False, 'session': session_name, 'reason': 'no_log'}

    try:
        # Read last 4KB of log
        with open(log_file, 'rb') as f:
            f.seek(0, 2)  # End of file
            size = f.tell()
            f.seek(max(0, size - 4096))
            content = f.read().decode('utf-8', errors='ignore')

        # Strip ANSI codes
        clean_content = strip_ansi(content)

        # Get last few lines
        lines = clean_content.strip().split('\n')
        last_lines = '\n'.join(lines[-10:])

        # Check for input prompts
        for pattern in INPUT_PATTERNS:
            if re.search(pattern, last_lines, re.IGNORECASE):
                return {
                    'waiting': True,
                    'session': session_name,
                    'pattern': pattern,
                    'preview': last_lines[-300:] if len(last_lines) > 300 else last_lines
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
    socket_dir = '/tmp/dtach-sessions'

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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80, debug=False)
