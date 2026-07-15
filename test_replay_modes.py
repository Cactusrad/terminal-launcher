#!/usr/bin/env python3
"""
Vérifie que le replay de reconnexion ré-asserte les modes DEC « collants »
(alt-screen ?1049, souris ?1000/?1002/?1003/?1006, DECCKM ?1, bracketed
paste ?2004) même quand leurs séquences d'origine ont été évincées du
buffer circulaire (512 KB) par une session bavarde.

Bug d'origine (2026-07-14) : Claude Code ≥ 2.1.150 émet ?1049h + modes
souris UNE fois au démarrage puis produit des Mo de repaints absolus (aucun
scroll, aucun \n). Après éviction, un client qui recharge la page reçoit un
replay sans ces modes → xterm reste en buffer normal, _appWantsMouse=false
côté frontend → la molette n'est plus forwardée à Claude et le scrollback
local est vide : impossible de voir plus haut que l'écran courant.

Lancer : python3 test_replay_modes.py
"""
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).parent

spec = importlib.util.spec_from_file_location('terminal_server', HERE / 'terminal-server.py')
ts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ts)

PASS = 0
FAIL = 0


def check(name, cond, detail=''):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        print(f"  ✗ {name} {detail}")


def make_trimmed_claude_buffer():
    """Simule une session Claude Code : init une fois, puis assez de repaints
    pour évincer l'init du buffer circulaire."""
    buf = ts.SessionBuffer()
    # Init réelle capturée dans /tmp/terminal-logs (v1.0.14) : alt-screen,
    # DECCKM, souris any-event + SGR, bracketed paste.
    buf.append(b'\x1b[?1049h\x1b[?1h\x1b[?2004h')
    buf.append(b'\x1b[?1000h\x1b[?1002h\x1b[?1003h\x1b[?1006h')
    buf.append(b'bienvenue dans claude\r\n')
    # ~2 MB de frames de repaint (4x la limite de 512 KB) → éviction certaine
    frame = b'\x1b[2;1H\x1b[K' + b'x' * 1000
    for _ in range(2048):
        buf.append(frame)
    return buf


print("== 1. Éviction : l'init n'est plus dans les données brutes ==")
buf = make_trimmed_claude_buffer()
raw = b''.join(buf.data)
check("init 1049h évincée du buffer brut", b'\x1b[?1049h' not in raw)
check("init 1000h évincée du buffer brut", b'\x1b[?1000h' not in raw)

print("== 2. Le replay ré-asserte les modes actifs (LE fix) ==")
replay = buf.get_all()
for mode in ('1049', '1', '1000', '1002', '1003', '1006', '2004'):
    seq = f'\x1b[?{mode}h'.encode()
    check(f"replay contient ?{mode}h", replay.startswith(b'\x1b[') and seq in replay[:200],
          f"(absent des 200 premiers octets du replay)")

print("== 3. L'alt-screen est ré-asserté AVANT les frames ==")
idx_alt = replay.find(b'\x1b[?1049h')
idx_frames = replay.find(b'\x1b[2;1H')
check("?1049h précède les frames de repaint", 0 <= idx_alt < idx_frames)

print("== 4. Un mode désactivé (h puis l) n'est PAS ré-asserté ==")
buf2 = ts.SessionBuffer()
buf2.append(b'\x1b[?1049h\x1b[?1000h')
buf2.append(b'\x1b[?1000l\x1b[?1049l')  # l'appli quitte l'alt-screen (ex. claude exit)
for _ in range(2048):
    buf2.append(b'\x1b[2;1H\x1b[K' + b'y' * 1000)
replay2 = buf2.get_all()
check("pas de ?1049h dans le préfixe", b'\x1b[?1049h' not in replay2[:200])
check("pas de ?1000h dans le préfixe", b'\x1b[?1000h' not in replay2[:200])

print("== 5. Session bash (aucun mode) : replay identique aux données ==")
buf3 = ts.SessionBuffer()
buf3.append(b'$ ls\r\nfichier.txt\r\n$ ')
check("replay inchangé", buf3.get_all() == b'$ ls\r\nfichier.txt\r\n$ ')

print("== 6. Séquence coupée entre deux chunks PTY ==")
buf4 = ts.SessionBuffer()
buf4.append(b'\x1b[?10')      # coupure en plein milieu de ?1049h
buf4.append(b'49h\x1b[?1006h')
for _ in range(2048):
    buf4.append(b'\x1b[2;1H' + b'z' * 1000)
replay4 = buf4.get_all()
check("?1049h détecté malgré la coupure", b'\x1b[?1049h' in replay4[:200])
check("?1006h détecté", b'\x1b[?1006h' in replay4[:200])

print("== 7. Params groupés (?1000;1002;1006h) ==")
buf5 = ts.SessionBuffer()
buf5.append(b'\x1b[?1000;1002;1006h')
for _ in range(2048):
    buf5.append(b'\x1b[2;1H' + b'w' * 1000)
replay5 = buf5.get_all()
for mode in ('1000', '1002', '1006'):
    check(f"?{mode}h ré-asserté depuis params groupés", f'\x1b[?{mode}h'.encode() in replay5[:200])

print("== 8. clear() remet aussi l'état des modes à zéro ==")
buf6 = ts.SessionBuffer()
buf6.append(b'\x1b[?1049h\x1b[?1000h')
buf6.clear()
buf6.append(b'apres reset')
check("aucun mode ré-asserté après clear()", buf6.get_all() == b'apres reset')

print("== 9. seed_modes_from_log : restart du serveur, session dtach vivante ==")
import tempfile, os
buf7 = ts.SessionBuffer()
with tempfile.NamedTemporaryFile(delete=False, suffix='.log') as f:
    f.write(b'\x1b[?1049h\x1b[?1000h\x1b[?1006h' + b'\x1b[2;1H' + b'v' * 100000)
    logpath = f.name
buf7.seed_modes_from_log(logpath)
os.unlink(logpath)
replay7 = buf7.get_all()
check("?1049h ré-asserté depuis le log", b'\x1b[?1049h' in replay7[:200])
check("?1000h ré-asserté depuis le log", b'\x1b[?1000h' in replay7[:200])
buf8 = ts.SessionBuffer()
buf8.seed_modes_from_log('/nonexistent/x.log')
check("log absent → silencieux, replay vide", buf8.get_all() == b'')

print(f"\n{PASS} passés, {FAIL} échoués")
sys.exit(1 if FAIL else 0)
