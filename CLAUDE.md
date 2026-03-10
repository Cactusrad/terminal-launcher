# CLAUDE.md - Terminal Launcher

## Résumé

Dashboard homelab "Cactus Home" — lanceur de raccourcis avec authentification multi-utilisateur et préférences isolées par user.

- **URL** : `http://192.168.1.100` (port 80)
- **Repo** : `git@github.com:Cactusrad/terminal-launcher.git`
- **Conteneur** : `terminal-launcher` (Docker Compose)

## Architecture

```
Navigateur ──► Docker (terminal-launcher, port 80)
                ├── Gunicorn (2 workers)
                │   └── Flask (server.py)
                │       ├── GET /          → index.html (read from disk, no cache)
                │       ├── /api/auth/*   → Login/logout/session (bcrypt + signed cookies)
                │       └── /api/*         → JSON preferences (user-scoped)
                └── Volume launcher-data
                    ├── /data/users.json          (comptes utilisateurs)
                    ├── /data/.secret_key         (clé de session Flask)
                    └── /data/users/{username}/   (préférences per-user)
                        ├── preferences.json
                        └── apps.json

           ──► terminal-server.py (hôte, port 7681, systemd)
                └── WebSocket + PTY sessions (aiohttp, venv Python)

           ──► ttyd (hôte, port 7694, systemd)
                └── terminal-launcher-workspace (tmux)
```

**Serveur de production** : `192.168.1.100`
**Paths sur l'hôte** : `~/terminal-launcher/` (pas `~/claude/terminal-launcher/`)
**Dev/git** : `~/claude/terminal-launcher/` sur 192.168.1.200

**Fichier unique** : `index.html` (~290KB) contient tout le CSS, JS et HTML.

## Stack

- **Backend** : Python 3.11, Flask 3.0, Gunicorn, Flask-CORS, python-dotenv, bcrypt
- **Auth** : Cookies signés Flask (`cactus_session`), bcrypt password hashing, sessions 7 jours
- **Frontend** : HTML/CSS/JS vanilla, SVG inline (82+ icônes Lucide-style)
- **Infra** : Docker Compose, volume persistant `launcher-data`
- **Design** : Dark mode par défaut (#0a0a0f), glassmorphism, police Inter, accent orange #E75B12

## Commandes Docker

```bash
cd /home/cactus/claude/terminal-launcher

# Rebuild et redéployer
docker compose build --no-cache && docker compose up -d

# Logs
docker logs terminal-launcher

# Inspecter les préférences d'un user
docker exec terminal-launcher cat /data/users/pierre/preferences.json

# Inspecter les users
docker exec terminal-launcher cat /data/users.json

# Reset complet (users + prefs)
docker exec terminal-launcher rm -rf /data/users /data/users.json /data/.secret_key
```

## API REST

| Endpoint | Méthode | Description |
|----------|---------|-------------|
| `/` | GET | Page HTML (lu depuis disque, no-cache) |
| `/health` | GET | Health check |
| `/api/auth/login` | POST | Login (username/password → cookie session) |
| `/api/auth/logout` | POST | Logout (détruit session) |
| `/api/auth/me` | GET | Info user courant + is_admin + liste users |
| `/api/auth/password` | POST | Changer son mot de passe |
| `/api/auth/switch-user` | POST | Admin : voir les données d'un autre user |
| `/api/preferences` | GET/POST | Préférences complètes (user-scoped) |
| `/api/preferences/pages` | POST | Pages uniquement |
| `/api/preferences/current-page` | POST | Page courante |
| `/api/preferences/custom-apps` | POST | Applications personnalisées |
| `/api/preferences/app-overrides` | POST | Overrides d'apps (URL, nom, etc.) |
| `/api/terminal/state` | GET/POST | État des terminaux (onglets, vue) |
| `/api/terminal/activity` | GET | Détection d'attente terminal |
| `/api/terminal/sessions` | GET | Sessions dtach actives |
| `/api/projects/folders` | GET | Dossiers dans /home/cactus/claude (scan local du volume monté) |
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
  "appOverrides": {},
  "hiddenFolders": ["folder1", "folder2"]
}
```

- **Défauts** : aucune app (clean install)
- **Stockage** : `/data/users/{username}/preferences.json` (volume Docker, per-user)
- **Fallback** : localStorage si API indisponible

## Authentification

- **Users** : stockés dans `/data/users.json` avec hash bcrypt
- **Users par défaut** : `pierre` (admin, mdp `12345`), `mohamed` (user, mdp `12345`)
- **Cookie** : `cactus_session`, signé avec `/data/.secret_key`, HTTPOnly, SameSite=Lax, 7 jours
- **Routes publiques** : `/`, `/health`, `/api/auth/login`, `/api/auth/me`
- **Middleware** : `before_request` retourne 401 sur `/api/*` si pas de session
- **Réseau local** : les requêtes depuis `192.168.1.0/24` sont auto-connectées en tant que `pierre` (pas de login requis). Configuré via `LOCAL_SUBNET` et `LOCAL_DEFAULT_USER` dans `server.py`
- **Admin** : Pierre peut switcher vers un autre user pour voir/modifier ses données (`admin_view_as` en session)
- **Migration** : au premier démarrage, si `/data/preferences.json` existe et `/data/users/` n'existe pas, les données globales sont copiées vers chaque user puis renommées en `.bak`
- **Frontend** : login overlay glassmorphism (z-index 2000), fetch interceptor 401 avec compteur de 3 consécutifs, menu user + admin switcher dans la top-bar

## Fonctionnalités principales

- **Raccourcis** : création avec nom, URL, icône (82+), couleur (16 gradients)
- **Auto-prefix URL** : ajoute `http://` si protocole manquant
- **Pages multiples** : organisation par pages, drag & drop
- **Menu contextuel** : clic droit → modifier, déplacer, supprimer
- **Multi-utilisateur** : login, préférences isolées, admin peut voir les données des autres
- **Sync globale** : préférences partagées entre appareils (per-user)
- **Thème** : dark (défaut) / light toggle
- **Terminal Manager** : xterm.js + WebSocket, sessions dtach
- **Projets** : scan dynamique de /home/cactus/claude
- **Demandes ERP** : tickets avec notifications Telegram
- **Bug Report** : widget connecté au bugs_service local (http://192.168.1.200:9010), projet "Terminal Launcher" (slug: terminal-launcher, préfixe: TER)

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
terminal-launcher/
├── CLAUDE.md              # Cette documentation
├── server.py              # Flask backend + API REST + auth (~1100 lignes)
├── config.py              # Configuration centralisée (dotenv, Path, SECRET_KEY, USERS_*)
├── index.html             # Frontend complet (~300KB, inclut login overlay + auth JS)
├── requirements.txt       # flask, flask-cors, gunicorn, requests, python-dotenv, aiohttp, bcrypt
├── Dockerfile             # Python 3.11-slim, gunicorn, healthcheck
├── docker-compose.yml     # Port 80, volume launcher-data
├── .env.example           # Template de configuration
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
- **Déploiement indépendant** : chaque install (.100, .200) est autonome. Les projets sont scannés depuis le volume local `/home/cactus/claude` monté dans le conteneur, pas via le terminal-server distant.
- **Persistance** : toutes les données (users, préférences, apps, secret key) survivent aux rebuilds Docker grâce au volume `launcher-data`
- **Cookie session** : nommé `cactus_session` (pas `session`) pour éviter les conflits avec d'anciens cookies
- **SECRET_KEY** : env var optionnelle ; si absente, auto-générée et persistée dans `/data/.secret_key`

## Session du 27 février 2026

**Synchronisation des terminaux entre postes**

Permet à plusieurs appareils de voir les mêmes onglets terminaux en temps réel.

1. **Auto-reconnexion WebSocket**
   - `loadTerminal()` refactorisé avec fonction interne `connectWs()` rappelable
   - `ws.onclose` déclenche une reconnexion automatique avec backoff exponentiel (2s → 4s → 8s → 16s → 30s max)
   - Message jaune "Connexion perdue. Reconnexion..." affiché dans le terminal xterm.js
   - `terminal.onData` et `ResizeObserver` utilisent `getWs()` (lookup dans `terminalInstances`) au lieu d'une référence fermée, pour survivre aux reconnexions
   - `disposedTabs` Set + flag `ws._manualClose` empêchent la reconnexion lors d'un close volontaire
   - `manualRefreshTerminal()` nettoie `disposedTabs` après dispose pour permettre la recréation

2. **Sync polling toutes les 5 secondes (`syncTerminalTabs()`)**
   - Fetch `/api/terminal/state` (état serveur) et `http://host:7681/sessions` (sessions dtach actives)
   - Merge par `tmuxSession` (clé unique) :
     - Session sur serveur mais pas locale → créer le tab + `loadTerminal()`
     - Session locale mais dtach morte → `closeTerminalTab()`
   - `startTerminalSync()` / `stopTerminalSync()` gèrent le `setInterval`
   - Polling démarré dans `initTerminalManager()`, stoppé quand on quitte la page Terminaux
   - Skip si `saveDebounceTimeout` actif (l'utilisateur vient de faire un changement)

3. **Smart save anti-écrasement (`saveTerminalState()`)**
   - Avant de sauver vers le serveur, fetch l'état courant
   - Merge par union sur `tmuxSession` : les tabs distants absents localement sont conservés
   - `saveDebounceTimeout` remis à `null` après exécution du callback

**Structures de données modifiées :**
- `terminalInstances` Map : tabId → `{ terminal, fitAddon, ws, resizeObserver, reconnectTimer }`
- `disposedTabs` Set : tabIds fermés volontairement (empêche la reconnexion)
- `syncInterval` : ID du setInterval de polling
