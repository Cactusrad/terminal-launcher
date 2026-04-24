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
| `/api/projects/folders` | GET | Dossiers dans /home/cactus/claude (scan local du volume monté). `?git=1` enrichit avec branches + worktrees |
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
- **Projets** : scan dynamique de /home/cactus/claude, gestion git intégrée
- **Git branches vs worktrees** : dans la liste des projets, l'expand affiche deux sections distinctes :
  - **Worktrees** (icône **W** verte) : branches checkout dans un dossier séparé (`projet--branche`), avec boutons Claude/Team/Supprimer
  - **Branches** (icône **B** violette) : branches locales non-worktree, avec bouton "↗ Worktree" pour les convertir
  - Les labels "WORKTREES" / "BRANCHES" n'apparaissent que si les deux types sont présents
  - `get_git_info()` retourne `worktrees[]` et `branches[]` (branches locales excluant celles déjà en worktree ou branche courante)
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
- **Déploiement** : dev sur `.200` (`~/claude/terminal-launcher/`, branche `master`), prod sur `.100` (`~/terminal-launcher/`, branche `main`). **Règle** : toute modif part de `.200` → commit → push → `git pull` sur `.100` → `docker compose build && docker compose up -d --force-recreate`. **Jamais d'edit direct sur `.100`** (ni `ssh ... sed`, ni `docker cp`, ni SCP d'un fichier isolé) — ça crée une divergence entre prod et Git.
- **Topologie divergente entre `main` et `master`** : `main` (prod `.100`) expose le port 180 en direct (`PORT=180` dans `.env`), pas d'HTTPS, pas de multi-user auth. `master` (dev `.200`) ajoute nginx reverse-proxy + HTTPS (certs dans `./certs/`), multi-user auth avec `SECRET_KEY`, détection default_branch. Un merge `master` → `main` nécessiterait de provisionner nginx + certs + `SECRET_KEY` sur `.100` avant rebuild — pas fait, réconciliation à planifier séparément.
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

3. **🟠 `BUGS_API_KEY` hardcodée dans `index.html:8446`** (`TER_7cd1...`) : **risque connu accepté**. La clé est de toute façon visible dans le DevTools de tout utilisateur légitime du launcher. Le repo public n'ajoute pas significativement à l'exposition. L'attaque nécessite en plus un accès au LAN (`192.168.1.200:9010`) → exposition effective très limitée. Pour éliminer complètement : soit rendre le repo privé, soit migrer vers un proxy serveur dans `terminal-launcher` (frontend appelle `/api/bugs/*` du launcher, qui relay vers le bugs service avec la clé côté backend).

4. **🟡 Mots de passe par défaut `12345`** pour `pierre` (admin) et `mohamed` dans `server.py:117,124` (seed au premier démarrage) : impact uniquement si quelqu'un déploie tel quel avec auth activée sans changer les mdp. Acceptable pour un homelab, à documenter dans le README si on en crée un.
