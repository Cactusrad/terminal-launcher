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

# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN = "8559016458:AAFZJLQO_Mm3ew-L9nbmWWTwOOManjbcszc"
TELEGRAM_CHAT_ID = "7190745870"
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

def send_telegram(message, parse_mode="HTML"):
    """Envoie un message via Telegram"""
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80, debug=False)
