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

## Notes

- Données Docker dans le volume `launcher-data` (anciennement `homepage-data`)
- L'ancien volume `homepage-data` peut être supprimé : `docker volume rm homepage-app_homepage-data`
- Backup des données dans `/tmp/launcher-backup/` (temporaire, sera perdu au reboot)
