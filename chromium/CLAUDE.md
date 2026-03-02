# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Résumé

Navigateur Chromium accessible à distance via un navigateur web, basé sur Kasm Workspaces.

**URL** : https://192.168.1.135:6901

## Architecture

```
┌─────────────────────┐     HTTPS      ┌──────────────────────────┐
│  Navigateur local   │ ─────────────▶ │   Conteneur Kasm         │
│  (client)           │ ◀───────────── │                          │
└─────────────────────┘    WebSocket   │  ┌────────────────────┐  │
                                       │  │  Chromium Browser  │  │
                                       │  └────────────────────┘  │
                                       │  ┌────────────────────┐  │
                                       │  │  noVNC / KasmVNC   │  │
                                       │  └────────────────────┘  │
                                       │  ┌────────────────────┐  │
                                       │  │  XFCE Desktop      │  │
                                       │  └────────────────────┘  │
                                       └──────────────────────────┘
```

## Accès

| Paramètre | Valeur |
|-----------|--------|
| URL | https://localhost:6901 |
| Utilisateur | `kasm_user` |
| Mot de passe | `secret` |
| Protocole | HTTPS obligatoire |

## Commandes Docker

```bash
# Démarrer
docker-compose up -d

# Ou sans docker-compose
docker run -d --name kasm-chrome \
  -p 6901:6901 \
  -e VNC_PW=secret \
  --shm-size=2g \
  kasmweb/chromium:1.15.0

# Arrêter
docker stop kasm-chrome

# Redémarrer
docker start kasm-chrome

# Supprimer
docker rm -f kasm-chrome

# Voir les logs
docker logs kasm-chrome

# Changer le mot de passe (recréer le conteneur)
docker rm -f kasm-chrome
docker run -d --name kasm-chrome \
  -p 6901:6901 \
  -e VNC_PW=monmotdepasse \
  --shm-size=2g \
  kasmweb/chromium:1.15.0
```

## Configuration

| Variable | Description | Défaut |
|----------|-------------|--------|
| `VNC_PW` | Mot de passe VNC | `secret` |
| `--shm-size` | Mémoire partagée (requis pour Chrome) | `2g` |
| Port 6901 | Interface web HTTPS | - |

## Notes importantes

- **HTTPS obligatoire** : Kasm refuse les connexions HTTP non-SSL
- **Certificat auto-signé** : Accepter l'avertissement du navigateur
- **shm-size** : Requis pour éviter les crashes de Chromium (minimum 2g)
- **Persistance** : Les données ne sont pas persistées par défaut (ajouter un volume si besoin)

## Persistance des données (optionnel)

```bash
docker run -d --name kasm-chrome \
  -p 6901:6901 \
  -e VNC_PW=secret \
  --shm-size=2g \
  -v kasm-chrome-data:/home/kasm-user \
  kasmweb/chromium:1.15.0
```
