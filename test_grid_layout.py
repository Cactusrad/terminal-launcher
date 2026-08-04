#!/usr/bin/env python3
"""
Vérifie le fix BUG-161 : « les 6 terminaux ne partagent pas correctement
l'espace, ça devrait être 3 colonnes de 2 lignes ».

Cause : la media query `@media (min-width: 1921px)` (héritée du layout grille
initial, commit 71f69e5) redéfinissait `grid-cols-3` en 4 colonnes sur viewport
large (moniteur >1920px CSS, ou zoom navigateur <100% sur un 1920). Le JS
calcule pourtant ceil(sqrt(6)) = 3 colonnes → la grille rendait 4+2 panes avec
deux cellules vides au lieu de 3×2.

Fix 1 : media query supprimée — la classe grid-cols-N posée par applyViewMode()
fait foi à toutes les largeurs desktop.
Fix 2 (cosmétique, même screenshot) : le badge numéroté des panes est renuméroté
dans applyViewMode() — il était figé à la création (tabIndex+1) et gardait des
trous après une fermeture d'onglet (badges 1,2,3,4,6,7 sans 5).

Méthode (hermétique, AUCUNE vraie session) :
  - window.WebSocket stubbé (aucune connexion réelle), saveTerminalState
    neutralisé (aucune écriture dans le terminalState de mohamed).
  - viewport 2200×1000 → déclenche la media query fautive sur le vieux code.
  - 6 onglets créés via la vraie createTerminalTab(), vue grille via la vraie
    applyViewMode().

Assertions :
  APRÈS (.200, corrigé) : 6 onglets → 3 pistes de colonnes, panes sur 2 lignes ;
    fermeture d'un onglet du milieu → badges renumérotés sans trou.
  AVANT (prod .100, vieux code) : les mêmes assertions ÉCHOUENT (4 colonnes,
    badge troué) → prouve le bug et le fix.
  Non-régression : 4 onglets → 2 colonnes ; 1 onglet → 1 colonne.

Usage : python3.12 test_grid_layout.py [after|before|both]
"""
import sys
from playwright.sync_api import sync_playwright

AFTER_URL = "https://192.168.1.200"   # code corrigé
BEFORE_URL = "https://192.168.1.100"  # prod, vieux code (état AVANT)

WS_STUB = r"""
window.__wsInstances = [];
(function () {
  function FakeWS(url) {
    this.url = url;
    this.readyState = 1;
    this.binaryType = 'blob';
    this.onopen = null; this.onmessage = null; this.onerror = null; this.onclose = null;
    window.__wsInstances.push(this);
    const self = this;
    setTimeout(() => { if (self.onopen) self.onopen({}); }, 0);
  }
  FakeWS.prototype.send = function () {};
  FakeWS.prototype.close = function () { this.readyState = 3; if (this.onclose) this.onclose({}); };
  FakeWS.CONNECTING = 0; FakeWS.OPEN = 1; FakeWS.CLOSING = 2; FakeWS.CLOSED = 3;
  window.WebSocket = FakeWS;
})();
"""

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f" — {detail}" if detail else ""))


def grid_state(page):
    """Colonnes calculées de la grille + géométrie et badges des panes visibles."""
    return page.evaluate("""() => {
        const c = document.getElementById('terminalContainer');
        const cols = getComputedStyle(c).gridTemplateColumns.split(' ').filter(Boolean);
        const panes = [...c.querySelectorAll('.terminal-div')]
            .filter(d => getComputedStyle(d).display !== 'none')
            .map(d => {
                const r = d.getBoundingClientRect();
                const n = d.querySelector('.grid-term-number');
                return { top: Math.round(r.top), left: Math.round(r.left),
                         width: Math.round(r.width),
                         badge: n ? n.textContent.trim() : null };
            });
        const tops = [...new Set(panes.map(p => p.top))].sort((a, b) => a - b);
        const lefts = [...new Set(panes.map(p => p.left))].sort((a, b) => a - b);
        return { colCount: cols.length, cols, className: c.className,
                 rendered: panes.every(p => p.width > 0),
                 rowTops: tops.length, colLefts: lefts.length,
                 rowSizes: tops.map(t => panes.filter(p => p.top === t).length),
                 badges: panes.map(p => p.badge), paneCount: panes.length };
    }""")


def run(url, label, expect_fix):
    print(f"\n=== {label} ({url}) — fix attendu: {expect_fix} ===")
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--ignore-certificate-errors"])
        # 2200px CSS de large : déclenche la media query min-width:1921px du vieux code
        ctx = browser.new_context(ignore_https_errors=True, viewport={"width": 2200, "height": 1000})
        page = ctx.new_page()
        page.add_init_script(WS_STUB)
        page.goto(url, wait_until="domcontentloaded")
        # Auth LAN sans mot de passe : mohamed (jamais pierre en E2E)
        page.evaluate("""async () => {
            await fetch('/api/auth/select-user', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({username:'mohamed'})});
        }""")
        page.reload(wait_until="domcontentloaded")
        page.wait_for_function("typeof createTerminalTab === 'function' && typeof applyViewMode === 'function'", timeout=15000)
        page.wait_for_timeout(800)

        # Hermétique : aucune écriture d'état serveur, aucun onglet préexistant,
        # et vue Terminaux forcée (le conteneur doit être rendu pour mesurer).
        page.evaluate("""() => {
            window.saveTerminalState = () => {};
            terminalTabs.length = 0;
            document.querySelectorAll('.terminal-div').forEach(d => d.remove());
            activeTerminalTabId = null;
            setCurrentPageId('terminals');
        }""")
        page.wait_for_timeout(300)

        # --- Cas 1 : 6 terminaux en vue grille → 3 colonnes × 2 lignes ---
        page.evaluate("""() => {
            for (let i = 1; i <= 6; i++) createTerminalTab('bash', 'VERIFYGRID' + i);
            viewMode = 'grid';
            applyViewMode();
        }""")
        page.wait_for_timeout(400)
        st = grid_state(page)
        print("     état grille (6 onglets):", st)
        check("6 onglets → classe grid-cols-3 posée par le JS",
              "grid-cols-3" in st["className"], st["className"])
        check("panes rendus et mesurables (vue Terminaux visible)",
              st["rendered"] and st["paneCount"] == 6, str(st))
        check(f"6 onglets → 3 pistes de colonnes CALCULÉES à 2200px  (attendu fix={expect_fix})",
              (st["colCount"] == 3) == expect_fix, f"{st['colCount']} colonnes: {st['cols']}")
        check(f"6 onglets → géométrie 3 colonnes × 2 lignes équilibrées (3+3)  (attendu fix={expect_fix})",
              (st["colLefts"] == 3 and st["rowSizes"] == [3, 3]) == expect_fix,
              f"{st['colLefts']} col x, lignes {st['rowSizes']}")

        # --- Cas 2 : fermeture du pane 5 → badges renumérotés sans trou ---
        page.evaluate("""() => {
            const tab = terminalTabs[4];  // 5e onglet
            disposeTerminal(tab.id);
            document.querySelector(`.terminal-div[data-tab-id="${tab.id}"]`)?.remove();
            terminalTabs.splice(4, 1);
            applyViewMode();
        }""")
        page.wait_for_timeout(300)
        st2 = grid_state(page)
        print("     badges après fermeture du 5e:", st2["badges"])
        check(f"fermeture d'un onglet du milieu → badges 1..5 sans trou  (attendu fix={expect_fix})",
              (st2["badges"] == ["1", "2", "3", "4", "5"]) == expect_fix, str(st2["badges"]))

        if expect_fix:
            # --- Non-régression : les autres tailles gardent leur layout ---
            page.evaluate("""() => {
                while (terminalTabs.length > 4) {
                    const t = terminalTabs.pop();
                    disposeTerminal(t.id);
                    document.querySelector(`.terminal-div[data-tab-id="${t.id}"]`)?.remove();
                }
                applyViewMode();
            }""")
            page.wait_for_timeout(200)
            st4 = grid_state(page)
            check("non-régression: 4 onglets → 2 colonnes", st4["colCount"] == 2, str(st4["cols"]))
            page.evaluate("""() => {
                while (terminalTabs.length > 1) {
                    const t = terminalTabs.pop();
                    disposeTerminal(t.id);
                    document.querySelector(`.terminal-div[data-tab-id="${t.id}"]`)?.remove();
                }
                applyViewMode();
            }""")
            page.wait_for_timeout(200)
            st1 = grid_state(page)
            check("non-régression: 1 onglet → 1 colonne", st1["colCount"] == 1, str(st1["cols"]))

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
