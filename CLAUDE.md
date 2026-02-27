# CLAUDE.md - Homepage Cactus

## Résumé

Dashboard homelab "Cactus Home" — lanceur de raccourcis avec persistance globale des préférences.

- **URL** : `http://192.168.1.100` (port 80)
- **Repo** : `git@github.com:Cactusrad/homepage-app.git`
- **Conteneur** : `homepage` (Docker Compose)

## Architecture

```
Navigateur ──► Docker (homepage, port 80)
                ├── Gunicorn (2 workers)
                │   └── Flask (server.py)
                │       ├── GET /          → index.html (read from disk, no cache)
                │       └── /api/*         → JSON preferences
                └── Volume homepage-data
                    └── /data/preferences.json
```

**Fichier unique** : `index.html` (~290KB) contient tout le CSS, JS et HTML.

## Stack

- **Backend** : Python 3.11, Flask 3.0, Gunicorn, Flask-CORS
- **Frontend** : HTML/CSS/JS vanilla, SVG inline (82+ icônes Lucide-style)
- **Infra** : Docker Compose, volume persistant `homepage-data`
- **Design** : Dark mode par défaut (#0a0a0f), glassmorphism, police Inter, accent orange #E75B12

## Commandes Docker

```bash
cd /home/cactus/homepage-app

# Rebuild et redéployer
docker compose build --no-cache && docker compose up -d

# Logs
docker logs homepage

# Inspecter les préférences
docker exec homepage cat /data/preferences.json

# Reset préférences (clean install)
docker exec homepage rm -f /data/preferences.json
```

## API REST

| Endpoint | Méthode | Description |
|----------|---------|-------------|
| `/` | GET | Page HTML (lu depuis disque, no-cache) |
| `/health` | GET | Health check |
| `/api/preferences` | GET/POST | Préférences complètes |
| `/api/preferences/pages` | POST | Pages uniquement |
| `/api/preferences/current-page` | POST | Page courante |
| `/api/preferences/custom-apps` | POST | Applications personnalisées |
| `/api/preferences/app-overrides` | POST | Overrides d'apps (URL, nom, etc.) |
| `/api/terminal/state` | GET/POST | État des terminaux (onglets, vue) |
| `/api/terminal/activity` | GET | Détection d'attente terminal |
| `/api/terminal/sessions` | GET | Sessions dtach actives |
| `/api/projects/folders` | GET | Dossiers dans /home/cactus/claude |
| `/api/projects/hidden` | POST | Dossiers cachés |
| `/api/erp/requests` | GET/POST | Demandes ERP (+notification Telegram) |
| `/api/erp/requests/<id>` | PATCH/DELETE | Gestion demande ERP |
| `/api/subagents/<project>` | GET | Sous-agents Claude d'un projet |

## Préférences (format JSON)

```json
{
  "pages": [{ "id": "main", "name": "Accueil", "apps": [] }],
  "currentPage": "main",
  "customApps": { "custom_123": { "id": "...", "name": "...", "url": "...", "icon": "...", "gradient": "..." } },
  "appOverrides": {}
}
```

- **Défauts** : aucune app (clean install)
- **Stockage** : `/data/preferences.json` (volume Docker)
- **Fallback** : localStorage si API indisponible

## Fonctionnalités principales

- **Raccourcis** : création avec nom, URL, icône (82+), couleur (16 gradients)
- **Auto-prefix URL** : ajoute `http://` si protocole manquant
- **Pages multiples** : organisation par pages, drag & drop
- **Menu contextuel** : clic droit → modifier, déplacer, supprimer
- **Sync globale** : préférences partagées entre appareils
- **Thème** : dark (défaut) / light toggle
- **Terminal Manager** : xterm.js + WebSocket, sessions dtach
- **Projets** : scan dynamique de /home/cactus/claude
- **Demandes ERP** : tickets avec notifications Telegram
- **Bug Report** : widget connecté à bugs.sharpi.ca

## Créer un raccourci (code)

Les apps custom sont stockées dans `customApps` avec un gradient inline.
Pour ajouter une app par défaut (hardcodée), modifier `defaultApps` dans index.html :

```javascript
const defaultApps = [
    { id: 'myapp', name: 'Mon App', desc: 'Description', port: ':5001', url: baseUrl(5001), icon: 'myapp' }
];
```

Puis ajouter l'icône SVG dans l'objet `icons` et le style CSS `.myapp { background: linear-gradient(...); }`.

## Fichiers du projet

```
homepage-app/
├── CLAUDE.md              # Cette documentation
├── server.py              # Flask backend + API REST (~700 lignes)
├── index.html             # Frontend complet (~290KB)
├── requirements.txt       # flask, flask-cors, gunicorn, requests
├── Dockerfile             # Python 3.11-slim, gunicorn
├── docker-compose.yml     # Port 80, volume homepage-data
├── terminal-server.py     # Serveur WebSocket pour terminaux
├── chromium/              # Config navigateur Chromium distant
├── dtach-wrapper.sh       # Wrapper sessions dtach
└── *.service              # Services systemd (ttyd, terminal-server)
```

## Notes importantes

- `static_folder=None` sur Flask — le fichier est lu avec `open()` à chaque requête
- Headers `Cache-Control: no-cache, no-store, must-revalidate` sur la route `/`
- L'IP de la machine est `192.168.1.100` (pas .200)
- Notifications Telegram via env vars `TELEGRAM_BOT_TOKEN` et `TELEGRAM_CHAT_ID` dans `.env`
