#!/bin/bash
# Script pour ajouter Claude Notify Config à la homepage
# Exécuter avec: sudo bash add-notify-config.sh

HOMEPAGE="/home/cactus/docker/homepage/index.html"

# Backup
cp "$HOMEPAGE" "$HOMEPAGE.bak"

# 1. Ajouter la classe CSS pour l'icône notify
sed -i 's/.n8n { background: linear-gradient(135deg, #ff6d5a, #ea4b30); }/.n8n { background: linear-gradient(135deg, #ff6d5a, #ea4b30); }\n        .notify { background: linear-gradient(135deg, #ff6d5a, #ff8f4a); }/' "$HOMEPAGE"

# 2. Ajouter l'app dans defaultApps (après n8n)
sed -i "/{ id: 'n8n',.*visible: true },/a\\            { id: 'notify', name: 'Claude Notify Config', desc: 'Configuration notifications push', port: ':5001', url: baseUrl(5001), icon: 'notify', visible: true }," "$HOMEPAGE"

# 3. Ajouter l'icône (cloche avec point d'exclamation)
sed -i "/n8n: '<path/a\\            notify: '<path d=\"M12 22c1.1 0 2-.9 2-2h-4c0 1.1.9 2 2 2zm6-6v-5c0-3.07-1.63-5.64-4.5-6.32V4c0-.83-.67-1.5-1.5-1.5s-1.5.67-1.5 1.5v.68C7.64 5.36 6 7.92 6 11v5l-2 2v1h16v-1l-2-2zm-2 1H8v-6c0-2.48 1.51-4.5 4-4.5s4 2.02 4 4.5v6z\"/><circle cx=\"18\" cy=\"8\" r=\"4\" fill=\"#ff6d5a\"/><text x=\"18\" y=\"10\" text-anchor=\"middle\" fill=\"white\" font-size=\"6\" font-weight=\"bold\">!</text>'," "$HOMEPAGE"

echo "Claude Notify Config ajouté à la homepage!"
echo "Rafraîchis la page http://192.168.1.200 pour voir les changements."
