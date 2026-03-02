const puppeteer = require('puppeteer');
const path = require('path');

const SCREENSHOT_DIR = '/home/cactus/claude/homepage-app/screenshots';
const BASE_URL = 'http://192.168.1.200';

async function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

async function test() {
    const browser = await puppeteer.launch({
        headless: 'new',
        args: ['--no-sandbox', '--disable-setuid-sandbox', '--window-size=1920,1080'],
        defaultViewport: { width: 1920, height: 1080 }
    });

    const page = await browser.newPage();

    // Collect console messages
    const consoleLogs = [];
    const consoleErrors = [];
    const networkErrors = [];
    const networkRequests = [];

    page.on('console', msg => {
        const text = msg.text();
        consoleLogs.push({ type: msg.type(), text });
        if (msg.type() === 'error') {
            consoleErrors.push(text);
        }
    });

    page.on('requestfailed', request => {
        networkErrors.push({
            url: request.url(),
            failure: request.failure()?.errorText || 'unknown'
        });
    });

    page.on('response', response => {
        const status = response.status();
        const url = response.url();
        if (status >= 400) {
            networkErrors.push({ url, status });
        }
        // Track terminal-related requests
        if (url.includes('/api/terminal') || url.includes('/api/preferences')) {
            networkRequests.push({ url, status, time: Date.now() });
        }
    });

    const results = {};

    try {
        // ============================================
        // TEST 1: Page loads correctly
        // ============================================
        console.log('\n=== TEST 1: Page loads correctly ===');
        await page.goto(BASE_URL, { waitUntil: 'networkidle2', timeout: 15000 });
        await sleep(2000);

        // Take screenshot of initial page
        await page.screenshot({ path: path.join(SCREENSHOT_DIR, 'test1_initial_page.png'), fullPage: false });
        console.log('Screenshot: test1_initial_page.png');

        // Check if we're on the Terminals page (currentPage is 'terminals' per preferences)
        const currentPageTitle = await page.evaluate(() => {
            const activeBtn = document.querySelector('.page-btn.active');
            return activeBtn ? activeBtn.textContent.trim() : 'unknown';
        });
        console.log('Current page:', currentPageTitle);

        // If not on terminals page, navigate there
        const isTerminalsPage = await page.evaluate(() => {
            // Check if terminal sidebar is visible
            const sidebar = document.querySelector('.terminal-sidebar') || document.querySelector('#terminalSidebar');
            return sidebar !== null;
        });

        if (!isTerminalsPage) {
            console.log('Not on terminals page, clicking Terminaux button...');
            const termBtn = await page.$('button.page-btn');
            const buttons = await page.$$('.page-btn');
            for (const btn of buttons) {
                const text = await btn.evaluate(el => el.textContent.trim());
                if (text.includes('Terminaux') || text.includes('Terminal')) {
                    await btn.click();
                    await sleep(2000);
                    break;
                }
            }
        }

        await page.screenshot({ path: path.join(SCREENSHOT_DIR, 'test1_terminals_page.png'), fullPage: false });
        console.log('Screenshot: test1_terminals_page.png');

        // Check for JS errors so far
        const initialErrors = consoleErrors.filter(e => !e.includes('favicon'));
        results.test1 = {
            pageLoaded: true,
            currentPage: currentPageTitle,
            jsErrors: initialErrors.length,
            jsErrorDetails: initialErrors
        };
        console.log('JS errors:', initialErrors.length);
        if (initialErrors.length > 0) {
            initialErrors.forEach(e => console.log('  ERROR:', e));
        }

        // ============================================
        // TEST 2: Terminal creation works
        // ============================================
        console.log('\n=== TEST 2: Terminal creation works ===');

        // Find a project in the sidebar and click it
        const projectClicked = await page.evaluate(() => {
            // Look for project buttons in the sidebar
            const projectBtns = document.querySelectorAll('.project-btn, .sidebar-project, [data-project]');
            if (projectBtns.length > 0) {
                projectBtns[0].click();
                return projectBtns[0].textContent.trim();
            }
            // Try alternative selectors
            const sidebarItems = document.querySelectorAll('.terminal-sidebar button, .terminal-sidebar .project-item, .terminal-sidebar li');
            if (sidebarItems.length > 0) {
                sidebarItems[0].click();
                return sidebarItems[0].textContent.trim();
            }
            return null;
        });

        console.log('Project clicked:', projectClicked);
        await sleep(1000);

        // Now look for the B (Bash) button
        const bashBtnFound = await page.evaluate(() => {
            // Look for B button
            const btns = document.querySelectorAll('button');
            for (const btn of btns) {
                const text = btn.textContent.trim();
                if (text === 'B' || text === 'Bash' || btn.title?.includes('Bash')) {
                    btn.click();
                    return { text, title: btn.title || '', clicked: true };
                }
            }
            // Check for type buttons
            const typeBtns = document.querySelectorAll('.terminal-type-btn, .type-btn, .btn-bash');
            if (typeBtns.length > 0) {
                typeBtns[0].click();
                return { text: typeBtns[0].textContent.trim(), clicked: true };
            }
            return { clicked: false, availableButtons: Array.from(document.querySelectorAll('button')).map(b => b.textContent.trim().substring(0, 20)).slice(0, 20) };
        });

        console.log('Bash button:', JSON.stringify(bashBtnFound));
        await sleep(3000); // Wait for terminal to open and connect

        await page.screenshot({ path: path.join(SCREENSHOT_DIR, 'test2_terminal_opened.png'), fullPage: false });
        console.log('Screenshot: test2_terminal_opened.png');

        // Check if a terminal div was created
        const terminalCreated = await page.evaluate(() => {
            const termDivs = document.querySelectorAll('.terminal-div, .xterm, .xterm-screen');
            const tabs = document.querySelectorAll('.terminal-tab, [class*="tab"]');
            return {
                xtermElements: termDivs.length,
                tabCount: tabs.length,
                hasXtermScreen: document.querySelector('.xterm-screen') !== null
            };
        });

        console.log('Terminal created:', JSON.stringify(terminalCreated));
        results.test2 = {
            projectClicked,
            bashBtnFound,
            terminalCreated
        };

        // ============================================
        // TEST 3: WebSocket connection
        // ============================================
        console.log('\n=== TEST 3: WebSocket connection ===');

        // Check console logs for WebSocket-related messages
        const wsLogs = consoleLogs.filter(l =>
            l.text.toLowerCase().includes('websocket') ||
            l.text.toLowerCase().includes('terminal connected') ||
            l.text.toLowerCase().includes('ws://') ||
            l.text.toLowerCase().includes('connected') ||
            l.text.toLowerCase().includes('connexion')
        );

        console.log('WebSocket-related console messages:');
        wsLogs.forEach(l => console.log(`  [${l.type}] ${l.text}`));

        // Check if there are WebSocket errors
        const wsErrors = consoleErrors.filter(e =>
            e.toLowerCase().includes('websocket') ||
            e.toLowerCase().includes('ws://') ||
            e.toLowerCase().includes('connection')
        );

        results.test3 = {
            wsMessages: wsLogs.length,
            wsErrors: wsErrors.length,
            wsErrorDetails: wsErrors,
            wsLogDetails: wsLogs.map(l => l.text)
        };

        // ============================================
        // TEST 4: Auto-reconnection check
        // ============================================
        console.log('\n=== TEST 4: Auto-reconnection check ===');

        // Check if "Connexion perdue" appears anywhere
        const reconnectionCheck = await page.evaluate(() => {
            const body = document.body.innerText;
            const hasConnexionPerdue = body.includes('Connexion perdue');
            const hasReconnecting = body.includes('Reconnecting') || body.includes('reconnect');
            const hasDisconnected = body.includes('Disconnected') || body.includes('déconnecté');
            return { hasConnexionPerdue, hasReconnecting, hasDisconnected };
        });

        console.log('Reconnection messages:', JSON.stringify(reconnectionCheck));

        // Also check console for reconnection logs
        const reconnectLogs = consoleLogs.filter(l =>
            l.text.includes('Connexion perdue') ||
            l.text.includes('reconnect') ||
            l.text.includes('Reconnecting') ||
            l.text.includes('disconnected')
        );

        console.log('Reconnection console logs:', reconnectLogs.length);
        reconnectLogs.forEach(l => console.log(`  [${l.type}] ${l.text}`));

        results.test4 = {
            ...reconnectionCheck,
            reconnectConsoleLogs: reconnectLogs.map(l => l.text)
        };

        // ============================================
        // TEST 5: Sync polling
        // ============================================
        console.log('\n=== TEST 5: Sync polling ===');

        // Clear the request log and wait 15 seconds to capture polling
        const pollStartTime = Date.now();
        networkRequests.length = 0;

        console.log('Waiting 15 seconds to observe polling...');
        await sleep(15000);

        const terminalStateRequests = networkRequests.filter(r => r.url.includes('/api/terminal/state'));
        const preferencesRequests = networkRequests.filter(r => r.url.includes('/api/preferences'));
        const allTerminalRequests = networkRequests.filter(r => r.url.includes('/api/terminal'));

        console.log(`Terminal state requests in 15s: ${terminalStateRequests.length}`);
        console.log(`Preferences requests in 15s: ${preferencesRequests.length}`);
        console.log(`All terminal API requests in 15s: ${allTerminalRequests.length}`);

        // Log all captured requests
        console.log('All tracked requests:');
        networkRequests.forEach(r => {
            const elapsed = ((r.time - pollStartTime) / 1000).toFixed(1);
            console.log(`  [${elapsed}s] ${r.status} ${r.url.replace(BASE_URL, '')}`);
        });

        results.test5 = {
            terminalStatePolls: terminalStateRequests.length,
            preferencesPolls: preferencesRequests.length,
            allTerminalPolls: allTerminalRequests.length,
            expectedPolls: '~3 (every 5s in 15s)',
            allRequests: networkRequests.map(r => ({
                url: r.url.replace(BASE_URL, ''),
                status: r.status,
                elapsed: ((r.time - pollStartTime) / 1000).toFixed(1)
            }))
        };

        // ============================================
        // TEST 6: API endpoints
        // ============================================
        console.log('\n=== TEST 6: API endpoints ===');

        // Test from within the browser context
        const apiResults = await page.evaluate(async () => {
            const results = {};

            try {
                const stateRes = await fetch('/api/terminal/state');
                const stateData = await stateRes.json();
                results.terminalState = {
                    status: stateRes.status,
                    hasTabs: Array.isArray(stateData.tabs),
                    tabCount: stateData.tabs?.length || 0,
                    hasActiveTab: !!stateData.activeTabId,
                    hasViewMode: !!stateData.viewMode
                };
            } catch (e) {
                results.terminalState = { error: e.message };
            }

            try {
                const sessionsRes = await fetch('http://192.168.1.200:7681/sessions');
                const sessionsData = await sessionsRes.json();
                results.terminalSessions = {
                    status: sessionsRes.status,
                    hasSessions: Array.isArray(sessionsData.sessions),
                    sessionCount: sessionsData.sessions?.length || 0,
                    sessionNames: sessionsData.sessions?.map(s => s.name) || []
                };
            } catch (e) {
                results.terminalSessions = { error: e.message };
            }

            return results;
        });

        console.log('Terminal state API:', JSON.stringify(apiResults.terminalState));
        console.log('Terminal sessions API:', JSON.stringify(apiResults.terminalSessions));

        results.test6 = apiResults;

        // Final screenshot
        await page.screenshot({ path: path.join(SCREENSHOT_DIR, 'test_final_state.png'), fullPage: false });

        // ============================================
        // SUMMARY
        // ============================================
        console.log('\n========================================');
        console.log('         TEST SUMMARY');
        console.log('========================================');

        // All network errors
        console.log('\nNetwork errors:');
        if (networkErrors.length === 0) {
            console.log('  None');
        } else {
            networkErrors.forEach(e => console.log(`  ${e.status || ''} ${e.url} ${e.failure || ''}`));
        }

        // All console errors
        const relevantErrors = consoleErrors.filter(e => !e.includes('favicon'));
        console.log('\nConsole errors (excluding favicon):');
        if (relevantErrors.length === 0) {
            console.log('  None');
        } else {
            relevantErrors.forEach(e => console.log(`  ${e}`));
        }

        // Verdict
        const hasJsErrors = relevantErrors.length > 0;
        const hasNetworkErrors = networkErrors.length > 0;
        const hasTerminal = terminalCreated.hasXtermScreen;
        const hasPolling = terminalStateRequests.length > 0 || allTerminalRequests.length > 0;
        const apiWorks = apiResults.terminalState?.status === 200 && apiResults.terminalSessions?.status === 200;
        const noSpuriousReconnect = !reconnectionCheck.hasConnexionPerdue;

        console.log('\n--- Results ---');
        console.log(`[${hasJsErrors ? 'FAIL' : 'PASS'}] JS Errors: ${relevantErrors.length}`);
        console.log(`[${hasNetworkErrors ? 'WARN' : 'PASS'}] Network Errors: ${networkErrors.length}`);
        console.log(`[${hasTerminal ? 'PASS' : 'FAIL'}] Terminal xterm.js created: ${hasTerminal}`);
        console.log(`[${hasPolling ? 'PASS' : 'FAIL'}] Sync polling detected: ${hasPolling} (${terminalStateRequests.length} state polls, ${allTerminalRequests.length} total terminal API)`);
        console.log(`[${apiWorks ? 'PASS' : 'FAIL'}] API endpoints working: ${apiWorks}`);
        console.log(`[${noSpuriousReconnect ? 'PASS' : 'FAIL'}] No spurious reconnection: ${noSpuriousReconnect}`);

        const allPass = !hasJsErrors && hasTerminal && hasPolling && apiWorks && noSpuriousReconnect;
        console.log(`\nOverall verdict: ${allPass ? 'SUCCES' : (hasTerminal && apiWorks ? 'PARTIEL' : 'ECHEC')}`);

        // Dump all console logs for debugging
        console.log('\n--- All console logs ---');
        consoleLogs.forEach(l => console.log(`  [${l.type}] ${l.text.substring(0, 200)}`));

    } catch (err) {
        console.error('Test error:', err.message);
        await page.screenshot({ path: path.join(SCREENSHOT_DIR, 'test_error.png'), fullPage: false });
    } finally {
        await browser.close();
    }
}

test().catch(err => {
    console.error('Fatal error:', err);
    process.exit(1);
});
