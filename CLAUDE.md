# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Résumé

Homepage personnalisée "Cactus Home Server" - Dashboard de lancement pour serveur homelab avec persistance globale des préférences.

**URL** : http://192.168.1.200 (port 80)

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
| Terminal | 7680 | Terminal Bash web |
| Claude Terminal | 7681 | Terminal web Claude Code |
| Sudo Claude Terminal | 7682 | Terminal web sudo Claude |

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

## Fichiers du projet

```
/home/cactus/claude/homepage-app/
├── CLAUDE.md              # Cette documentation
├── server.py              # Serveur Flask + API REST
├── index.html             # Frontend (HTML + CSS + JS)
├── requirements.txt       # Dépendances Python
├── Dockerfile             # Image Docker
├── docker-compose.yml     # Configuration Docker Compose
└── add-notify-config.sh   # Script utilitaire
```

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
docker run -d --name homepage --restart unless-stopped -p 80:80 -v homepage-data:/data homepage-flask

# Inspecter le volume des préférences
docker exec homepage cat /data/preferences.json
```

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

## Améliorations possibles

- ~~Externaliser la config dans un fichier JSON~~ (fait via API)
- ~~Persistance globale des préférences~~ (fait)
- Ajouter un health check des services (ping automatique)
- Ajouter une fonction de recherche
- Support du thème clair
- Authentification pour l'API
