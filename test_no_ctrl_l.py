#!/usr/bin/env python3
"""
Vérifie le fix du « /clear fantôme » (incident 2026-07-15 : après un reload ou
un redémarrage, chaque terminal Claude se retrouve avec un /clear — conversations
effacées).

Cause : à chaque (re)connexion WebSocket, ws.onopen envoyait \\x0c (Ctrl+L)
500 ms après l'ouverture pour « forcer un redraw ». Or Claude Code ≥ 2.1.x mappe
Ctrl+L ×2 sur la commande /clear (« Press ctrl+l again to /clear » — vérifié
empiriquement contre claude 2.1.210 dans un PTY). Avec plusieurs clients
attachés à la même session (plusieurs onglets/appareils), un reload = plusieurs
\\x0c rapprochés = /clear exécuté. 1 octet = invisible pour l'instrumentation
INPUT-CHUNK (seuil ≥ 3 octets), d'où le fantôme.

Fix : ne plus envoyer le Ctrl+L de redraw aux onglets dont la commande contient
« claude » (le replay du buffer repeint le TUI) ; bash le garde.

Méthode (hermétique, AUCUNE vraie session) :
  - window.WebSocket remplacé par un stub OUVERT qui ENREGISTRE chaque send().
  - onglet créé via la vraie createTerminalTab() → vrai ws.onopen inline.
  - on attend > 500 ms (le \\x0c partait dans un setTimeout(500)).

Assertions :
  AVANT (.100, vieux code) : un \\x0c est envoyé au WS d'un onglet claude
    (la connexion seule suffit — aucune frappe utilisateur).
  APRÈS (.200, corrigé)   : AUCUN \\x0c sur un onglet claude.
  Non-régression          : un onglet bash reçoit toujours son \\x0c de redraw.

Usage : python3.12 test_no_ctrl_l.py [after|before|both]
"""
import sys
import time
from playwright.sync_api import sync_playwright

# Noms uniques par run : un onglet du même nom déjà présent dans le state de
# mohamed court-circuiterait createTerminalTab (simple activation, pas de WS).
RUN_ID = str(int(time.time()))[-6:]

AFTER_URL = "https://192.168.1.200"   # code corrigé
BEFORE_URL = "https://192.168.1.100"  # prod, vieux code (état AVANT)

WS_STUB = r"""
window.__wsSent = [];
window.__wsInstances = [];
(function () {
  const decode = (data) => {
    try {
      if (data instanceof ArrayBuffer) return new TextDecoder().decode(data);
      if (ArrayBuffer.isView(data)) return new TextDecoder().decode(data.buffer);
      return String(data);
    } catch (e) { return ''; }
  };
  function FakeWS(url) {
    this.url = url;
    this.readyState = 1;            // OPEN d'emblée
    this.binaryType = 'blob';
    this.onopen = null; this.onmessage = null; this.onerror = null; this.onclose = null;
    window.__wsInstances.push(this);
    const self = this;
    setTimeout(() => { if (self.onopen) self.onopen({}); }, 0);  // déclenche le flux normal
  }
  FakeWS.prototype.send = function (data) { window.__wsSent.push({url: this.url, data: decode(data)}); };
  FakeWS.prototype.close = function () { this.readyState = 3; if (this.onclose) this.onclose({}); };
  FakeWS.CONNECTING = 0; FakeWS.OPEN = 1; FakeWS.CLOSING = 2; FakeWS.CLOSED = 3;
  window.WebSocket = FakeWS;
})();
"""

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f" — {detail}" if detail else ""))


def ctrl_l_count(sent, session_substr):
    return sum(1 for s in sent if session_substr in s["url"] and "\x0c" in s["data"])


def run(url, label, expect_fix):
    print(f"\n=== {label} ({url}) — fix attendu: {expect_fix} ===")
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--ignore-certificate-errors"])
        ctx = browser.new_context(ignore_https_errors=True, viewport={"width": 1200, "height": 800})
        page = ctx.new_page()
        page.add_init_script(WS_STUB)
        page.goto(url, wait_until="domcontentloaded")
        # Auth LAN sans mot de passe : sélection de l'user mohamed (jamais pierre en E2E)
        page.evaluate("""async () => {
            await fetch('/api/auth/select-user', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({username:'mohamed'})});
        }""")
        page.reload(wait_until="domcontentloaded")
        page.wait_for_function("typeof createTerminalTab === 'function' && typeof loadTerminal === 'function'", timeout=15000)
        # La vue Terminaux doit être active pour que loadTerminal construise le pane
        page.evaluate("typeof setCurrentPageId === 'function' && setCurrentPageId('terminals')")
        page.wait_for_function("!!document.getElementById('terminalContainer')", timeout=10000)
        page.wait_for_timeout(800)

        def connect_tab(tab_type, name):
            """Crée un onglet, attend le setTimeout(500) du onopen, renvoie les sends de SON WS."""
            page.evaluate(f"window.__wsSent = []; createTerminalTab('{tab_type}', '{name}');")
            # sanity : le WS de l'onglet doit s'être ouvert (resize envoyé) — sinon l'assertion serait creuse
            page.wait_for_function(
                f"window.__wsSent.some(s => s.url.includes('{name}') && s.data.includes('resize'))", timeout=10000)
            page.wait_for_timeout(1200)   # le \x0c partait à +500 ms
            return page.evaluate("window.__wsSent.slice()")

        # --- Cas 1 : onglet CLAUDE — la simple connexion ne doit rien taper ---
        name_claude = f"VERIFYNOCTRL{RUN_ID}"
        sent = connect_tab('claude', name_claude)
        n = ctrl_l_count(sent, name_claude)
        check("sanity : le WS de l'onglet claude s'est connecté (resize vu)", True)
        if expect_fix:
            check("onglet claude : AUCUN \\x0c (Ctrl+L) envoyé à la connexion", n == 0, f"{n} \\x0c")
        else:
            check("AVANT : le \\x0c part bien à la connexion (bug présent)", n >= 1, f"{n} \\x0c")

        # --- Cas 2 (fix only) : non-régression bash — le redraw Ctrl+L reste ---
        if expect_fix:
            name_bash = f"VERIFYCTRLBASH{RUN_ID}"
            sent2 = connect_tab('bash', name_bash)
            n2 = ctrl_l_count(sent2, name_bash)
            check("non-régression : onglet bash → le \\x0c de redraw est toujours envoyé", n2 >= 1, f"{n2} \\x0c")

        browser.close()


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "after"
    if mode in ("before", "both"):
        try:
            run(BEFORE_URL, "AVANT (prod .100, vieux code)", expect_fix=False)
        except Exception as e:
            print("  (AVANT non testé:", e, ")")
    if mode in ("after", "both"):
        run(AFTER_URL, "APRÈS (dev .200, corrigé)", expect_fix=True)
    ok = all(RESULTS)
    print(f"\n=== {sum(RESULTS)}/{len(RESULTS)} assertions OK ===")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
