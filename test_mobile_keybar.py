#!/usr/bin/env python3
"""
Vérifie la barre de touches tactile (Esc/Tab/flèches) sur iPhone/iPad.

Bug d'origine : le clavier virtuel iOS n'a ni Esc, ni Tab, ni flèches —
impossible de répondre aux prompts interactifs (Claude Code) dans le terminal.

Assertions :
  A. AVANT (prod .100, sans le fix)  : #terminalKeybar absent du DOM.
  B. APRÈS (dev .200, avec le fix)   : iPhone 14 WebKit — keybar visible,
     chaque touche tapée arrive au PTY (prouvé par `cat -v` qui affiche
     ^[ pour Esc, ^I pour Tab, ^[[A pour ↑, ^[[Z pour Shift+Tab, ^C interrompt).
  C. iPad (gen 7) WebKit : keybar visible (layout tablette > 768px).
  D. Desktop Chromium (souris) : keybar masquée.

Usage : python3 test_mobile_keybar.py
"""

import sys
import time
from playwright.sync_api import sync_playwright

DEV_URL = "https://192.168.1.200"
PROD_URL = "https://192.168.1.100"
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f" — {detail}" if detail else ""))


def login(page):
    # IMPORTANT : se logger en mohamed, JAMAIS en pierre — l'app restaure les
    # onglets sauvegardés du user et le terminal-server RECRÉE les sessions
    # dtach mortes à la connexion WS (respawn de `claude`). Un test loggé en
    # pierre ressuscite les terminaux qu'il vient de fermer (incident 2026-06-11).
    page.goto(DEV_URL, wait_until="domcontentloaded")
    page.wait_for_selector(".login-user-btn", timeout=15000)
    page.locator(".login-user-btn", has_text="mohamed").first.click()
    # Atterrissage par défaut sur la vue Terminaux
    page.wait_for_selector("#terminalKeybar", state="attached", timeout=15000)
    time.sleep(1.5)


def buffer_text(page):
    return page.evaluate("""() => {
        const inst = terminalInstances.get(activeTerminalTabId);
        if (!inst) return '';
        const buf = inst.terminal.buffer.active;
        let out = [];
        for (let i = 0; i < buf.length; i++) {
            const line = buf.getLine(i);
            if (line) out.push(line.translateToString(true));
        }
        return out.join('\\n');
    }""")


def main():
    with sync_playwright() as p:
        # ---- A. AVANT : prod .100 (v1.0.7, sans le fix) ----
        print("\n[A] Prod .100 (état AVANT le fix)")
        iphone = p.devices["iPhone 14"]
        browser = p.webkit.launch()
        ctx = browser.new_context(**iphone, ignore_https_errors=True)
        page = ctx.new_page()
        page.goto(PROD_URL, wait_until="domcontentloaded")
        time.sleep(2)
        present = page.evaluate("() => !!document.getElementById('terminalKeybar')")
        check("AVANT — keybar absente sur prod (bug présent)", not present,
              f"présente={present}")
        ctx.close()

        # ---- B. APRÈS : dev .200, iPhone 14 ----
        print("\n[B] Dev .200 — iPhone 14 (WebKit)")
        ctx = browser.new_context(**iphone, ignore_https_errors=True)
        page = ctx.new_page()
        login(page)

        coarse = page.evaluate("() => matchMedia('(pointer: coarse)').matches")
        check("media (pointer: coarse) émulé", coarse)
        visible = page.locator("#terminalKeybar").is_visible()
        check("keybar visible sur iPhone", visible)

        # Ouvre un bash : sidebar mobile → bouton Nouveau Bash
        page.locator(".mobile-menu-btn").first.click()
        page.wait_for_selector(".terminal-sidebar.mobile-open", timeout=5000)
        page.locator(".sidebar-btn[title='Nouveau Bash']").click()
        page.wait_for_function(
            "() => activeTerminalTabId && "
            "terminalInstances.get(activeTerminalTabId)?.ws?.readyState === 1",
            timeout=15000)
        time.sleep(2)

        # Lance cat -vt pour révéler les séquences reçues par le PTY
        # (-t : affiche aussi les tabs en ^I, que -v seul laisse passer)
        page.evaluate("""() => {
            const inst = terminalInstances.get(activeTerminalTabId);
            inst.ws.send(new TextEncoder().encode('cat -vt\\n'));
        }""")
        time.sleep(1.5)

        for key in ("esc", "tab", "up", "shifttab"):
            page.tap(f"#terminalKeybar button[data-key='{key}']")
            time.sleep(0.4)
        # Enter : cat est en mode ligne — il ne relit (et ne transforme en ^X)
        # la ligne qu'au newline. L'écho TTY seul affiche le tab en blanc.
        page.evaluate("""() => {
            const inst = terminalInstances.get(activeTerminalTabId);
            inst.ws.send(new TextEncoder().encode('\\n'));
        }""")
        time.sleep(1.5)

        buf = buffer_text(page)
        check("Esc reçu par le PTY (^[)", "^[" in buf)
        check("Tab reçu par le PTY (^I)", "^I" in buf)
        check("Flèche ↑ reçue par le PTY (^[[A)", "^[[A" in buf)
        check("Shift+Tab reçu par le PTY (^[[Z)", "^[[Z" in buf)

        # ^C interrompt cat → le prompt revient
        page.tap("#terminalKeybar button[data-key='ctrlc']")
        time.sleep(1.5)
        buf2 = buffer_text(page)
        check("^C interrompt cat (^C affiché)", "^C" in buf2)

        page.screenshot(path="screenshots/keybar_iphone14.png")

        # Nettoyage : exit → session_ended ferme l'onglet
        page.evaluate("""() => {
            const inst = terminalInstances.get(activeTerminalTabId);
            inst.ws.send(new TextEncoder().encode('exit\\n'));
        }""")
        time.sleep(2)
        ctx.close()

        # ---- C. iPad (gen 7) ----
        print("\n[C] Dev .200 — iPad gen 7 (WebKit)")
        ipad = p.devices["iPad (gen 7)"]
        ctx = browser.new_context(**ipad, ignore_https_errors=True)
        page = ctx.new_page()
        login(page)
        check("keybar visible sur iPad", page.locator("#terminalKeybar").is_visible())
        page.screenshot(path="screenshots/keybar_ipad.png")
        ctx.close()
        browser.close()

        # ---- D. Desktop (souris) ----
        print("\n[D] Dev .200 — Desktop Chromium")
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1440, "height": 900},
                                  ignore_https_errors=True)
        page = ctx.new_page()
        login(page)
        check("keybar masquée sur desktop", not page.locator("#terminalKeybar").is_visible())
        ctx.close()
        browser.close()

    failed = [r for r in RESULTS if not r[1]]
    print(f"\n{'=' * 50}\n{len(RESULTS) - len(failed)}/{len(RESULTS)} assertions PASS")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
