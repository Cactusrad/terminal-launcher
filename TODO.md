# TODO - Terminal Launcher

## Post-rename

- [x] Installer les services systemd sur 192.168.1.100
- [x] Supprimer l'ancien service `homepage-workspace.service`
- [x] Supprimer l'ancien service `ttyd.service` (conflit port 7681)
- [x] Supprimer le dossier `homepage-app` (sur .100 et .200)
- [x] Supprimer les volumes Docker `homepage-data` et `homepage-app_homepage-data`
- [ ] Supprimer le repo GitHub `Cactusrad/homepage-app` (besoin `gh auth refresh -s delete_repo`)
- [ ] Commiter les changements et push
- [x] ~~BUG : service systemd `terminal-server` pointe vers l'ancien chemin `homepage-app`~~ (corrigé sur .200)

## Bugs à investiguer

- [ ] Bug report widget ne fonctionne plus (investiguer la connexion avec bugs_service sur http://192.168.1.200:9010)

## Améliorations prévues

- [ ] Ajouter logging structuré (remplacer les `print()` par `logging`)
- [ ] Rate limiting sur les endpoints API
- [ ] Compression gzip sur les réponses (index.html = 290KB)
- [ ] Tests unitaires pour les routes API
- [ ] CI/CD pipeline (GitHub Actions)
- [ ] Séparer index.html en fichiers modulaires (CSS, JS)

## Complété

- [x] **Drag & drop onglets** : glisser les onglets pour réorganiser leur position
- [x] **Couleur par projet** : chaque projet a une couleur d'onglet distincte (border-left coloré par hash)
- [x] **Bouton Bash global** : bouton Bash dans le header sidebar (icône >_), bouton B retiré des projets
- [x] **Terminal se réouvre après fermeture** : fix via `disposedSessions` + guard dans merge et sync
- [x] **Détecter "exit" / fin de session** : terminal-server.py envoie `session_ended`, client ferme le tab auto
- [x] **Indicateur de terminal actif dans le menu projets** : badge orange avec compteur par projet
- [x] **Terminal pour discuter avec un agent de team** : bouton "T" par projet, type `team` avec prompt du nom d'agent
- [x] **Bash multiples** : le bouton Bash global ouvre un nouveau terminal à chaque clic (home, home_2, home_3...)
- [x] **Modal config opaque** : fond #141420 au lieu de transparent

## Guide d'installation from scratch

### Prérequis

- Ubuntu 24.04 LTS (ou compatible)
- Python 3.12+
- Docker + Docker Compose
- Git + accès au repo GitHub

### 1. Cloner le repo

```bash
cd ~
git clone git@github.com:Cactusrad/terminal-launcher.git
cd ~/terminal-launcher
```

### 2. Configurer l'environnement

```bash
cp .env.example .env
nano .env
```

Variables à configurer :
```env
HOST_IP=192.168.1.100        # IP du serveur
PORT=80                       # Port de l'interface web
TELEGRAM_BOT_TOKEN=           # Optionnel : notifications Telegram
TELEGRAM_CHAT_ID=             # Optionnel : notifications Telegram
BUGS_API_URL=                 # Optionnel : bug tracker
BUGS_API_KEY=                 # Optionnel : bug tracker
```

### 3. Déployer le container Docker (interface web)

```bash
cd ~/terminal-launcher
docker compose build --no-cache
docker compose up -d
```

Vérifier : `http://192.168.1.100` doit afficher le dashboard.

### 4. Installer les dépendances système

```bash
sudo apt install -y ttyd python3.12-venv tmux
```

### 5. Créer le venv Python pour terminal-server

```bash
python3 -m venv ~/terminal-launcher/venv
~/terminal-launcher/venv/bin/pip install aiohttp
```

### 6. Installer les services systemd

```bash
sudo cp ~/terminal-launcher/terminal-server.service ~/terminal-launcher/terminal-launcher-workspace.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now terminal-server terminal-launcher-workspace
```

### 7. Vérifier

```bash
# Docker (web UI)
docker ps | grep terminal-launcher
curl -s http://localhost/health

# terminal-server (WebSocket)
sudo systemctl status terminal-server
ss -tlnp | grep 7681

# terminal-launcher-workspace (ttyd)
sudo systemctl status terminal-launcher-workspace
ss -tlnp | grep 7694
```

### Mise à jour

```bash
cd ~/terminal-launcher
git pull

# Rebuild Docker (si server.py, config.py ou index.html modifié)
docker compose build --no-cache && docker compose up -d

# Restart terminal-server (si terminal-server.py modifié)
sudo systemctl restart terminal-server
```

---

## Services (sur 192.168.1.100)

| Service | Type | Port | Description |
|---------|------|------|-------------|
| `terminal-launcher` | Docker | 80 | Flask web UI (Gunicorn, 2 workers) |
| `terminal-server.service` | systemd | 7681 | WebSocket terminal server (venv Python, aiohttp) |
| `terminal-launcher-workspace.service` | systemd | 7694 | ttyd + tmux workspace |

## Notes

- **Serveur de production** : `192.168.1.100` (pas .200)
- **Paths sur .100** : `~/terminal-launcher/` (pas `~/claude/terminal-launcher/`)
- **Dev/git sur .200** : `~/claude/terminal-launcher/`
- Données Docker dans le volume `launcher-data`
- Le terminal-server.py utilise un venv : `~/terminal-launcher/venv/`
- Le port 7681 ne doit pas être utilisé par un autre service (ex: `ttyd.service` par défaut)
