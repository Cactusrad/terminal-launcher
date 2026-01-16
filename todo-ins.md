# Cactus TODO-LIST - Instructions

## Accès au workspace

**URL** : http://192.168.1.200:7690

Tu devrais voir le workspace tmux avec les 7 fenêtres.

---

## Navigation dans le workspace

| Raccourci   | Action                  |
|-------------|-------------------------|
| Ctrl+B, 1   | Claude (maître d'œuvre) |
| Ctrl+B, 2   | Structure (tree)        |
| Ctrl+B, 3   | DevLog                  |
| Ctrl+B, 4   | Backend                 |
| Ctrl+B, 5   | Frontend                |
| Ctrl+B, 6   | Tests                   |
| Ctrl+B, 7   | Git                     |

---

## Description des fenêtres

### 1. Claude (maître d'œuvre)
Fenêtre principale où Claude Code orchestre le travail et coordonne les différents agents.

### 2. Structure (tree)
Affichage de l'arborescence du projet pour visualiser la structure des fichiers.

### 3. DevLog
Journal de développement pour suivre les logs et messages du système.

### 4. Backend
Terminal dédié au développement backend (serveur, API, base de données).

### 5. Frontend
Terminal dédié au développement frontend (interface utilisateur, styles).

### 6. Tests
Terminal pour l'exécution des tests unitaires et d'intégration.

### 7. Git
Terminal dédié aux opérations Git (commits, branches, push/pull).

---

## Comment modifier les outils

### Fichiers de configuration

- **Page projet** : `/home/cactus/claude/homepage-app/index.html`
  - Modifier la section `projectsConfig` pour ajouter/modifier des projets
  - Modifier `defaultIssues` pour les problèmes par défaut

- **Préférences** : `/data/preferences.json` (dans le conteneur Docker)
  - Contient les issues et tâches sauvegardées

### Ajouter un nouveau projet

1. Dans `index.html`, ajouter une entrée dans `projectsConfig`:
```javascript
{
    id: 'mon-projet',
    name: 'Mon Projet',
    terminalPort: 7690,
    description: 'Description du projet'
}
```

### Modifier les issues

Les issues sont stockées dans le localStorage et synchronisées avec le serveur.
Format d'une issue:
```javascript
{
    id: 'issue-123',
    title: 'Titre du problème',
    description: 'Description détaillée',
    priority: 'high', // high, medium, low
    status: 'open'    // open, in_progress, resolved
}
```

### Modifier les tâches agents

Les tâches agents sont mises à jour dynamiquement.
Format d'une tâche:
```javascript
{
    id: 'task-123',
    agent: 'Backend',
    task: 'Description de la tâche',
    status: 'running' // pending, running, completed
}
```

---

## API Endpoints pour les projets

| Endpoint | Méthode | Description |
|----------|---------|-------------|
| `/api/projects` | GET | Liste des projets |
| `/api/projects/:id/issues` | GET | Issues d'un projet |
| `/api/projects/:id/issues` | POST | Ajouter une issue |
| `/api/projects/:id/tasks` | GET | Tâches agents d'un projet |

---

## Raccourcis clavier tmux utiles

| Raccourci | Action |
|-----------|--------|
| Ctrl+B, c | Créer une nouvelle fenêtre |
| Ctrl+B, n | Fenêtre suivante |
| Ctrl+B, p | Fenêtre précédente |
| Ctrl+B, d | Détacher la session |
| Ctrl+B, % | Split vertical |
| Ctrl+B, " | Split horizontal |
| Ctrl+B, z | Zoom sur le panneau actuel |
| Ctrl+B, [ | Mode scroll (q pour quitter) |
