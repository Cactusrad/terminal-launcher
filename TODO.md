# TODO - Terminal Launcher

## Post-rename (à faire manuellement)

- [ ] Autoriser GitHub pour supprimer `homepage-app` (code device flow)
- [ ] Supprimer le repo `Cactusrad/homepage-app` : `gh repo delete Cactusrad/homepage-app --yes`
- [ ] Rendre le repo `terminal-launcher` privé : `gh repo edit Cactusrad/terminal-launcher --visibility private`
- [ ] Installer les services systemd :
  ```bash
  sudo cp /home/cactus/claude/terminal-launcher/terminal-server.service /etc/systemd/system/
  sudo cp /home/cactus/claude/terminal-launcher/terminal-launcher-workspace.service /etc/systemd/system/
  sudo systemctl daemon-reload
  sudo systemctl restart terminal-server
  ```
- [ ] Supprimer l'ancien service : `sudo rm /etc/systemd/system/homepage-workspace.service`
- [ ] Commiter les changements et push

## Terminal Manager

- [ ] **Drag & drop onglets** : pouvoir glisser les onglets pour réorganiser leur position
- [ ] **Couleur par projet** : chaque projet a une couleur d'onglet distincte (attribuée automatiquement)
- [ ] **Bouton Bash global** : supprimer le bouton bash de chaque projet, ajouter un seul bouton Bash dans le header à côté de Reload et Config (icône cohérente avec le style existant)

## Améliorations prévues

- [ ] Ajouter logging structuré (remplacer les `print()` par `logging`)
- [ ] Rate limiting sur les endpoints API
- [ ] Compression gzip sur les réponses (index.html = 290KB)
- [ ] Tests unitaires pour les routes API
- [ ] CI/CD pipeline (GitHub Actions)
- [ ] Séparer index.html en fichiers modulaires (CSS, JS)

## Bugs connus

- [x] **Terminal se réouvre après fermeture** : quand on ferme un onglet terminal, il se réouvre automatiquement (probablement le sync polling qui le recrée depuis l'état serveur ou les sessions dtach) — **CORRIGÉ** : disposedSessions empêche le merge de ré-ajouter les tabs fermés

## Nouvelles fonctionnalités

- [ ] **Détecter "exit" dans un terminal Claude** : Quand l'utilisateur tape "exit" dans un terminal (surtout Claude), la session ne doit plus être considérée comme active/ouverte. Détecter la commande exit et fermer/retirer le tab automatiquement.
- [ ] **Indicateur de terminal actif dans le menu projets** : Afficher quelque chose à côté du nom de chaque projet dans le sidebar qui indique qu'il y a un ou des terminaux actifs pour ce projet (ex: un badge, un point coloré, ou un compteur).
- [ ] **Terminal pour discuter avec un agent d'un team** : Pouvoir ouvrir un nouveau type de terminal qui permet de communiquer/discuter avec un agent membre d'un team (Claude Code teams/subagents).

## Notes

- Données Docker dans le volume `launcher-data` (anciennement `homepage-data`)
- L'ancien volume `homepage-data` peut être supprimé : `docker volume rm homepage-app_homepage-data`
- Backup des données dans `/tmp/launcher-backup/` (temporaire, sera perdu au reboot)
