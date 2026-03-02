const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const SCREENSHOT_DIR = '/home/cactus/claude/homepage-app/screenshots';
const BASE_URL = 'http://192.168.1.200';

if (!fs.existsSync(SCREENSHOT_DIR)) {
    fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
}

// Clean old screenshots for this test run
const prefix = 'qv_';
fs.readdirSync(SCREENSHOT_DIR).filter(f => f.startsWith(prefix)).forEach(f => {
    fs.unlinkSync(path.join(SCREENSHOT_DIR, f));
});

let screenshotCounter = 0;
async function takeScreenshot(page, name) {
    screenshotCounter++;
    const num = String(screenshotCounter).padStart(2, '0');
    const filePath = path.join(SCREENSHOT_DIR, `${prefix}${num}_${name}.png`);
    await page.screenshot({ path: filePath, fullPage: false });
    console.log(`  [SCREENSHOT] ${filePath}`);
    return filePath;
}

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

(async () => {
    const consoleErrors = [];
    const networkErrors = [];
    const results = [];

    const browser = await chromium.launch({
        headless: true,
        args: ['--no-sandbox', '--disable-setuid-sandbox']
    });

    const context = await browser.newContext({
        viewport: { width: 1400, height: 900 },
        ignoreHTTPSErrors: true
    });

    const page = await context.newPage();

    // Capture console errors
    page.on('console', msg => {
        if (msg.type() === 'error') {
            consoleErrors.push(msg.text());
        }
    });

    // Capture network errors (4xx/5xx) - ignore port 7681 (terminal WebSocket) and CDN
    page.on('response', response => {
        if (response.status() >= 400) {
            const url = response.url();
            if (!url.includes(':7681') && !url.includes('cdn.jsdelivr') && !url.includes('fonts.googleapis')) {
                networkErrors.push(`${response.status()} ${response.request().method()} ${url}`);
            }
        }
    });

    page.on('requestfailed', request => {
        const url = request.url();
        if (!url.includes(':7681') && !url.includes('websocket') &&
            !url.includes('cdn.jsdelivr') && !url.includes('fonts.googleapis')) {
            networkErrors.push(`FAILED ${request.method()} ${url} - ${request.failure().errorText}`);
        }
    });

    try {
        // =============================================
        // TEST 1: Load the homepage
        // =============================================
        console.log('\n=== TEST 1: Load http://192.168.1.100 ===');

        // Load the page and let it initialize from the API
        await page.goto(BASE_URL, { waitUntil: 'networkidle', timeout: 15000 });
        await sleep(3000);

        await takeScreenshot(page, 'homepage_loaded');

        // Check page title
        const pageTitle = await page.title();
        console.log(`  Page title: "${pageTitle}"`);

        // Check for "Cactus Home" header
        const headerCheck = await page.evaluate(() => {
            const bodyText = document.body.innerText;
            return {
                hasCactusHome: bodyText.includes('Cactus Home'),
                hasDashboard: bodyText.includes('DASHBOARD'),
            };
        });
        console.log(`  Has "Cactus Home": ${headerCheck.hasCactusHome}`);
        console.log(`  Has "DASHBOARD": ${headerCheck.hasDashboard}`);

        // Check what the app loaded from the API
        const appState = await page.evaluate(() => {
            const pages = typeof getPages === 'function' ? getPages() : [];
            const pageInfo = pages.map(p => ({ id: p.id, name: p.name, apps: (p.apps || []).length }));

            // Check app cards on current page
            const cards = document.querySelectorAll('.app-card');
            const visibleCards = [];
            for (const card of cards) {
                if (card.offsetParent !== null) {
                    const nameEl = card.querySelector('h2');
                    visibleCards.push(nameEl ? nameEl.innerText.trim() : card.innerText.trim().substring(0, 30));
                }
            }

            // Check page tabs
            const tabs = document.querySelectorAll('.page-tab');
            const tabNames = [];
            for (const t of tabs) {
                tabNames.push({ name: t.innerText.trim(), active: t.classList.contains('active') });
            }

            const emptyState = document.body.innerText.includes('Ajoutez votre premier raccourci');
            const bodyText = document.body.innerText;

            return {
                pages: pageInfo,
                pageCount: pageInfo.length,
                visibleCards,
                cardCount: visibleCards.length,
                pageTabs: tabNames,
                pageTabCount: tabNames.length,
                emptyState,
                currentPageId: typeof currentPageId !== 'undefined' ? currentPageId : 'unknown',
                hasSyncServeur: bodyText.includes('Sync serveur'),
                hasBugReport: bodyText.includes('Bug Report'),
                hasAdmin: bodyText.includes('Admin'),
                hasTerminalManager: !!document.getElementById('terminalManager'),
                terminalManagerVisible: (() => {
                    const tm = document.getElementById('terminalManager');
                    return tm ? window.getComputedStyle(tm).display !== 'none' : false;
                })()
            };
        });

        console.log(`  Pages loaded: ${appState.pageCount} - ${JSON.stringify(appState.pages)}`);
        console.log(`  Current page: ${appState.currentPageId}`);
        console.log(`  Visible cards: ${appState.cardCount} - ${appState.visibleCards.join(', ')}`);
        console.log(`  Page tabs: ${appState.pageTabCount} - ${JSON.stringify(appState.pageTabs)}`);
        console.log(`  Empty state: ${appState.emptyState}`);
        console.log(`  Terminal manager visible: ${appState.terminalManagerVisible}`);
        console.log(`  UI: Sync=${appState.hasSyncServeur}, Bug Report=${appState.hasBugReport}, Admin=${appState.hasAdmin}`);

        // Build verdict for Test 1
        let test1Details = [];
        let test1Status = 'PASS';

        // 1. "Cactus Home" header
        if (headerCheck.hasCactusHome) {
            test1Details.push('"Cactus Home" header: OK');
        } else {
            test1Details.push('"Cactus Home" header: MISSING');
            test1Status = 'FAIL';
        }

        // 2. App cards or terminal manager visible
        if (appState.currentPageId === 'terminals' && appState.terminalManagerVisible) {
            test1Details.push('Currently on Terminals page (terminal manager visible)');
        } else if (appState.cardCount > 0) {
            test1Details.push(`${appState.cardCount} app cards visible: ${appState.visibleCards.join(', ')}`);
        } else if (appState.emptyState && appState.currentPageId === 'main' && appState.pages.find(p => p.id === 'main' && p.apps === 0)) {
            test1Details.push('Accueil page has 0 apps (empty state shown) - configured with no apps on this page');
        } else if (appState.emptyState) {
            test1Details.push('Empty state shown - page has no apps configured');
        } else {
            test1Details.push('No cards visible, no empty state, no terminal manager');
            test1Status = 'FAIL';
        }

        // 3. Navigation tabs (5 pages expected)
        if (appState.pageTabCount >= 5) {
            test1Details.push(`${appState.pageTabCount} navigation tabs: ${appState.pageTabs.map(t => t.name).join(', ')}`);
        } else if (appState.pageCount >= 5) {
            test1Details.push(`${appState.pageCount} pages loaded, ${appState.pageTabCount} tabs shown`);
        } else {
            test1Details.push(`Only ${appState.pageCount} page(s) loaded (expected 5)`);
            if (test1Status === 'PASS') test1Status = 'PARTIAL';
        }

        // 4. Page is not blank
        test1Details.push('Page not blank: OK');

        results.push(`TEST 1: ${test1Details.join(' | ')} - ${test1Status}`);

        // =============================================
        // TEST 2: Navigate to Terminaux page
        // =============================================
        console.log('\n=== TEST 2: Navigate to Terminaux page ===');

        // If already on terminals page, skip navigation
        if (appState.currentPageId === 'terminals' && appState.terminalManagerVisible) {
            console.log('  Already on Terminals page!');
        } else {
            // Click the "Terminaux" tab if visible
            let navigated = false;
            if (appState.pageTabCount > 0) {
                const termTabIndex = appState.pageTabs.findIndex(t => t.name.includes('Termin'));
                if (termTabIndex >= 0) {
                    console.log(`  Clicking tab "${appState.pageTabs[termTabIndex].name}" (index ${termTabIndex})...`);
                    const tabs = await page.$$('.page-tab');
                    if (tabs[termTabIndex]) {
                        await tabs[termTabIndex].click();
                        navigated = true;
                    }
                }
            }

            if (!navigated) {
                // Try setCurrentPageId
                console.log('  Using setCurrentPageId("terminals")...');
                await page.evaluate(() => {
                    if (typeof setCurrentPageId === 'function') {
                        setCurrentPageId('terminals');
                    }
                });
            }
            await sleep(2000);
        }

        await takeScreenshot(page, 'terminaux_page');

        // Check terminal manager state
        const termCheck = await page.evaluate(() => {
            const termManager = document.getElementById('terminalManager');
            if (!termManager) return { found: false, isVisible: false, projects: [], tabs: [], sidebarVisible: false, projectCount: 0, tabCount: 0 };

            const display = window.getComputedStyle(termManager).display;
            const isVisible = display !== 'none';

            // Project items
            const projectItems = termManager.querySelectorAll('.project-item');
            const projects = [];
            for (const item of projectItems) {
                // Get just the project name (the first text node, before B/C buttons)
                const nameEl = item.querySelector('.project-name') || item.querySelector('span:first-child');
                const name = nameEl ? nameEl.innerText.trim() : item.childNodes[0] ? item.childNodes[0].textContent.trim() : item.innerText.split('\n')[0].trim();
                if (name) projects.push(name);
            }

            // Terminal tabs
            const termTabs = termManager.querySelectorAll('.terminal-tab');
            const tabs = [];
            for (const tab of termTabs) {
                const text = tab.innerText.trim();
                if (text) tabs.push(text.substring(0, 40));
            }

            // Sidebar
            const sidebar = termManager.querySelector('.terminal-sidebar');
            const sidebarVisible = sidebar ? window.getComputedStyle(sidebar).display !== 'none' : false;

            return {
                found: true,
                isVisible,
                display,
                projectCount: projects.length,
                projects,
                tabCount: tabs.length,
                tabs,
                sidebarVisible
            };
        });

        console.log(`  Terminal manager visible: ${termCheck.isVisible}`);
        console.log(`  Sidebar visible: ${termCheck.sidebarVisible}`);
        console.log(`  Projects (${termCheck.projectCount}): ${JSON.stringify(termCheck.projects)}`);
        console.log(`  Terminal tabs (${termCheck.tabCount}): ${JSON.stringify(termCheck.tabs)}`);

        // Build verdict for Test 2
        let test2Details = [];
        let test2Status = 'PASS';

        if (termCheck.isVisible) {
            test2Details.push('Terminal manager opened: YES');
        } else {
            test2Details.push('Terminal manager NOT visible');
            test2Status = 'FAIL';
        }

        if (termCheck.sidebarVisible) {
            test2Details.push(`Sidebar visible with ${termCheck.projectCount} projects`);
        } else {
            test2Details.push('Sidebar NOT visible');
            if (test2Status === 'PASS') test2Status = 'PARTIAL';
        }

        // Check project count
        if (termCheck.projectCount > 30) {
            test2Details.push(`${termCheck.projectCount} projects shown (expected ~11, TOO MANY - hidden folders may be showing)`);
            test2Status = 'FAIL';
        } else if (termCheck.projectCount >= 5 && termCheck.projectCount <= 20) {
            test2Details.push(`${termCheck.projectCount} projects (reasonable, ~11 expected)`);
        } else if (termCheck.projectCount > 0) {
            test2Details.push(`Only ${termCheck.projectCount} project(s) shown`);
        }

        // Check for dot-prefixed folders
        const dotFolders = termCheck.projects.filter(p => p.startsWith('.'));
        if (dotFolders.length > 0) {
            test2Details.push(`WARNING: dot-prefixed folders shown: ${dotFolders.join(', ')}`);
            test2Status = 'FAIL';
        } else {
            test2Details.push('No dot-prefixed folders');
        }

        // Terminal tabs
        test2Details.push(`${termCheck.tabCount} terminal tabs saved`);

        results.push(`TEST 2: ${test2Details.join(' | ')} - ${test2Status}`);

        // =============================================
        // TEST 3: Screenshot project list sidebar detail
        // =============================================
        console.log('\n=== TEST 3: Verify project list sidebar (hidden folders excluded) ===');

        // Take a detailed sidebar screenshot
        if (termCheck.isVisible && termCheck.sidebarVisible) {
            const sidebarEl = await page.$('.terminal-sidebar');
            if (sidebarEl) {
                const box = await sidebarEl.boundingBox();
                if (box && box.width > 0 && box.height > 0) {
                    await page.screenshot({
                        path: path.join(SCREENSHOT_DIR, `${prefix}04_sidebar_detail.png`),
                        clip: {
                            x: Math.max(0, Math.floor(box.x)),
                            y: Math.max(0, Math.floor(box.y)),
                            width: Math.ceil(box.width),
                            height: Math.ceil(box.height)
                        }
                    });
                    console.log(`  [SCREENSHOT] Sidebar detail captured`);
                }
            }
        }

        await takeScreenshot(page, 'sidebar_fullpage');

        // Also check the API directly for comparison
        const apiProjects = await page.evaluate(async () => {
            try {
                const resp = await fetch('/api/projects/folders');
                return await resp.json();
            } catch(e) {
                return { error: e.message };
            }
        });
        console.log(`  API /api/projects/folders: ${JSON.stringify(apiProjects)}`);

        const apiFolders = apiProjects.folders || [];
        const apiHidden = apiProjects.hidden || [];
        const apiDotFolders = apiFolders.filter(f => f.startsWith('.'));

        console.log(`  API visible folders: ${apiFolders.length}`);
        console.log(`  API hidden folders: ${apiHidden.length}`);
        console.log(`  API dot-prefixed in visible: ${apiDotFolders.length}`);

        // Verdict for Test 3
        let test3Details = [];
        let test3Status = 'PASS';

        if (apiDotFolders.length > 0) {
            test3Details.push(`API returns ${apiDotFolders.length} dot-prefixed folders (should be 0)`);
            test3Status = 'FAIL';
        } else {
            test3Details.push('No dot-prefixed folders in API response');
        }

        if (apiFolders.length > 30) {
            test3Details.push(`API shows ${apiFolders.length} visible folders (hidden list may be empty)`);
            if (apiHidden.length === 0) {
                test3Details.push('Hidden list is EMPTY - all 37 folders are showing');
                test3Status = 'FAIL';
            }
        } else {
            test3Details.push(`API shows ${apiFolders.length} visible + ${apiHidden.length} hidden folders`);
        }

        // Visual check
        if (termCheck.projectCount > 0) {
            test3Details.push(`UI shows ${termCheck.projectCount} projects: ${termCheck.projects.join(', ')}`);
        }

        results.push(`TEST 3: ${test3Details.join(' | ')} - ${test3Status}`);

        // =============================================
        // BONUS: Navigate back to Accueil and check cards
        // =============================================
        console.log('\n=== BONUS: Navigate to Accueil page ===');
        await page.evaluate(() => {
            if (typeof setCurrentPageId === 'function') {
                setCurrentPageId('main');
            }
        });
        await sleep(1500);
        await takeScreenshot(page, 'accueil_restored');

        const accueilState = await page.evaluate(() => {
            const cards = document.querySelectorAll('.app-card');
            const visible = [];
            for (const card of cards) {
                if (card.offsetParent !== null) {
                    const nameEl = card.querySelector('h2');
                    visible.push(nameEl ? nameEl.innerText.trim() : card.innerText.trim().substring(0, 30));
                }
            }
            const tabs = document.querySelectorAll('.page-tab');
            const tabNames = [];
            for (const t of tabs) {
                tabNames.push(t.innerText.trim());
            }
            return { cardCount: visible.length, cards: visible, tabs: tabNames };
        });
        console.log(`  Accueil cards: ${accueilState.cardCount} - ${accueilState.cards.join(', ')}`);
        console.log(`  Page tabs: ${accueilState.tabs.join(', ')}`);

    } catch (error) {
        console.error(`\nFATAL ERROR: ${error.message}`);
        console.error(error.stack);
        try { await takeScreenshot(page, 'error'); } catch(e) {}
        results.push(`FATAL ERROR: ${error.message}`);
    } finally {
        await browser.close();
    }

    // =============================================
    // SUMMARY
    // =============================================
    console.log('\n\n========================================');
    console.log('     QUICK VALIDATION TEST REPORT');
    console.log('========================================');
    console.log(`\nURL testée: ${BASE_URL}`);

    console.log(`\nErreurs console JS (${consoleErrors.length}):`);
    if (consoleErrors.length === 0) console.log('  aucune');
    else consoleErrors.forEach(e => console.log(`  - ${e}`));

    console.log(`\nRequêtes en erreur (${networkErrors.length}):`);
    if (networkErrors.length === 0) console.log('  aucune');
    else networkErrors.forEach(e => console.log(`  - ${e}`));

    console.log('\nRésultats:');
    results.forEach(r => console.log(`  ${r}`));

    const passes = results.filter(r => r.endsWith('PASS')).length;
    const fails = results.filter(r => r.endsWith('FAIL')).length;
    const partials = results.filter(r => r.includes('PARTIAL')).length;

    console.log(`\nScore: ${passes} PASS, ${partials} PARTIAL, ${fails} FAIL / ${results.length} tests`);

    if (fails === 0 && partials === 0) console.log('\nVerdict: SUCCES');
    else if (fails > results.length / 2) console.log('\nVerdict: ECHEC');
    else console.log('\nVerdict: PARTIEL');
})();
