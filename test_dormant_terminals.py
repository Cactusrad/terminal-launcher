#!/usr/bin/env python3
"""
Vérifie le fix structurel du respawn des terminaux (TODO « fix structurel respawn »).

Bug d'origine (incident 2026-06-11, « terminaux qui réouvrent tout seuls ») :
au chargement de la page, l'app reconnectait le WebSocket de CHAQUE onglet
sauvegardé sans vérifier que sa session dtach existait encore. Le terminal-server
recrée la session à la demande et relance `claude` → respawn fantôme.

Fix : un onglet dont la session dtach est morte au chargement est rendu
« endormi » (placeholder, AUCUN WebSocket). La session n'est (re)lancée que
lorsque l'utilisateur réveille l'onglet explicitement (clic).

Méthode (hermétique, ne crée AUCUNE vraie session) :
  - window.WebSocket est remplacé par un stub qui ENREGISTRE l'URL de chaque
    tentative de connexion mais n'ouvre jamais de vraie socket. Donc même contre
    le vieux code de .100, aucun terminal réel n'est ressuscité.
  - /api/terminal/state est mocké pour renvoyer UN onglet pointant sur une fausse
    session morte ; l'endpoint des sessions actives renvoie une liste vide.

Assertions :
  A. AVANT (.100, vieux code) : au chargement, un WS est ouvert vers la session
     morte → RESPAWN. L'assertion « aucun WS vers la session morte » ÉCHOUE.
  B. APRÈS (.200, corrigé)   : au chargement, AUCUN WS vers la session morte ;
     l'onglet est marqué dormant (window.dormantTabs + badge 💤).
  C. APRÈS (.200) : un clic sur l'onglet endormi le RÉVEILLE → un WS est alors
     ouvert vers la session (respawn intentionnel, au clic uniquement).

Usage : python3 test_dormant_terminals.py
"""

import sys
import time
from playwright.sync_api import sync_playwright

DEV_URL = "https://192.168.1.200"   # corrigé
PROD_URL = "https://192.168.1.100"  # vieux code = état AVANT

DEAD_SESSION = "claude_VERIFYDORMANT_deadsession"
DEAD_TAB_ID = "tab_verify_dormant"

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f" — {detail}" if detail else ""))


# Stub WebSocket : enregistre l'URL, n'ouvre jamais de vraie connexion.
WS_STUB = """
window.__wsUrls = [];
(function () {
  function FakeWS(url, protocols) {
    window.__wsUrls.push(url);
    this.url = url;
    this.readyState = 0; // CONNECTING, n'atteint jamais OPEN
    this.binaryType = 'blob';
    this.onopen = null; this.onmessage = null; this.onerror = null; this.onclose = null;
    this.send = function () {};
    this.close = function () { this.readyState = 3; };
    this.addEventListener = function () {};
    this.removeEventListener = function () {};
  }
  FakeWS.CONNECTING = 0; FakeWS.OPEN = 1; FakeWS.CLOSING = 2; FakeWS.CLOSED = 3;
  FakeWS.prototype.CONNECTING = 0; FakeWS.prototype.OPEN = 1;
  FakeWS.prototype.CLOSING = 2; FakeWS.prototype.CLOSED = 3;
  window.WebSocket = FakeWS;
})();
"""

MOCK_STATE = {
    "tabs": [{
        "id": DEAD_TAB_ID,
        "name": "VERIFY-DORMANT",
        "type": "claude",
        "project": "terminal-launcher",
        "tmuxSession": DEAD_SESSION,
        "command": "claude",
        "createdAt": 1700000000000,
        "order": 1,
    }],
    "activeTabId": DEAD_TAB_ID,
    "viewMode": "tabs",
    "dismissedSessions": [],
}


def setup_routes(page):
    import json

    def route_state(route):
        if route.request.method == "POST":
            route.fulfill(status=200, content_type="application/json", body="{}")
        else:
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps(MOCK_STATE))

    def route_empty_sessions(route):
        route.fulfill(status=200, content_type="application/json",
                      body='{"sessions": []}')

    page.route("**/api/terminal/state", route_state)
    page.route("**/terminal-api/sessions", route_empty_sessions)
    page.route("**/api/terminal/sessions", route_empty_sessions)


DESKTOP_TAB = f'#terminalTabs .terminal-tab[data-tab-id="{DEAD_TAB_ID}"]'


def login_terminals(page, base_url):
    page.goto(base_url, wait_until="domcontentloaded")
    page.wait_for_selector(".login-user-btn", timeout=15000)
    btn = page.locator(".login-user-btn", has_text="mohamed").first
    if btn.count() == 0:
        btn = page.locator(".login-user-btn").first
    btn.click()
    # Atterrissage par défaut sur la vue Terminaux. L'onglet est rendu en double
    # (barre desktop #terminalTabs + barre mobile) → scoper au desktop, attendre
    # « attached » (l'une des deux copies est masquée selon le layout).
    page.wait_for_selector(DESKTOP_TAB, state="attached", timeout=15000)
    time.sleep(2)  # laisser initTerminalManager terminer la boucle loadTerminal


def dead_ws_count(page):
    return page.evaluate(
        "(s) => (window.__wsUrls || []).filter(u => u.includes(s)).length",
        DEAD_SESSION,
    )


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()

        # ---- A. AVANT : .100 (vieux code) ----
        print("\n[A] Prod .100 — état AVANT le fix (vieux code)")
        ctx = browser.new_context(ignore_https_errors=True)
        page = ctx.new_page()
        page.add_init_script(WS_STUB)
        setup_routes(page)
        try:
            login_terminals(page, PROD_URL)
            n = dead_ws_count(page)
            # Le vieux code ouvre un WS vers la session morte au chargement (respawn).
            check("AVANT — WS ouvert vers la session morte au load (bug présent)",
                  n >= 1, f"ws_morte_au_load={n} (attendu >=1)")
        except Exception as e:
            check("AVANT — exécutable sur .100", False, str(e)[:120])
        ctx.close()

        # ---- B. APRÈS : .200 (corrigé) — pas de respawn au load ----
        print("\n[B] Dev .200 — APRÈS le fix : aucun respawn au chargement")
        ctx = browser.new_context(ignore_https_errors=True)
        page = ctx.new_page()
        page.add_init_script(WS_STUB)
        setup_routes(page)
        login_terminals(page, DEV_URL)

        n_load = dead_ws_count(page)
        check("APRÈS — AUCUN WS vers la session morte au load (pas de respawn)",
              n_load == 0, f"ws_morte_au_load={n_load} (attendu 0)")

        is_dormant = page.evaluate(
            "(id) => (typeof dormantTabs !== 'undefined') && dormantTabs.has(id)",
            DEAD_TAB_ID,
        )
        check("APRÈS — onglet marqué dormant (window.dormantTabs)", is_dormant)

        has_badge = page.evaluate(
            f"() => !!document.querySelector('{DESKTOP_TAB} .tab-dormant')"
        )
        check("APRÈS — badge 💤 visible sur l'onglet", has_badge)

        has_placeholder = page.evaluate(
            f'() => !!document.querySelector(\'.terminal-div[data-tab-id="{DEAD_TAB_ID}"] .terminal-dormant\')'
        )
        check("APRÈS — placeholder « Session endormie » dans le pane", has_placeholder)

        # ---- C. APRÈS : .200 — réveil au clic ----
        print("\n[C] Dev .200 — réveil explicite au clic")
        page.locator(DESKTOP_TAB).first.click()
        time.sleep(1.5)
        n_after_click = dead_ws_count(page)
        check("APRÈS — clic réveille l'onglet → WS ouvert (respawn intentionnel)",
              n_after_click >= 1, f"ws_morte_apres_clic={n_after_click} (attendu >=1)")
        still_dormant = page.evaluate(
            "(id) => (typeof dormantTabs !== 'undefined') && dormantTabs.has(id)",
            DEAD_TAB_ID,
        )
        check("APRÈS — onglet n'est plus dormant après réveil", not still_dormant)

        ctx.close()
        browser.close()

    print("\n" + "=" * 60)
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    total = len(RESULTS)
    print(f"RÉSULTAT : {passed}/{total} assertions PASS")
    failed = [n for n, ok, _ in RESULTS if not ok]
    if failed:
        print("ÉCHECS :")
        for n in failed:
            print(f"  - {n}")
        sys.exit(1)
    print("Toutes les assertions passent.")
    sys.exit(0)


if __name__ == "__main__":
    main()
