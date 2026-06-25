#!/usr/bin/env python3
"""
Vérifie le fix de la molette dans le terminal (bug du 25 juin 2026 : « je ne peux
plus défiler, la roulette de la souris ne fonctionne plus »).

Cause : le fix v1.0.13 (stripMouseTracking) retire le mouse tracking du flux pour
préserver la copie-par-sélection. Mais Claude Code tourne en ALTERNATE SCREEN
(CSI ? 1049 h — vérifié dans /tmp/terminal-logs/*.log : 1049h sans 1049l) → aucun
scrollback xterm. Sans mouse tracking, xterm ne transmet plus la molette à Claude
ET n'a rien à défiler localement → molette morte.

Fix : on retient l'intention souris de l'appli depuis le flux BRUT
(updateAppMouseState) et un handler `wheel` réinjecte les rapports SGR molette
(\\x1b[<64;..M haut / \\x1b[<65;..M bas) que Claude attend — à l'identique de ce
que xterm émettrait en mode brut — tout en gardant la sélection-souris (mouse=none).

Méthode (hermétique, AUCUNE vraie session) :
  - window.WebSocket remplacé par un stub OUVERT qui ENREGISTRE chaque send()
    (décodé) et permet de pousser des données via window.__pushWs().
  - on crée un onglet via la vraie fonction createTerminalTab() → loadTerminal()
    attache le VRAI handler molette inline.
  - on pousse la séquence d'init RÉELLE de Claude (alt-screen + 1000/1002/1003/1006)
    dans ws.onmessage → updateAppMouseState met _appWantsMouse=true.
  - on dispatch un wheel (deltaY<0) sur .terminal-wrapper.

Assertions :
  APRÈS (.200, corrigé) : un rapport \\x1b[<64;1;1M est envoyé au WS.
  AVANT (.100, vieux code) : AUCUN rapport molette n'est envoyé (la même
    assertion ÉCHOUE) → prouve la régression et le fix.
  Non-régression : sans intention souris (bash), la molette n'injecte rien.

Usage : python3.12 test_wheel_scroll.py [after|before|both]
"""
import sys
from playwright.sync_api import sync_playwright

AFTER_URL = "https://192.168.1.200"   # code corrigé
BEFORE_URL = "https://192.168.1.100"  # prod, vieux code (état AVANT)

WS_STUB = r"""
window.__wsSent = [];
window.__wsInstances = [];
(function () {
  const RealEncoderDecode = (data) => {
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
  FakeWS.prototype.send = function (data) { window.__wsSent.push(RealEncoderDecode(data)); };
  FakeWS.prototype.close = function () { this.readyState = 3; if (this.onclose) this.onclose({}); };
  FakeWS.CONNECTING = 0; FakeWS.OPEN = 1; FakeWS.CLOSING = 2; FakeWS.CLOSED = 3;
  window.WebSocket = FakeWS;
})();
// pousse un flux (string) dans le dernier WS comme un message binaire du serveur
window.__pushWs = function (s) {
  const ws = window.__wsInstances[window.__wsInstances.length - 1];
  if (!ws || !ws.onmessage) return false;
  const buf = new TextEncoder().encode(s).buffer;
  ws.onmessage({ data: buf });
  return true;
};
"""

# Séquence d'init RÉELLE de Claude Code (capturée dans /tmp/terminal-logs)
CLAUDE_INIT = "\x1b[?1049h\x1b[?1000h\x1b[?1002h\x1b[?1003h\x1b[?1006h"

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f" — {detail}" if detail else ""))


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
        page.wait_for_timeout(800)

        # --- Cas 1 : appli AVEC mouse tracking (Claude) ---
        page.evaluate("window.__wsSent = []; createTerminalTab('claude', 'VERIFYWHEEL');")
        page.wait_for_timeout(300)
        pushed = page.evaluate("(s) => window.__pushWs(s)", CLAUDE_INIT)
        check("flux Claude poussé dans le WS", pushed is True, str(pushed))
        page.wait_for_timeout(150)

        # état détecté sur l'instance terminal réelle
        want = page.evaluate("""() => {
            const inst = [...terminalInstances.values()].find(i => i.terminal);
            return inst ? { wantsMouse: inst.terminal._appWantsMouse, sgr: inst.terminal._mouseSGR,
                            mouse: inst.terminal.modes.mouseTrackingMode } : null;
        }""")
        print("     état terminal:", want)
        if expect_fix:
            check("intention souris détectée (_appWantsMouse=true)", bool(want) and want["wantsMouse"] is True, str(want))
            check("sélection préservée (mouseTrackingMode=none)", bool(want) and want["mouse"] == "none", str(want))

        # dispatch molette HAUT sur le wrapper de l'onglet actif
        page.evaluate("window.__wsSent = [];")
        dispatched = page.evaluate("""() => {
            const w = document.querySelector('.terminal-div.active .terminal-wrapper')
                   || document.querySelector('.terminal-wrapper');
            if (!w) return 'no-wrapper';
            w.dispatchEvent(new WheelEvent('wheel', {deltaY:-120, deltaMode:0, bubbles:true, cancelable:true}));
            return 'ok';
        }""")
        check("wrapper terminal trouvé pour dispatch", dispatched == "ok", dispatched)
        page.wait_for_timeout(100)
        sent = page.evaluate("window.__wsSent.slice()")
        wheel_up = [s for s in sent if s == "\x1b[<64;1;1M"]
        print("     octets envoyés au WS après molette:", [repr(s) for s in sent])
        check(f"molette HAUT → rapport SGR \\x1b[<64;1;1M envoyé à l'appli  (attendu fix={expect_fix})",
              (len(wheel_up) >= 1) == expect_fix,
              f"{len(wheel_up)} rapport(s)")

        # --- Cas 2 (fix only) : non-régression bash, pas d'intention souris ---
        if expect_fix:
            page.evaluate("window.__wsSent = []; createTerminalTab('bash', 'VERIFYWHEELBASH');")
            page.wait_for_timeout(300)
            # AUCUN push de mouse-enable → _appWantsMouse reste falsy
            page.evaluate("window.__wsSent = [];")
            page.evaluate("""() => {
                const w = document.querySelector('.terminal-div.active .terminal-wrapper')
                       || document.querySelector('.terminal-wrapper');
                w && w.dispatchEvent(new WheelEvent('wheel', {deltaY:-120, deltaMode:0, bubbles:true, cancelable:true}));
            }""")
            page.wait_for_timeout(100)
            sent2 = page.evaluate("window.__wsSent.slice()")
            sgr2 = [s for s in sent2 if s in ("\x1b[<64;1;1M", "\x1b[<65;1;1M")]
            check("non-régression: bash (pas d'intention souris) → AUCUN rapport molette injecté (scroll xterm natif)",
                  len(sgr2) == 0, f"{len(sgr2)} rapport(s)")

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
