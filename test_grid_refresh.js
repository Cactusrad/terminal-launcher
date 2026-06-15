// Prouve que rafraîchir un terminal en mode GRILLE ne le déplace pas en dernière
// position. WS vivant (sessions de pierre déjà actives = lecture seule, pas de
// relance). Assertion : l'ordre DOM des panes est identique avant/après refresh
// d'un pane du milieu.
const { chromium } = require('playwright');
const BASE = 'https://192.168.1.200';

(async () => {
    const browser = await chromium.launch();
    const ctx = await browser.newContext({ ignoreHTTPSErrors: true });
    await ctx.request.post(`${BASE}/api/auth/select-user`, { data: { username: 'pierre' }, ignoreHTTPSErrors: true });
    const page = await ctx.newPage();
    await page.goto(BASE, { waitUntil: 'networkidle' });
    await page.waitForTimeout(2500);

    // Passer en mode grille si on n'y est pas.
    await page.evaluate(() => {
        const c = document.getElementById('terminalContainer');
        if (c && !c.classList.contains('grid-view') && typeof toggleViewMode === 'function') toggleViewMode();
    });
    await page.waitForTimeout(1500);

    const domOrder = () => page.evaluate(() =>
        [...document.querySelectorAll('#terminalContainer .terminal-div')].map(d => d.dataset.tabId));

    const before = await domOrder();
    if (before.length < 3) { console.log('SKIP: moins de 3 panes en grille (', before.length, ')'); await browser.close(); process.exit(2); }

    const midIdx = Math.floor(before.length / 2);
    const midId = before[midIdx];
    console.log('panes:', before.length, '| refresh du pane index', midIdx, '(', midId, ')');

    // Clic sur le bouton ↻ de ce pane précis.
    await page.evaluate((id) => {
        const div = document.querySelector(`.terminal-div[data-tab-id="${id}"]`);
        const btn = div && [...div.querySelectorAll('.grid-term-actions button')].find(b => b.title === 'Rafraîchir');
        if (btn) btn.click();
    }, midId);
    await page.waitForTimeout(2500);

    const after = await domOrder();
    const newIdx = after.indexOf(midId);
    console.log('avant :', before.map(s => s.slice(-6)).join(' '));
    console.log('après :', after.map(s => s.slice(-6)).join(' '));
    console.log(`pane rafraîchi : index ${midIdx} -> ${newIdx} (dernier index = ${after.length - 1})`);

    const samePos = newIdx === midIdx;
    const movedLast = newIdx === after.length - 1 && midIdx !== after.length - 1;
    console.log(samePos
        ? 'PASS: le pane rafraîchi est resté à sa position'
        : (movedLast ? 'FAIL: le pane rafraîchi a sauté en DERNIÈRE position (bug)' : `FAIL: position changée ${midIdx}->${newIdx}`));

    await browser.close();
    process.exit(samePos ? 0 : 1);
})();
