#!/usr/bin/env node
// Prouve le fix d'ordre des onglets terminaux (dérive multi-fenêtres).
// Extrait les vrais helpers tabOrderKey/sortTabsByOrder de index.html et rejoue
// le scénario : 3 onglets créés dans l'ordre T1,T2,T3 ; une 2e fenêtre qui ne
// connaît que [T2,T3] sauvegarde et merge l'onglet manquant T1.
//
//   AVANT le fix (merge "append en fin", sans tri) -> ordre serveur = [T2,T3,T1]
//        => l'onglet premier (T1) n'est plus premier : le test ASSERT_OLD échoue.
//   APRÈS le fix (tri par clé d'ordre stable)       -> ordre serveur = [T1,T2,T3]
//        => l'onglet premier reste premier : le test ASSERT_NEW passe.

const fs = require('fs');
const path = require('path');

const html = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf8');

// --- Extraction des vrais helpers du fichier (pas une copie) ---
const m = html.match(/function tabOrderKey\(t\) \{[\s\S]*?\n {8}\}\n {8}function sortTabsByOrder\(tabs\) \{[\s\S]*?\n {8}\}/);
if (!m) {
    console.error('FAIL: helpers tabOrderKey/sortTabsByOrder introuvables dans index.html (fix absent)');
    process.exit(1);
}
// eval direct (mode sloppy) : les déclarations de fonctions fuitent dans ce scope.
const { tabOrderKey, sortTabsByOrder } = eval(
    '(function(){' + m[0] + '\nreturn { tabOrderKey, sortTabsByOrder };})()'
);

// --- Scénario ---
const T1 = { id: 'T1', tmuxSession: 's1', createdAt: 100 };
const T2 = { id: 'T2', tmuxSession: 's2', createdAt: 200 };
const T3 = { id: 'T3', tmuxSession: 's3', createdAt: 300 };

const serverTabs = [T1, T2, T3];        // ordre serveur canonique
const windowBLocal = [T2, T3];          // 2e fenêtre : a perdu T1 localement

// Replique le merge de saveTerminalState : locaux d'abord, server-only ajoutés en fin.
function merge(local, server) {
    const localBySession = new Map();
    local.forEach(t => localBySession.set(t.tmuxSession, t));
    const merged = [...local];
    server.forEach(rt => { if (!localBySession.has(rt.tmuxSession)) merged.push(rt); });
    return merged;
}

const mergedOld = merge(windowBLocal, serverTabs);                 // comportement d'avant
const mergedNew = sortTabsByOrder(merge(windowBLocal, serverTabs)); // comportement d'après

let failures = 0;
function check(label, cond) {
    console.log(`${cond ? 'PASS' : 'FAIL'}: ${label}`);
    if (!cond) failures++;
}

// Démonstration de la régression d'origine (l'onglet premier dérive).
check('ASSERT_OLD: sans tri, T1 (premier) se retrouve dernier (bug reproduit)',
      mergedOld[0].id !== 'T1' && mergedOld[mergedOld.length - 1].id === 'T1');

// Le fix : ordre stable, premier reste premier, ordre = ordre de création.
check('ASSERT_NEW: avec tri, T1 reste premier', mergedNew[0].id === 'T1');
check('ASSERT_NEW: ordre complet stable = [T1,T2,T3]',
      mergedNew.map(t => t.id).join(',') === 'T1,T2,T3');

// Idempotence : re-merger l'ordre trié depuis n'importe quelle fenêtre ne dérive plus.
const reMerged = sortTabsByOrder(merge([T3, T1], mergedNew));
check('ASSERT_NEW: convergence (re-merge depuis une autre fenêtre reste [T1,T2,T3])',
      reMerged.map(t => t.id).join(',') === 'T1,T2,T3');

// Drag-drop : un order fractionnaire place l'onglet et survit au tri.
const dragged = { id: 'T2', tmuxSession: 's2', createdAt: 200, order: 350 }; // déplacé après T3
const afterDrag = sortTabsByOrder([T1, dragged, T3]);
check('ASSERT_NEW: drag-drop (order fractionnaire) persiste après tri = [T1,T3,T2]',
      afterDrag.map(t => t.id).join(',') === 'T1,T3,T2');

console.log(failures === 0 ? '\nOK — fix vérifié' : `\n${failures} assertion(s) en échec`);
process.exit(failures === 0 ? 0 : 1);
