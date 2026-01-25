# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Résumé

Homepage personnalisée "Cactus Home Server" - Dashboard de lancement pour serveur homelab avec persistance globale des préférences.

**URL** : http://192.168.1.200:1000 (port 1000)

## Architecture

```
┌─────────────────┐     ┌──────────────────────────────────┐
│   Navigateur    │────▶│     Conteneur Docker (Flask)     │
│                 │◀────│                                  │
└─────────────────┘     │  ┌────────────┐  ┌────────────┐ │
                        │  │ index.html │  │ server.py  │ │
                        │  └────────────┘  └─────┬──────┘ │
                        │                        │        │
                        │              ┌─────────▼──────┐ │
                        │              │ /data/         │ │
                        │              │ preferences.json│ │
                        │              └────────────────┘ │
                        └──────────────────────────────────┘
                                         │
                                  Volume Docker
                               (homepage-data)
```

## Stack technique

**Backend :**
- **Python 3.11** avec Flask 3.0
- **Gunicorn** pour la production (2 workers)
- **Flask-CORS** pour les requêtes cross-origin

**Frontend :**
- **HTML5** (fichier unique)
- **CSS3** vanilla (pas de framework)
- **JavaScript** vanilla (pas de dépendances)
- **SVG inline** pour les icônes

**Infrastructure :**
- **Docker** avec volume persistant
- **API REST** pour la synchronisation des préférences

**Design** :
- Thème sombre avec gradient bleu foncé
- Effet glassmorphism sur les cartes
- Police système (`-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto`)

## API REST

| Endpoint | Méthode | Description |
|----------|---------|-------------|
| `/` | GET | Page principale HTML |
| `/health` | GET | Health check |
| `/api/preferences` | GET | Récupère toutes les préférences |
| `/api/preferences` | POST | Met à jour toutes les préférences |
| `/api/preferences/pages` | POST | Met à jour les pages uniquement |
| `/api/preferences/current-page` | POST | Met à jour la page courante |
| `/api/projects/folders` | GET | Liste les dossiers dans /home/cactus/claude |
| `/api/projects/hidden` | POST | Met à jour la liste des dossiers cachés |
| `/api/erp/requests` | GET | Liste les demandes ERP |
| `/api/erp/requests` | POST | Ajoute une demande ERP (+ notification Telegram) |
| `/api/erp/requests/<id>` | PATCH | Met à jour une demande ERP |
| `/api/erp/requests/<id>` | DELETE | Supprime une demande ERP |
| `/api/terminal/activity` | GET | Vérifie si les terminaux attendent une entrée |
| `/api/terminal/sessions` | GET | Liste les sessions dtach actives |

**Format des préférences :**
```json
{
  "pages": [
    { "id": "main", "name": "Accueil", "apps": ["ha", "grafana", ...] },
    { "id": "terminals", "name": "Terminaux", "apps": ["terminal", "claude", ...] }
  ],
  "currentPage": "main"
}
```

## Services listés

| Service | Port | Description |
|---------|------|-------------|
| Home Assistant | 8123 | Domotique et automatisation |
| Grafana | 3000 | Dashboards et monitoring |
| Portainer | 9443 | Gestion conteneurs Docker (HTTPS) |
| InfluxDB | 8086 | Base de données temporelles |
| Thermostats Neviweb | - | Dashboard Grafana spécifique |
| n8n | 5678 | Automatisation workflows |
| Claude Notify Config | 5003 | Configuration notifications push |
| MCP Manager | 3456 | Gestionnaire serveurs MCP |
| Serial Numbers | 8000 | Base de données numéros de série |
| Soumission Opermax | 5002 | Générateur de soumissions |
| Trading Bot | 8080 | Grid Trading Binance |
| Guillevin Prix | 5050 | Gestion des prix fournisseurs |
| Terminal | 7680 | Terminal Bash web (dtach) |
| Claude Terminal | 7681 | Terminal web Claude Code (dtach) |
| Sudo Claude Terminal | 7682 | Terminal web sudo Claude (dtach) |

## Persistance

**Synchronisation globale (serveur) :**
- Les préférences sont stockées dans `/data/preferences.json` (volume Docker)
- Toutes les machines partagent la même configuration
- Synchronisation automatique avec debounce (500ms)

**Fallback local :**
- Si l'API n'est pas disponible, utilisation du localStorage
- Indicateur visuel dans le footer : "Sync serveur" ou "Local uniquement"

| Clé localStorage | Contenu |
|------------------|---------|
| `cactusPages` | Backup local des pages |
| `cactusCurrentPage` | Page courante |

## Fonctionnalités

| Fonctionnalité | Description |
|----------------|-------------|
| **Pages multiples** | Organisation des apps en pages séparées |
| **Drag & Drop** | Réorganisation des cartes par glisser-déposer |
| **Menu contextuel** | Clic droit pour déplacer une app vers une autre page |
| **Sync globale** | Préférences partagées entre tous les appareils |
| **Admin** | Interface d'administration pour gérer pages et apps |
| **Reset** | Réinitialisation complète (local + serveur) |
| **Vue Projet** | Interface dédiée avec terminal, issues et tâches agents |
| **Terminal Manager** | Gestionnaire de terminaux avec onglets et sessions dtach |
| **Projets dynamiques** | Scan automatique des dossiers /home/cactus/claude |
| **Gestion projets cachés** | Modal ⚙ pour masquer/afficher des projets |
| **Demandes ERP** | Système de tickets avec notifications Telegram |
| **Bug Report** | Widget de signalement connecté à bugs.sharpi.ca |

## Page Projets

La page "Projets" permet de gérer des workspaces de développement avec :

- **Terminal iframe** : Affiche le terminal web du projet
- **Boutons tmux** : Changement de fenêtre via API (Ctrl+B, 1-7)
- **Gestionnaire d'issues** : Suivi des problèmes à corriger
- **Visionneur d'agents** : Statut des tâches en cours par agent

### Configuration d'un projet

```javascript
const projectsConfig = {
    'todo-list': {
        id: 'todo-list',
        name: 'Todo List ERP',
        terminalPort: 7690,
        description: 'Module Todo List pour système ERP'
    }
};
```

### API JavaScript pour les projets

```javascript
// Ajouter une issue (depuis la console ou un script)
window.addProjectIssue('todo-list', 'Titre', 'Description', 'high');

// Lire les issues
window.getProjectIssues('todo-list');

// Mettre à jour une tâche agent
window.updateAgentTask('todo-list', 'Backend', 'Migration DB', 'running');
```

## Terminal Manager (dtach)

Les terminaux web utilisent **dtach** au lieu de tmux pour permettre le scroll natif du navigateur.

**Services systemd :**
- `ttyd-terminal.service` - Port 7680 (Bash)
- `ttyd-claude.service` - Port 7681 (Claude Code)
- `ttyd-sudo-claude.service` - Port 7682 (Sudo Claude)

**Fichiers :**
- `/home/cactus/bin/dtach-wrapper.sh` - Script wrapper pour les sessions
- `/etc/systemd/system/ttyd-*.service` - Services systemd

**Avantages de dtach vs tmux :**
- Scroll natif du navigateur fonctionne
- Pas de raccourcis qui interfèrent avec Claude Code
- Sessions persistantes (survivent à la fermeture de l'onglet)

**Interface :**
- Boutons **B** (Bash) et **C** (Claude) pour ouvrir un terminal
- Onglets pour gérer plusieurs terminaux
- Bouton ⚙ pour gérer les projets visibles/cachés
- Bouton ↻ pour rafraîchir la liste des dossiers

## Widget Bug Report

Widget de signalement de bugs/suggestions intégré à l'API centralisée bugs.sharpi.ca.

**Fonctionnalités :**
- Bouton flottant rouge "Bug Report" (bas droite, caché en mode terminal)
- Barre verticale à droite en mode terminal avec accès Bug Report
- Types: Bug, Suggestion, Feature, Amélioration
- Priorités: Basse, Normale, Haute, Critique
- Support capture d'écran: Ctrl+V (paste), drag & drop, ou clic pour choisir
- Collecte automatique du contexte (URL, user agent, timestamp)
- Référence unique générée (ex: HOM-001)

**Configuration :**
```javascript
const BUGS_API_URL = 'https://bugs.sharpi.ca/api/v1';
const BUGS_API_KEY = 'HOM_3fdff2c497afcb524fff12dc0f6d7e36cde2b6cafbecbe80';
```

**API bugs.sharpi.ca :**
```bash
# Créer une issue
POST /api/v1/issues
Authorization: Bearer HOM_xxx

# Lister les issues
GET /api/v1/issues

# Uploader une capture
POST /api/v1/issues/HOM-001/attachments
```

## Notifications Telegram

Le système envoie des notifications Telegram quand une demande ERP est soumise.

**Configuration** (variables d'environnement) :
```bash
TELEGRAM_BOT_TOKEN=xxx
TELEGRAM_CHAT_ID=xxx
```

Les credentials sont stockés dans `.env` (gitignored) et passés au conteneur Docker.

## Fichiers du projet

```
/home/cactus/claude/homepage-app/
├── CLAUDE.md              # Cette documentation
├── server.py              # Serveur Flask + API REST
├── index.html             # Frontend (HTML + CSS + JS)
├── requirements.txt       # Dépendances Python
├── Dockerfile             # Image Docker
├── docker-compose.yml     # Configuration Docker Compose
├── .env                   # Variables d'environnement (gitignored)
├── .gitignore             # Fichiers ignorés par git
├── dtach-wrapper.sh       # Script wrapper pour terminaux dtach
├── ttyd-terminal.service  # Service systemd terminal Bash
├── ttyd-claude.service    # Service systemd terminal Claude
└── ttyd-sudo-claude.service # Service systemd terminal Sudo
```

## Sous-projet : chromium/

Le dossier `chromium/` contient la configuration pour un navigateur Chromium accessible à distance via le web (Kasm Workspaces).

- **URL** : https://192.168.1.135:6901
- **Credentials** : `kasm_user` / `secret`
- **Voir** : `chromium/CLAUDE.md` pour la documentation complète

## Commandes Docker

```bash
# Voir les logs
docker logs homepage

# Redémarrer le conteneur
docker restart homepage

# Reconstruire et redéployer
cd /home/cactus/claude/homepage-app
docker build -t homepage-flask .
docker stop homepage && docker rm homepage
docker run -d --name homepage --restart unless-stopped \
  -p 1000:80 \
  -e TELEGRAM_BOT_TOKEN="xxx" \
  -e TELEGRAM_CHAT_ID="xxx" \
  -v homepage-data:/data \
  -v /home/cactus/claude:/home/cactus/claude:ro \
  -v /tmp/terminal-logs:/tmp/terminal-logs:ro \
  -v /tmp/dtach-sessions:/tmp/dtach-sessions:ro \
  homepage-flask

# Inspecter le volume des préférences
docker exec homepage cat /data/preferences.json
```

**Volumes montés :**
- `/home/cactus/claude` - Dossiers projets (lecture seule)
- `/tmp/terminal-logs` - Logs des terminaux pour détection d'activité
- `/tmp/dtach-sessions` - Sockets des sessions dtach

## Ajouter une nouvelle application

1. Modifier le tableau `defaultApps` dans `index.html` :

```javascript
const defaultApps = [
    // ... apps existantes
    {
        id: 'myapp',           // Identifiant unique
        name: 'Mon App',       // Nom affiché
        desc: 'Description',   // Description sous le nom
        port: ':5001',         // Port affiché
        url: baseUrl(5001),    // URL de redirection
        icon: 'myapp'          // ID de l'icône SVG
    }
];
```

2. Ajouter l'icône SVG dans l'objet `icons` :

```javascript
const icons = {
    // ... icônes existantes
    'myapp': '<path d="..." fill="currentColor"/>'
};
```

3. Ajouter le style de couleur pour l'icône :

```css
.myapp { background: linear-gradient(135deg, #color1, #color2); }
```

4. Ajouter l'app à la page par défaut dans `defaultPages` :

```javascript
const defaultPages = [
    { id: 'main', name: 'Accueil', apps: [..., 'myapp'] },
    // ...
];
```

5. Reconstruire et redéployer le conteneur.

## Bugs corrigés

| Bug | Correction |
|-----|------------|
| Texte invisible dans le menu contextuel | Ajout de `!important` sur les couleurs des boutons |
| Options dropdown invisibles dans Admin | Fond explicite `#1e293b` et texte blanc sur les `<option>` |

## Améliorations possibles

- ~~Externaliser la config dans un fichier JSON~~ (fait via API)
- ~~Persistance globale des préférences~~ (fait)
- ~~Scroll natif dans les terminaux web~~ (fait avec dtach)
- ~~Liste dynamique des projets~~ (fait via API scan)
- Ajouter un health check des services (ping automatique)
- Support du thème clair
- Authentification pour l'API

## Session du 24 janvier 2026

**Changements effectués :**

1. **Migration tmux → dtach** pour les terminaux web
   - Scroll natif du navigateur fonctionne
   - Création de `dtach-wrapper.sh`
   - Mise à jour des services systemd

2. **Terminal Manager optimisé**
   - Liste des projets chargée dynamiquement depuis `/home/cactus/claude`
   - Modal ⚙ pour gérer les projets cachés (persisté sur serveur)
   - Suppression bouton Sudo (S) et bouton hide par ligne
   - Plus d'espace pour les noms de projets (171px vs 107px)

3. **Système de demandes ERP**
   - API REST pour gérer les demandes (feature/bug/improvement)
   - Notifications Telegram automatiques
   - Interface dans la homepage

4. **Commits :**
   - `feat: add ERP requests system with Telegram notifications`
   - `feat: replace tmux with dtach for web terminals`
   - `feat: dynamic project folders with hide/show functionality`
   - `refactor: optimize terminal sidebar and add settings modal`

## Session du 25 janvier 2026

**Changements effectués :**

1. **Widget Bug Report**
   - Bouton flottant rouge en bas à droite (caché en mode terminal)
   - Modal de signalement avec types: Bug, Suggestion, Feature, Amélioration
   - Priorités: Basse, Normale, Haute, Critique
   - Support paste/drag-drop de captures d'écran (Ctrl+V)
   - Intégration avec bugs_service (https://bugs.sharpi.ca)
   - Projet "Homepage Cactus" créé (slug: homepage, préfixe: HOM)
   - API Key: `HOM_3fdff2c497afcb524fff12dc0f6d7e36cde2b6cafbecbe80`

2. **Mode Terminal optimisé**
   - Header, footer et top-bar cachés sur la page Terminaux
   - Barre de navigation verticale à droite (Accueil, Terminaux, Bug Report)
   - Sidebar projets rétractable avec bouton ◀
   - Terminal maximisé: `height: calc(100vh - 80px)`

3. **Sessions dtach persistantes**
   - Noms de session basés sur `projet_type` (sans timestamp)
   - Si on reclique B/C pour le même projet, active l'onglet existant
   - Wrapper dtach mis à jour pour sessions en arrière-plan (`dtach -n` puis `dtach -a`)

4. **Corrections services ttyd**
   - Ajout option `-a` (url-arg) pour passer les arguments via URL
   - Permissions `/tmp/dtach-sessions/` corrigées (chmod 777)
   - Commande: `ttyd -p PORT -W -a -t fontSize=14 -t fontFamily=monospace /home/cactus/bin/dtach-wrapper.sh`

**Configuration ttyd requise :**
```bash
# Les 3 services doivent avoir l'option -a
ExecStart=/usr/bin/ttyd -p 7680 -W -a -t fontSize=14 -t fontFamily=monospace /home/cactus/bin/dtach-wrapper.sh
ExecStart=/usr/bin/ttyd -p 7681 -W -a -t fontSize=14 -t fontFamily=monospace /home/cactus/bin/dtach-wrapper.sh
ExecStart=/usr/bin/ttyd -p 7682 -W -a -t fontSize=14 -t fontFamily=monospace /home/cactus/bin/dtach-wrapper.sh
```

**Permissions requises :**
```bash
chmod 777 /tmp/dtach-sessions/
chmod 777 /tmp/terminal-logs/
```

## Session du 25 janvier 2026 (suite)

**Nouvelles fonctionnalités Terminal Manager :**

1. **Détection d'attente terminal**
   - Le wrapper `dtach-wrapper.sh` utilise `script` pour logger la sortie
   - API `/api/terminal/activity` poll les logs pour détecter les patterns
   - Patterns détectés : `[Y/n]`, `[y/N]`, `Continue?`, `Password:`, etc.
   - Polling toutes les 2 secondes quand en mode terminal

2. **Bip sonore**
   - Web Audio API joue un beep (800Hz, 0.2s) quand un terminal attend
   - Throttle de 3 secondes entre les beeps
   - Ne joue pas si l'onglet en attente est actif

3. **Indicateur visuel d'attente**
   - Point jaune pulsant sur l'onglet
   - Bordure dorée avec glow
   - Animation CSS `activity-pulse`

4. **Boutons Yes/Yes to All**
   - Boutons **Y** (vert) et **Y*** (bleu) apparaissent sur les onglets en attente
   - Connexion WebSocket parallèle vers ttyd
   - Protocole ttyd : `[0x30][data]` pour envoyer du texte
   - Ferme automatiquement l'état d'attente après envoi

5. **Preview au survol des onglets**
   - Mini-iframe (400x250px) scalée à 50%
   - Apparaît après 400ms de survol
   - Position fixe sous l'onglet, par-dessus le terminal
   - Ne s'affiche pas pour l'onglet actif

6. **Clic droit pour coller**
   - Menu contextuel "Coller" sur le terminal
   - Utilise `navigator.clipboard.readText()`
   - Envoie le texte via WebSocket ttyd

**Corrections de sécurité :**

7. **Credentials Telegram externalisés**
   - Déplacés de `server.py` vers variables d'environnement
   - Fichier `.env` créé (gitignored)
   - `docker-compose.yml` mis à jour avec les env vars

8. **Protection XSS**
   - Fonction `escapeHtml()` utilisée pour les noms de projets
   - Échappement des quotes dans les handlers `onclick`

**Design responsive mobile/tablette :**

9. **Layout Mobile (< 768px)**
   - Sidebar en drawer slide-out (85% largeur)
   - Bouton hamburger ☰ pour ouvrir
   - Onglets scrollables horizontalement
   - Bouton 🏠 pour retourner à l'accueil
   - Terminal plein écran (100vh)
   - Header/footer cachés en mode terminal

10. **Layout Tablette (768px - 1024px)**
    - Sidebar plus étroite (220px)
    - Boutons et onglets plus compacts
    - Preview réduit (300x180px)

11. **Petit Mobile (< 480px)**
    - Drawer pleine largeur
    - Onglets encore plus compacts

**Fichiers modifiés :**
- `server.py` - API terminal activity, credentials en env vars
- `index.html` - Toutes les fonctionnalités frontend + responsive
- `docker-compose.yml` - Volumes pour logs/sessions
- `dtach-wrapper.sh` - Logging avec `script`
- `.env` + `.gitignore` - Credentials sécurisés

**Dépendances :**
- Créer `/tmp/terminal-logs/` avec permissions 777
- Copier `dtach-wrapper.sh` vers `/home/cactus/bin/`
