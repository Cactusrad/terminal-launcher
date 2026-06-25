# CLAUDE.md - Terminal Launcher

## Résumé

Dashboard homelab "Cactus Home" — lanceur de raccourcis avec authentification multi-utilisateur et préférences isolées par user.

- **URL prod** : `https://192.168.1.100` (nginx 443 ; HTTP sur le port 180 → 301 HTTPS). ⚠️ le port 80 de `.100` est pris par `erp-web`, pas par le launcher
- **URL dev** : `https://192.168.1.200` (même topologie nginx)
- **URL distante** : `https://terminal.sharpi.ca` → instance dev `.200` via Cloudflare Access + tunnel SSH (voir « Accès distant »)
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
                    ├── /data/users.json            (comptes utilisateurs)
                    ├── /data/.secret_key           (clé de session Flask)
                    ├── /data/shared_page.json      (page de raccourcis partagée, admin-éditable)
                    ├── /data/worktree_origins.json (registre origine/owner des worktrees)
                    └── /data/users/{username}/     (préférences per-user)
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

## Accès distant (terminal.sharpi.ca)

Expose l'instance dev `.200` hors LAN, sans ouvrir de port chez Cactus :

```
Navigateur ──► Cloudflare (CF Access : auth Pierre uniquement)
           ──► Droplet DO 143.198.32.13 (nginx + TLS Let's Encrypt)
                └── proxy_pass http://127.0.0.1:9103
           ──► Tunnel SSH inverse (initié DEPUIS .200 : -R 127.0.0.1:9103:localhost:80)
           ──► nginx .200 port 80, vhost `server_name terminal.sharpi.ca` (nginx.conf)
                ├── /              → conteneur terminal-launcher:80
                ├── /terminal-ws/  → host:7681 (WebSocket terminaux, Upgrade headers)
                └── /terminal-api/ → host:7681 (REST sessions dtach)
```

- **Pas de redirect HTTPS sur ce vhost** : la requête arrive déjà en HTTPS côté public (TLS terminé au droplet), un 301 vers HTTPS créerait une boucle. Le `default_server` port 80 garde son 301 pour l'accès LAN direct.
- **Keepalive** : cron (`* * * * *` + `@reboot`) → `/home/cactus/scripts/terminal-tunnel-keepalive.sh`. Idempotent via PID file `/tmp/terminal_tunnel.pid` ; si le tunnel meurt, relancé au tick suivant. Logs : `~/logs/terminal-tunnel.log` (+ `terminal-tunnel-ssh.log`).
- **Clé dédiée restreinte** : `~/.ssh/id_ed25519_terminal_tunnel`, limitée côté droplet par `restrict,permitlisten="127.0.0.1:9103"` — même compromise, elle ne peut faire que ce port-forward précis. SSH du droplet sur le port **5896**. `known_hosts` séparé : `~/.ssh/known_hosts_terminal`.
- **Frontend** : aucun changement requis — quand la page est servie en HTTPS, `index.html` utilise déjà les chemins relatifs `/terminal-ws/` et `/terminal-api/` (même mécanisme que l'accès HTTPS LAN) au lieu de `host:7681` en direct.
- Le droplet est le même que celui du tunnel Home Assistant (`hilo.sharpi.ca`, service user `ha-tunnel.service`), mais le tunnel terminal est géré par cron, pas par systemd.

## Stack

- **Backend** : Python 3.11, Flask 3.0, Gunicorn, Flask-CORS, python-dotenv, bcrypt
- **Auth** : Cookies signés Flask (`cactus_session`), bcrypt password hashing, sessions 7 jours
- **Frontend** : HTML/CSS/JS vanilla, SVG inline (82+ icônes Lucide-style)
- **Infra** : Docker Compose, volume persistant `launcher-data`
- **Design** : Dark mode par défaut (#0a0a0f), glassmorphism, police Inter, accent orange #E75B12

## Commandes Docker

```bash
cd /home/cactus/claude/terminal-launcher

# Rebuild local (dev). NE PAS utiliser --no-cache : ça reconstruit toutes les
# layers à neuf et fait exploser le build cache (303 GB observés en 3 jours,
# incident 2026-05-07 — disque .100 à 96% par accumulation de dangling images).
docker compose build && docker compose up -d

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
| `/api/auth/select-user` | POST | Sélection de user **sans mot de passe** (LAN uniquement, 403 sinon) |
| `/api/auth/logout` | POST | Logout (détruit session) |
| `/api/auth/me` | GET | Info user courant + is_admin + liste users |
| `/api/auth/password` | POST | Changer son mot de passe |
| `/api/auth/switch-user` | POST | Admin : voir les données d'un autre user |
| `/api/preferences` | GET/POST | Préférences complètes (user-scoped) |
| `/api/preferences/pages` | POST | Pages uniquement |
| `/api/preferences/current-page` | POST | Page courante |
| `/api/preferences/custom-apps` | POST | Applications personnalisées |
| `/api/preferences/app-overrides` | POST | Overrides d'apps (URL, nom, etc.) |
| `/api/shared/page` | GET/POST | Page de raccourcis partagée (GET : tous ; POST : admin only) |
| `/api/terminal/state` | GET/POST | État des terminaux (onglets, vue) |
| `/api/terminal/activity` | GET | Détection d'attente terminal |
| `/api/terminal/sessions` | GET | Sessions dtach actives |
| `/api/projects/folders` | GET | Dossiers dans /home/cactus/claude (scan local du volume monté). `?git=1` enrichit avec branches + worktrees (+ `origin` par worktree) |
| `/api/projects/hidden` | POST | Dossiers cachés |
| `/api/projects/<p>/git/worktrees` | POST | Créer un worktree (marque `origin=user` dans le registre + marqueur in-tree) |
| `/api/projects/<p>/git/worktrees/<dir>` | DELETE | Supprimer un worktree (nettoie le registre) |
| `/api/projects/<p>/git/worktrees/<dir>/origin` | POST | Forcer l'origine d'un worktree `{"origin":"user"\|"claude"}` |
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
- **Apps custom** : `/data/users/{username}/apps.json` (séparé des pages depuis le commit `408cb16`). Les `customApps` sont des **objets indépendants** ; les `pages[].apps` ne contiennent que des **IDs** d'apps. Si une page est réinitialisée, les apps existent encore mais deviennent **orphelines** (non assignées à aucune page).
- **Source de vérité** : le serveur uniquement. **JAMAIS** de localStorage pour les données applicatives (préférences, tabs terminaux, issues, tasks). Plusieurs clients travaillent en simultané sur les mêmes sessions → localStorage = données stales/conflits.
- **localStorage autorisé** uniquement pour l'UI state pur navigateur : `cactusTheme`, `expandedProjects`, `terminalViewMode`, `alertsMuted`
- **TODO** : supprimer les fallbacks localStorage restants (cactusPages, cactusCurrentPage, cactusAppOverrides, cactusCustomApps, cactusTerminalTabs) et migrer projectIssues/agentTasks vers des API serveur

### ⚠️ Bug connu : écrasement des pages avec un état vide

**Symptôme** : la page Accueil devient vide ("Ajoutez votre premier raccourci") alors que les apps custom existent encore dans `apps.json`.

**Cause probable** : `savePages([{id:main, apps:[]}])` est appelé à un moment où `cachedPages` a été reset à `null` puis remis à `defaultPages` (clone vide), souvent autour de :
- `switchUser()` (line ~8969 index.html) qui fait `cachedPages = null` puis `await loadPreferencesFromAPI()` — si une action utilisateur tombe entre les deux, ou si le load échoue partiellement, `getPages()` retourne `defaultPages` et un save subséquent écrase
- Logout/login transitoire pendant qu'un debounce `savePages` est en attente
- Init avec `apiEnabled = false` initial (ne devrait pas sauver, mais à vérifier)

**Diagnostic** : comparer `pages[].apps` vs `customApps` keys dans le JSON. Si `customApps` est plein mais `pages[main].apps = []` → écrasement.

**Récupération** :
1. Backup global : `/data/preferences.json.bak` (depuis migration 6 mars 2026)
2. Pour chaque user, récupérer depuis un autre user dont les prefs sont intactes (mohamed n'est jamais utilisé en prod, ses pages reflètent l'état post-migration) :
   ```python
   import json
   with open('/data/users/mohamed/preferences.json') as f: src = json.load(f)
   with open('/data/users/{user}/preferences.json') as f: dst = json.load(f)
   dst['pages'] = src['pages']  # garde terminalState, hiddenFolders, etc.
   with open('/data/users/{user}/preferences.json', 'w') as f: json.dump(dst, f, indent=2, ensure_ascii=False)
   ```
3. Recharger le launcher dans le navigateur

**Protection à implémenter** (TODO) : dans `update_pages()` côté serveur (`server.py` ligne ~556), refuser le payload si c'est `[{id:main, apps:[]}]` ET que l'utilisateur a des `customApps` non vides — c'est forcément un reset accidentel.

## Authentification

- **Users** : stockés dans `/data/users.json` avec hash bcrypt
- **Users par défaut** : `pierre` (admin, mdp `12345`), `mohamed` (user, mdp `12345`)
- **Cookie** : `cactus_session`, signé avec `/data/.secret_key`, HTTPOnly, SameSite=Lax, 7 jours
- **Routes publiques** : `/`, `/health`, `/api/auth/login`, `/api/auth/me`, `/api/auth/select-user`
- **Middleware** : `before_request` retourne 401 sur `/api/*` si pas de session
- **Réseau local (depuis 2026-06-11)** : plus d'auto-login global vers `pierre`. Sur le LAN (`LOCAL_SUBNET`), le 401 de `/api/auth/me` contient `{lan:true, users:[...]}` → le frontend affiche un **sélecteur de user** (un clic, pas de mot de passe, `POST /api/auth/select-user`). Hors LAN : login classique avec mot de passe. Le choix est mémorisé 7 jours par appareil (cookie).
- **Versionnement de session** : `SESSION_VERSION` (`session['v']`) — les sessions de l'ancien auto-login (sans `v`) sont invalidées au premier hit, chaque appareil repasse une fois par le sélecteur
- **Admin** : Pierre peut switcher vers un autre user pour voir/modifier ses données (`admin_view_as` en session)
- **Migration** : au premier démarrage, si `/data/preferences.json` existe et `/data/users/` n'existe pas, les données globales sont copiées vers chaque user puis renommées en `.bak`
- **Frontend** : login overlay glassmorphism (z-index 2000) en deux modes — sélecteur de user (LAN) / formulaire mot de passe (lien de bascule) ; fetch interceptor 401 avec compteur de 3 consécutifs ; menu user + admin switcher dans la top-bar ; chip user (initiale colorée + nom, clic → logout) dans la barre des onglets terminaux desktop et mobile

## Fonctionnalités principales

- **Raccourcis** : création avec nom, URL, icône (82+), couleur (16 gradients)
- **Auto-prefix URL** : ajoute `http://` si protocole manquant
- **Pages multiples** : organisation par pages, drag & drop. **Atterrissage par défaut sur la vue Terminaux** à l'ouverture (la page sauvegardée ne sert qu'à la navigation en cours de session)
- **Page partagée** : onglet « 📌 Partagé » visible par tous les users (stockage global `/data/shared_page.json`, objets app complets indépendants des customApps). Édition **admin only** : « Nouveau » sur la page, clic droit → supprimer, menu contextuel d'une app perso → « Copier vers Partagé »
- **Menu contextuel** : clic droit → modifier, déplacer, supprimer
- **Multi-utilisateur** : sélecteur de user sur le LAN (sans mot de passe) / login classique hors LAN, préférences isolées, admin peut voir les données des autres
- **Sync globale** : préférences partagées entre appareils (per-user)
- **Thème** : dark (défaut) / light toggle
- **Terminal Manager** : xterm.js + WebSocket, sessions dtach
- **Copie terminal = sélection-souris** : surligner du texte le copie automatiquement (`onSelectionChange` → `navigator.clipboard`, toast « Copié ! »), **pas de Ctrl+C** (interrompt) ni de Shift. ⚠️ Nécessite un **contexte sécurisé** (https, donc cert auto-signé OK sur le LAN). Depuis Claude Code ≥ 2.1.150 qui active le mouse tracking xterm, le flux WebSocket est filtré par `stripMouseTracking()` pour que xterm n'entre jamais en mode souris et que la sélection reste possible (voir « Session du 25 juin 2026 », v1.0.13)
- **Barre de touches tactile (iPhone/iPad)** : Esc, Tab, ⇧Tab, flèches, ^C sous le terminal sur écran tactile (`pointer: coarse`) — le clavier virtuel iOS n'a pas ces touches, indispensables pour répondre aux prompts interactifs de Claude Code. Envoi des séquences ANSI directement sur le WebSocket (`sendKeybarKey()`), flèches sensibles au mode DECCKM (`terminal.modes.applicationCursorKeysMode`). `pointerdown` + `preventDefault` pour ne pas voler le focus xterm (le clavier iOS reste ouvert). Test : `test_mobile_keybar.py`
- **Projets** : scan dynamique de /home/cactus/claude, gestion git intégrée
- **Git branches vs worktrees** : dans la liste des projets, l'expand affiche deux sections distinctes :
  - **Worktrees** (icône **W** verte) : branches checkout dans un dossier séparé (`projet--branche`), avec boutons Claude/Team/Supprimer
  - **Branches** (icône **B** violette) : branches locales non-worktree, avec bouton "↗ Worktree" pour les convertir
  - Les labels "WORKTREES" / "BRANCHES" n'apparaissent que si les deux types sont présents
  - `get_git_info()` retourne `worktrees[]` et `branches[]` (branches locales excluant celles déjà en worktree ou branche courante)
- **Origine des worktrees (users vs Claude)** : chaque worktree porte `origin` (`user`/`claude`) + `owner` (username). Badge **initiale du créateur** (P/M, couleur stable) ou **🤖** dans la sidebar, avertissement si un autre user ouvre le worktree. Voir la section dédiée ci-dessous.
- **Demandes ERP** : tickets avec notifications Telegram
- **Bug Report** : widget connecté au bugs_service local (http://192.168.1.200:9010), projet "Terminal Launcher" (slug: terminal-launcher, préfixe: TER)

## Origine des worktrees (users vs Claude)

Distingue les worktrees créés par un utilisateur (pierre, mohamed, …) de ceux créés par Claude (skills `night-watch`/`bugs-fix`/`release-loop` qui font `git worktree add` en terminal). **Depuis 2026-06-11, l'origine `user` porte aussi le `username` du créateur** : badge avec l'**initiale** du user (ex. **P** pour Pierre, couleur stable par user via `userColor()`) au lieu du 👤 générique, et **avertissement** (`confirm`) quand un autre user ouvre un terminal (boutons C/T) sur ce worktree : « Du travail est actuellement en cours par Pierre. Continuer quand même ? ». Helpers frontend : `worktreeOwnedByOther()`, `confirmWorktreeAccess()`.

**Pourquoi un marqueur explicite** : aucun signal git ne les distingue — même auteur de commit (`Cactusrad`, car Claude commit avec l'identité de Pierre), conventions de nommage de branche identiques (Pierre nomme aussi ses branches `feat/...`), tracking remote mélangé. Une heuristique de nommage a été testée puis abandonnée (3 erreurs sur 6 contre la vérité terrain).

**Deux sources de vérité, par priorité de lecture** :
1. **Marqueur in-tree** `.cactus-worktree.json` (`{"creator":"user"|"claude", "username":"pierre"}`) écrit **dans le worktree**. Ajouté à l'`info/exclude` du worktree → invisible dans `git status`. Avantage : voyage avec le dossier, survit sur n'importe quelle install (ex. `.100` où le registre démarre vide).
2. **Registre central** `/data/worktree_origins.json` (volume `launcher-data`), clé = `dirname`, valeur `{"origin":"user"|"claude","username":...}` (les anciennes valeurs string restent lisibles via `normalize_origin_entry()`).
3. **Défaut** : `claude` (tout ce qui n'est ni marqué ni dans le registre = créé hors dashboard).

**Helpers `server.py`** : `load/set/forget_worktree_origin()`, `read/write_worktree_marker()`, `guess_worktree_origin(dirname, origins)`, `normalize_origin_entry()`. `get_git_info()` expose par worktree : `origin`, `owner` (username) et `owner_display`.

**Règle de fonctionnement** :
- Worktree créé via le bouton **« + Nouveau worktree »** du dashboard → marqué `user` **au nom du user connecté** (marqueur in-tree + registre).
- Worktree créé par Claude en terminal → pas marqué → `claude` par défaut.
- 100% fiable tant que les worktrees perso passent par le bouton.

**UI (`index.html`)** :
- Badge par worktree, **cliquable** → bascule l'origine (`toggleWorktreeOrigin()` → `POST .../origin`) : **initiale du créateur** (couleur `userColor(username)`, tooltip « Créé par X ») pour `origin=user`, **🤖** pour `origin=claude`. Re-cliquer un 🤖 le revendique au nom du user connecté. Sert à corriger/reclasser, notamment les worktrees créés hors dashboard.
- Bouton **🤖** dans l'en-tête du panneau projets (`toggleHideClaudeWorktrees()`) → masque/affiche les worktrees `origin=claude`. État en `localStorage` (`hideClaudeWorktrees`, UI state pur navigateur, autorisé).

**Retro-tag manuel** (données runtime, pas de divergence git — markers exclus, registre dans le volume) : écrire `.cactus-worktree.json` dans chaque worktree + `info/exclude`, et/ou éditer le registre via `docker exec terminal-launcher`. La sidebar ne rend plus les branches standalone (seulement les worktrees), donc le masquage couvre tout l'affiché.

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
├── server.py              # Flask backend + API REST + auth (~1200 lignes)
├── test_multiuser.py      # Assertions multi-user / page partagée / owner worktree (lancer après rebuild)
├── test_mobile_keybar.py  # Assertions barre de touches tactile iPhone/iPad (WebKit) — se logge en mohamed, jamais pierre
├── config.py              # Configuration centralisée (dotenv, Path, SECRET_KEY, USERS_*)
├── index.html             # Frontend complet (~300KB, inclut login overlay + auth JS)
├── requirements.txt       # flask, flask-cors, gunicorn, requests, python-dotenv, aiohttp, bcrypt
├── Dockerfile             # Python 3.11-slim, gunicorn, healthcheck
├── docker-compose.yml     # Port 80 + nginx (443), volume launcher-data
├── nginx.conf             # Reverse-proxy : 80→301 HTTPS, vhost terminal.sharpi.ca, 443 SSL
├── certs/                 # Certs self-signed nginx (gitignorés depuis l'audit d'avril)
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
- **Déploiement (tag-based, depuis 2026-05-07)** : dev sur `.200` (`~/claude/terminal-launcher/`), prod sur `.100` (`~/terminal-launcher/`). **Workflow** : commit & push librement sur `.200` (branche au choix) ; pour mettre en prod, créer un tag `vX.Y.Z` et `git push --tags`. Le timer user `terminal-launcher-autosync.timer` (toutes les 2 min sur `.200`) détecte le nouveau tag, SSH sur `.100`, checkout du tag, rebuild, redeploy. Tant qu'il n'y a pas de nouveau tag, **rien ne part en prod** — fini les rebuilds à chaque commit. Script : `~/.local/bin/terminal-launcher-autosync.sh`. État courant tracké dans `/home/cactus/terminal-launcher/VERSION` sur `.100`. **Jamais d'edit direct sur `.100`** (ni `ssh ... sed`, ni `docker cp`, ni SCP) — ça crée une divergence entre prod et Git.
- **Topologie `main` vs `master` (constat 2026-06-11, remplace la note d'avril)** : depuis l'autosync tag-based, `.100` tourne en **HEAD détaché sur les tags `vX.Y.Z` créés depuis `master`** (vérifié : v1.0.7 = `c42ebdd`), donc avec nginx + HTTPS + multi-user auth, exactement comme `.200`. `PORT=180` dans l'`.env` de `.100` → nginx HTTP sur 180 (301 vers HTTPS), app servie sur 443. La branche **`main` est gelée depuis avril 2026** (`daab27f`) et ne reflète plus la prod : ne plus cherry-pick vers `main` — releaser = commiter sur `master` + tagger.
- **Déploiement indépendant** : chaque install (`.100`, `.200`) est autonome. Les projets sont scannés depuis le volume local `/home/cactus/claude` monté dans le conteneur, pas via le terminal-server distant.
- **Remote git sur `.100`** : `git@github.com:Cactusrad/terminal-launcher.git` (SSH via `~/.ssh/github_key`). `.100` utilisait HTTPS au départ, basculé en SSH le 24 avril 2026 pour permettre les `git push` sans prompt credentials.
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

## Session du 24 avril 2026

**BUG-152 : nom des worktrees dans la sidebar ≠ nom des onglets**

Cause : la sidebar affichait `wt.branch` (ex. `fix/demande-par-dropdown-clipping`) alors que l'onglet terminal affichait `tab.name = wt.dirname` (ex. `cactus_erp--quote`). Deux conventions de nommage pour la même ressource.

Fix : `index.html:5985` — la sidebar affiche `wt.dirname` dans le texte principal, le nom de branche git reste disponible dans le tooltip `title="dirname — branche: <branch>"`. Sidebar = onglet, au caractère près. Commit `c5b7565` sur `master`, reporté dans `955338e` sur `main`.

**feat: detect default branch (main/master)**

Nouveau champ `default_branch` dans `get_git_info()` (`server.py`), détecté via `symbolic-ref refs/remotes/origin/HEAD` puis fallback `main` / `master`. Utilisé pour :
- calcul `behind_main` des worktrees et branches (au lieu de la branche courante)
- détection `merged` des branches
- badge "défaut" et masquage du bouton supprimer sur la branche par défaut dans la sidebar

Commit `7e229a6` sur `master` uniquement (pas sur `main` — .100 reste sans cette feature tant que `main` n'est pas mergé).

**Nettoyage du working tree sur `.100`**

`.100` avait 6 fichiers non commités (HOST_IP required, TODO.md, index.html avec la BUG-152 appliquée en in-place edit) — capturés dans le commit `955338e` sur `main`. Le remote est passé de HTTPS à SSH pour permettre le push. Working tree de `.100` maintenant propre et aligné avec `origin/main`.

**BUG-153 : préfixe du projet parent redondant dans les noms de worktree**

Suite de BUG-152. Comme la sidebar affichait maintenant le dirname complet (`cactus_erp--command`, `cactus_erp--chatwoot`, etc.), le préfixe `cactus_erp--` devenait redondant visuellement — les worktrees sont déjà groupés sous leur projet parent dans l'arborescence.

Fix : nouveau helper `worktreeDisplayName(dirname)` dans `index.html` qui split sur le premier `--` et renvoie le suffixe. Appliqué à 4 endroits :
- `index.html:5985` (sidebar worktree item — tooltip conserve le dirname complet + branche)
- `index.html:5339` (`createTerminalTab` → `tab.name`)
- `index.html:5375` (`createTeamTerminal` → `tab.name`)
- `index.html:6564` (auto-discovery dtach → `tab.name`)

Parité sidebar ↔ onglet terminal (contrainte de BUG-152) préservée : les deux affichent le nom court. `tab.project` reste le dirname complet (identifiant fonctionnel utilisé par le backend pour `cd`). Les onglets déjà ouverts gardent leur ancien nom long — le sync `syncTerminalTabs()` merge par `tmuxSession` sans écraser `tab.name` existant, il faut close/reopen pour appliquer.

Commit `4e3f75e` sur `master`, cherry-pick `e651aa3` sur `main` (.100).

**BUG-154 : onglet du projet principal affiche la branche checked-out au lieu de la default**

Les onglets de projet régulier (non-worktree) affichaient `gitInfo.branch` (checkout courant) — instable quand le dossier principal est sur une feature branch. Résultat : `terminal-launcher` montrait "master" (vert) mais `cactus_erp` montrait "fix/mcmaster-l" (bleu) car le dossier principal de cactus_erp était checkout sur cette branche.

Fix : `getTabBranchBadge()` (`index.html:5858`) utilise désormais `gitInfo.default_branch || gitInfo.branch`. Les onglets de projet régulier affichent toujours la branche par défaut du repo (stable, vert "main"/"master"). Les onglets worktree (`project--branch`) sont inchangés — ils affichent leur branche spécifique.

Commit `7ff129c` sur `master`, cherry-pick `f528b6d` sur `main`.

**Backport : infrastructure git sur `.100/main`**

Découvert que BUG-153/154 étaient inactifs sur `.100` — le backend `server.py` n'émettait aucune info git (le payload `/api/projects/folders?git=1` renvoyait juste des strings sans `branch`/`worktrees`/`default_branch`). Backport surgical depuis master :

- `Dockerfile` : ajout `git + openssh-client`, config SSH (`IdentityFile /root/.ssh/github_key`, `StrictHostKeyChecking accept-new`), `git config --global safe.directory='*'`
- `config.py` : variable `GITHUB_USER` (défaut `Cactusrad`)
- `docker-compose.yml` : montage `~/.ssh/github_key` et `known_hosts` du host dans `/root/.ssh/` du conteneur (ro)
- `server.py` : import `subprocess`, bloc de 6 helpers git (`get_project_path`, `is_git_repo`, `run_git`, `get_main_project`, `sanitize_branch_for_dirname`, `detect_default_branch`), fonction `get_git_info()` (branche, default_branch, dirty, worktrees avec behind_main, branches locales avec merged/behind_main), support `?git=1` sur `/api/projects/folders` (avec grouping des worktrees), 8 endpoints git (`/status`, `/branches` GET, `/branches/<b>` DELETE, `/worktrees` GET/POST, `/worktrees/<d>` DELETE, `/remotes`, `/link`)

**Explicitement non backporté** : multi-user auth (`bcrypt`, `SECRET_KEY`, `USERS_*`, `users.json`), nginx reverse-proxy + HTTPS, détection LAN auto-login. `main` reste single-user port 180 direct. La topologie divergente master/main persiste donc, mais réduite à : auth + nginx/HTTPS seulement.

Commit `2de40df` sur `main` uniquement.

**Audit sécurité — repo public Cactusrad/terminal-launcher**

Vérification après le travail ci-dessus :

1. **🔴 Telegram bot token fuité dans l'historique git** (commit `701b6213`) : `TELEGRAM_BOT_TOKEN="8559016458:AAFZJLQO_Mm3ew-L9nbmWWTwOOManjbcszc"` hardcodé dans `server.py` avant d'être migré vers `.env`. Bot compromis = `Cactus-vm-server` (@CactusMainBot). **Résolu** : ancien token révoqué via BotFather (confirmé `401 Unauthorized`), nouveau token `8559016458:AAE7sS5AFM85rNCUn-U3FoeKtPLIQaD-w3A` dans `.env` sur `.200`, conteneur redémarré, message test envoyé. `.100` n'avait pas Telegram configuré.

2. **🟠 Certs HTTPS auto-signés committés** (`certs/cert.pem`, `certs/key.pem`) : clé privée RSA 4096 visible dans l'historique. Risque limité (cert self-signed "Cactus Home" pour usage LAN uniquement, valide 2026→2036). **Résolu** : régénéré via openssl (nouveau fingerprint SHA1 `89:9A:16:DA:...`, valide jusqu'en 2036), ajouté `certs/*.pem` à `.gitignore`, `git rm --cached`, nginx redémarré. L'ancienne clé dans l'historique est désormais inutile car `.200` sert le nouveau cert.

3. **🟢 `BUGS_API_KEY` retirée de `index.html` — résolu par proxy serveur + cactus-secrets** (voir section suivante).

4. **🟡 Mots de passe par défaut `12345`** pour `pierre` (admin) et `mohamed` dans `server.py:117,124` (seed au premier démarrage) : impact uniquement si quelqu'un déploie tel quel avec auth activée sans changer les mdp. Acceptable pour un homelab, à documenter dans le README si on en crée un.

**Migration vers cactus-secrets (coffre-fort centralisé)**

Ajout d'un client `cactus_secrets_client.py` (88 lignes, copié depuis `/home/cactus/claude/cactus-secrets/clients/python/`) et refactor de la gestion des secrets runtime :

- Nouveau namespace `launcher` dans cactus-secrets (sur `.100:9020`) avec trois clés : `bugs_api_key`, `telegram_bot_token`, `telegram_chat_id`
- Deux tokens scopés `read:launcher/*` : `launcher-200` et `launcher-100`, un par machine (rotation indépendante)
- `server.py` : bloc `# ============ Cactus Secrets client ============`, helper `secret_or_env(namespace, key, env_fallback)` qui lit depuis cactus-secrets avec cache 5 min, fallback sur la variable d'env si client non initialisé ou read en échec
- `send_telegram()` : fetch `launcher/telegram_bot_token` + `launcher/telegram_chat_id` au lieu des env vars
- Deux nouveaux endpoints `/api/bugs/issues` (POST) et `/api/bugs/issues/<ref>/attachments` (POST) qui proxy vers `BUGS_API_URL` avec la clé `launcher/bugs_api_key` côté backend
- `index.html` : `BUGS_API_KEY` constante supprimée, `BUGS_API_URL` pointe sur `/api/bugs` (relatif), plus aucune clé envoyée au navigateur. Auth: `/api/bugs/*` suit le middleware standard (auto-login LAN sur `.200`, libre sur `.100`).
- `docker-compose.yml` : nouvelles env vars `SECRETS_URL` et `SECRETS_TOKEN` passées au container
- `Dockerfile` : `COPY cactus_secrets_client.py .` dans le build
- `.env` : ne contient plus aucun secret applicatif — seul `SECRETS_TOKEN` reste, scopé read-only, révocable indépendamment depuis cactus-secrets sans toucher au code ni aux apps

**Rotation des secrets** : `PUT /secrets/launcher/<key>` côté cactus-secrets avec le bootstrap admin token, cache invalidé en ~5 min sur les backends, zero redéploiement.

Commits : `3283eb9` (master), cherry-pick `daab27f` (main), `a6d154f` (docs `.env.example`).

## Session du 8 juin 2026

**Origine des worktrees (toi vs Claude)** — voir la section dédiée plus haut pour le mécanisme complet.

Contexte : le workflow récent de Claude (skills lancés en `/loop`) crée une branche nommée par tâche dans des worktrees `projet--slug`, d'où la confusion « qui a créé ce worktree ». Aucun signal git ne les distingue (auteur `Cactusrad` partagé, branches `feat/...` des deux côtés). Heuristique de nommage testée puis abandonnée → marqueur explicite.

Livré en 4 releases tag-based (déployées sur `.100` via autosync) :
- **v1.0.2** : champ `origin` dans `get_git_info()` + badge 👤/🤖 sidebar (registre central `/data/worktree_origins.json`)
- **v1.0.3** : marqueur portable `.cactus-worktree.json` écrit dans le worktree à la création (+ ajout à `info/exclude` → git status propre)
- **v1.0.4** : badge cliquable → `POST .../git/worktrees/<dir>/origin` (`toggleWorktreeOrigin`)
- **v1.0.5** : bouton 🤖 dans l'en-tête pour masquer les worktrees `origin=claude` (`hideClaudeWorktrees` en localStorage)

Retro-tag des worktrees existants sur `.200` : `fix/fix3/hook/partz/kestion` = toi, `nordsku/demande-id` = Claude (vérité terrain donnée par Pierre). `.100` n'a aucun worktree → rien à reclasser.

Découverte au passage : **la sidebar ne rend plus les branches standalone** (retirées dans `37d7d23` « collapsible projects sidebar, remove agents panel »), seulement les worktrees.

## Session du 11 juin 2026

**Multi-user réel + worktrees nominatifs + page partagée** — commit `c42ebdd` sur `master`, release **v1.0.7** déployée sur `.100` via autosync (health 200, HEAD détaché sur le tag). Constat au passage : `.100` déploie les tags de `master` depuis mai — la note « topologie divergente » d'avril est remplacée (voir Notes importantes), `main` est gelée.

1. **Fin de l'auto-login global** : tous les appareils LAN devenaient `pierre` (admin). Remplacé par un **sélecteur de user sans mot de passe** sur le LAN (overlay « Qui es-tu ? », un clic par user, lien « Connexion avec mot de passe » en secours). `SESSION_VERSION=2` invalide les anciennes sessions auto-login. Bouton/chip user (initiale colorée + nom) dans la barre des onglets terminaux (desktop + mobile) → confirm → logout.
2. **Worktrees au nom du créateur** : origine `user` enrichie du `username` (marqueur in-tree + registre, rétro-compatible). Badge initiale (P/M) coloré, tooltip nominatif, et confirm « Du travail est actuellement en cours par X » quand un autre user clique C/T sur le worktree. Rétro-tag effectué sur `.200` : tous les anciens `user` → `pierre`.
3. **Atterrissage par défaut sur la vue Terminaux** : à l'ouverture (et après login), `initDashboard()` force `currentPageId='terminals'` — la page sauvegardée ne sert que pour la navigation en cours de session.
4. **Page partagée** : onglet « 📌 Partagé » visible par tous (`/data/shared_page.json`, objets app complets, indépendant des users). Édition admin only : création via « Nouveau » sur la page, clic droit → suppression, menu contextuel d'une app perso → « Copier vers Partagé ».

**Documentation de l'accès distant `terminal.sharpi.ca`** (en place depuis ~5 juin, voir la section « Accès distant » plus haut). Le vhost nginx (`nginx.conf`) et le script keepalive (`/home/cactus/scripts/terminal-tunnel-keepalive.sh`, hors repo) existaient mais n'étaient pas documentés. ⚠️ Au 11 juin, la modif `nginx.conf` (vhost `terminal.sharpi.ca`) est **non commitée** sur `.200` — à committer pour qu'un futur tag ne la perde pas.

**Barre de touches tactile iPhone/iPad** (bug rapporté par Pierre : Esc/Tab/flèches impossibles depuis iOS → coincé quand Claude pose une question dans le terminal). Ajout dans `index.html` :
- Barre `#terminalKeybar` (Esc, ⇥, ⇧⇥, ↑ ↓ ← →, ^C) sous le terminal, visible uniquement en `@media (hover: none) and (pointer: coarse)` (couvre iPhone ET iPad, y compris iPad en mode desktop > 768px) ; masquée sur desktop souris
- `sendKeybarKey()` envoie la séquence sur le `ws` du terminal actif (`terminalInstances.get(activeTerminalTabId)`) ; flèches en `\x1bO?` si DECCKM actif, sinon `\x1b[?`
- Listener `pointerdown` + `preventDefault` : ne vole pas le focus du textarea xterm → le clavier iOS ne se referme pas entre deux touches
- `--keybar-h: 49px` soustrait du calc de hauteur mobile du `.terminal-container` ; `setViewportHeight()` utilise désormais `visualViewport.height` (suit l'ouverture du clavier iOS, garde la barre visible au-dessus)

Vérifié par `test_mobile_keybar.py` (10/10) : AVANT sur prod `.100` la barre est absente ; APRÈS sur `.200` en WebKit iPhone 14, chaque touche tapée arrive au PTY, prouvé par `cat -vt` (`^[`, `^I`, `^[[A`, `^[[Z`, `^C` interrompt) ; visible sur iPad gen 7 ; masquée en Chromium desktop. Limite : l'émulation ne simule pas le clavier virtuel iOS réel — comportement clavier ouvert à valider une fois sur appareil réel.

**Incident : terminaux qui réouvrent tout seuls (sharpi, 16:25–16:42)** — causé par les tests Playwright de cette session, loggés en `pierre`. Mécanisme (trois rouages, tous confirmés dans les logs terminal-server) :
1. Au chargement de page, l'app restaure **tous** les onglets du `terminalState` du user **sans vérifier que la session dtach existe** (`syncTabsWithActiveSessions` : « *Don't filter by dtach status - terminal-server creates sessions on demand* ») → la connexion WS fait recréer la session **et relancer `claude`** côté terminal-server.
2. L'auto-discovery (`syncTerminalTabs` 4c) recrée l'onglet sur tous les appareils dès qu'une session vit, et le smart-save union le réécrit dans le state.
3. Un onglet n'est retiré du state que si la session est morte **ET** absente du state serveur (4b) → un onglet mort dans le state est une mine : chaque page load le respawne.

Donc : Pierre tue `claude_sharpi` → un login frais (test Playwright, autre appareil, reload) la respawne → ses navigateurs la redécouvrent en ≤5s. Preuve : `Created dtach session: claude_sharpi` à 16:41:49 avec UA `HeadlessChrome/143` (Playwright).

**Règles tirées de l'incident** :
- **Tests E2E : se logger en `mohamed`, jamais en `pierre`** (son `terminalState` a été vidé — c'étaient 11 onglets fantômes de la migration, eux-mêmes des mines à respawn ; ses `pages` de référence sont intactes)
- Nettoyage fait : session `claude_sharpi` tuée, onglet retiré du state de pierre
- **~~TODO (fix structurel à discuter)~~ → CORRIGÉ le 25 juin 2026 (v1.0.12)** : au page load, les onglets dont la session dtach est morte sont rendus « endormis » (placeholder + badge 💤, aucun WebSocket) et ne respawn qu'au clic. Voir la section « Session du 25 juin 2026 »

**Fix : bouton « Accueil » mobile cassé** — `goToHome()` appelait `switchPage('main')`, fonction inexistante (reste d'un ancien nom avant refactor) → `ReferenceError`, le bouton 🏠 de la barre mobile ne faisait rien. Fix d'une ligne : `setCurrentPageId('main')` (la fonction utilisée partout ailleurs pour changer de page). Vérifié : `page.evaluate('goToHome()')` levait `ReferenceError` avant, passe après (+ tap réel du `.mobile-home-btn` en WebKit iPhone 14 : retour dashboard, `currentPageId=main`, 0 erreur). Touche aussi prod `.100` — corrigé là-bas au prochain tag.

Vérifié par 27 assertions (`test_multiuser.py` + Playwright) : avant le fix `/api/auth/me` sans cookie → 200 pierre ; après → 401 + sélecteur, session par user, 403 hors LAN, shared page admin-only, owner de worktree de bout en bout (badge + avertissement + refus = pas de terminal).

## Session du 25 juin 2026

**v1.0.12 — fix structurel du respawn des terminaux** (clôt le TODO de l'incident du 11 juin « terminaux qui réouvrent tout seuls »). Commit `3658257` sur `master`, tag `v1.0.12` déployé sur `.100` via autosync (version `v1.0.12`, health 200, code servi confirmé).

**Le bug** : au chargement de page, `initTerminalManager` faisait `terminalTabs.forEach(tab => loadTerminal(tab))` — il reconnectait le WebSocket de **chaque** onglet sauvegardé sans vérifier que sa session dtach vivait encore. Le terminal-server recrée la session à la demande à l'ouverture du WS → relance `claude` → respawn fantôme à chaque page load.

**Le fix** (frontend, `index.html` uniquement) :
- Nouveau Set `dormantTabs` (déclaré près de `disposedTabs`/`disposedSessions`).
- `initTerminalManager` interroge d'abord les sessions dtach vivantes (`/terminal-api/sessions` en HTTPS, sinon `host:7681/sessions`) → `activeSessionNames`. Chaque onglet est chargé via `loadTerminal(tab, { dormant: !alive })`.
- `loadTerminal(tab, opts)` : si `dormant`, construit le pane (div + grid header + position) mais **aucun xterm ni WebSocket** — un placeholder « Session endormie » (bouton « Réveiller ») est injecté, et le tab est ajouté à `dormantTabs`. Sinon, chemin xterm/WS classique **inchangé** (zéro régression sur les sessions vivantes).
- `wakeTerminal(tabId)` : seul chemin qui (re)lance une session morte — retire le placeholder, `dormantTabs.delete`, `loadTerminal(tab)` normal. Toujours déclenché par une action explicite.
- `activateTerminalTab(tabId, opts)` : réveille un onglet dormant à l'activation, **sauf** `{ wake: false }` — utilisé par l'activation initiale au page load pour ne PAS respawn la session active morte.
- `syncTerminalTabs` (étape « 4-pre ») : réveille auto un onglet dormant si sa session **redevient vivante** ailleurs (démarrée sur un autre appareil) — ce n'est pas un respawn, la session existe déjà.
- `disposeTerminal` nettoie aussi `dormantTabs`.
- UI : badge 💤 dans la barre d'onglets (`.tab-dormant`, onglet `.dormant` au nom estompé), placeholder centré dans le pane (visible aussi en vue grille).

**Vérifié** par `test_dormant_terminals.py` (7/7). Méthode hermétique : `window.WebSocket` est remplacé par un stub qui **enregistre** l'URL de chaque tentative de connexion sans jamais ouvrir de vraie socket → **aucune vraie session créée**, même contre le vieux code de `.100`. `/api/terminal/state` mocké (un onglet sur une fausse session morte) + endpoint sessions vide. AVANT sur `.100` (vieux code) : un WS part vers la session morte au load (`ws=1`, respawn). APRÈS sur `.200` : `ws=0` au load, onglet `dormant` + badge + placeholder ; clic → `ws=1` (réveil intentionnel) + sortie de `dormantTabs`.

**v1.0.13 — fix copie-par-sélection cassée par le mouse tracking de Claude Code** (rapporté par Pierre : « je ne suis plus en mesure de copier, ni avec Shift ni Ctrl+C, depuis le changement de mode souris de Claude Code »). Commit `f36aea6` sur `master`, tag `v1.0.13` déployé sur `.100` via autosync (fix présent, health 200).

**Le bug** : Claude Code **≥ 2.1.150** (juin 2026) active le *mouse tracking* xterm dans son TUI classique (séquences `CSI ? 1000/1002/1003/1006 h`). Comme Claude tourne sur le PTY Linux de `.200`/`.100` (l'exception Windows-console de la v2.1.181 ne s'applique pas), xterm.js se met à **transmettre le glisser-souris à l'appli au lieu de sélectionner du texte** → l'auto-copie sur sélection (`onSelectionChange`, `index.html:~5834`) ne se déclenche plus. **Aucun interrupteur en mode classique** côté Claude Code (issues GitHub #61936/#23581/#27995 non résolues) ; `CLAUDE_CODE_DISABLE_MOUSE=1` n'agit qu'en plein écran (`CLAUDE_CODE_NO_FLICKER=1`) — écarté car le plein écran repeint l'écran en boucle et risquait de casser la détection d'attente ⏳ (`check_terminal_activity`, `server.py:~1719`, qui lit le log `script`) et le scrollback xterm.

**Le fix** (frontend, `index.html` uniquement — Claude reste en mode classique) :
- Helper global `stripMouseTracking(text)` + `MOUSE_TRACKING_MODES` (Set `1000,1001,1002,1003,1005,1006,1015,1016`), déclarés juste après `XTERM_OPTIONS`.
- Retire les modes souris des séquences DEC privées `CSI ? p1;p2;… (h|l)` via regex, **en préservant les autres params** de la même séquence (ex. `?1000;1006h` → supprimé, `?2004h` bracketed paste → intact, `?25h` curseur → intact).
- Appliqué dans `ws.onmessage` : `stripMouseTracking(new TextDecoder().decode(event.data))` avant `terminal.write`. xterm n'entre jamais en mode souris → sélection-glisser + auto-copie « Copié ! » refonctionnent **sans Shift**.

**Vérifié** par assertion hermétique (Playwright + vrai xterm.js 5.5.0, pas de session réelle) : on écrit la séquence d'activation souris dans un `Terminal`, on lit `terminal.modes.mouseTrackingMode`. AVANT (flux brut) → `'any'` (souris active, drag vole la sélection). APRÈS (flux filtré) → `'none'` (sélection restaurée). Non-régression : `bracketedPasteMode` toujours actif après filtrage.

## Session du 9 juin 2026

**v1.0.6 — visibilité des boutons d'onglets terminaux**

Les boutons d'action des onglets (rafraîchir `.tab-refresh`, tuer `.tab-kill`, fermer `.tab-close` dans `index.html`) étaient quasi invisibles : `.tab-refresh`/`.tab-kill` en `opacity:0` (cachés sauf survol de l'onglet), les 3 en `--cactus-text-muted` (#555566, ~2:1, sous WCAG).

Fix CSS :
- couleur de base `--cactus-text-muted` → `--cactus-text-secondary` (#8a8a9a, ~4.3:1)
- `.tab-refresh`/`.tab-kill` : `opacity:0` → `0.5` au repos, `1` au survol de l'onglet (découvrables sans cacher)
- boutons 18 → 20px, icône kill svg 11 → 13px, override mobile `.tab-close` aligné (20px)
- feedback survol bouton renforcé (fond bleu `0,101,255` refresh / rouge `222,53,11` kill+close, alpha 0.35)

Vérifié par screenshots Playwright avant/après (`/app-team-test` scopé à un fix CSS ciblé plutôt que la team de 6 agents) + mesure couleur computed (`rgb(138,138,154)`).
