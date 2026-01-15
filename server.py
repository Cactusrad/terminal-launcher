#!/usr/bin/env python3
"""
Serveur Flask pour Homepage Cactus
Fournit une API pour sauvegarder les préférences globalement
"""

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import json
import os

app = Flask(__name__, static_folder='.')
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80, debug=False)
