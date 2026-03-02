const puppeteer = require('puppeteer');

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

    // Track ALL fetch requests
    const allRequests = [];
    page.on('request', request => {
        const url = request.url();
        if (url.includes('terminal') || url.includes('preferences') || url.includes('sessions')) {
            allRequests.push({ url, method: request.method(), time: Date.now() });
        }
    });

    const allResponses = [];
    page.on('response', response => {
        const url = response.url();
        const status = response.status();
        if (url.includes('terminal') || url.includes('preferences') || url.includes('sessions')) {
            allResponses.push({ url, status, time: Date.now() });
        }
    });

    const consoleLogs = [];
    page.on('console', msg => {
        consoleLogs.push({ type: msg.type(), text: msg.text() });
    });

    try {
        console.log('Loading page...');
        await page.goto(BASE_URL, { waitUntil: 'networkidle2', timeout: 15000 });
        await sleep(3000);

        // Check if we're on terminal page
        const isTerminal = await page.evaluate(() => {
            const tm = document.getElementById('terminalManager');
            return tm && tm.classList.contains('active');
        });
        console.log('Terminal manager active:', isTerminal);

        // Check if syncInterval is set
        const syncState = await page.evaluate(() => {
            return {
                hasSyncInterval: typeof syncInterval !== 'undefined' && syncInterval !== null,
                syncIntervalValue: typeof syncInterval !== 'undefined' ? syncInterval : 'undefined',
                terminalTabsCount: typeof terminalTabs !== 'undefined' ? terminalTabs.length : 'undefined',
                saveDebounceActive: typeof saveDebounceTimeout !== 'undefined' && saveDebounceTimeout !== null,
                syncInProgress: typeof _syncInProgress !== 'undefined' ? _syncInProgress : 'undefined'
            };
        });
        console.log('Sync state:', JSON.stringify(syncState));

        // Clear and wait
        console.log('\nWaiting 20 seconds to monitor requests...');
        const startTime = Date.now();
        allRequests.length = 0;
        allResponses.length = 0;

        await sleep(20000);

        console.log('\n=== Requests captured in 20s ===');
        console.log(`Total requests: ${allRequests.length}`);
        allRequests.forEach(r => {
            const elapsed = ((r.time - startTime) / 1000).toFixed(1);
            console.log(`  [${elapsed}s] ${r.method} ${r.url.replace(BASE_URL, '')}`);
        });

        console.log(`\nTotal responses: ${allResponses.length}`);
        allResponses.forEach(r => {
            const elapsed = ((r.time - startTime) / 1000).toFixed(1);
            console.log(`  [${elapsed}s] ${r.status} ${r.url.replace(BASE_URL, '')}`);
        });

        // Check sync state again
        const syncState2 = await page.evaluate(() => {
            return {
                hasSyncInterval: typeof syncInterval !== 'undefined' && syncInterval !== null,
                terminalTabsCount: typeof terminalTabs !== 'undefined' ? terminalTabs.length : 'undefined',
                saveDebounceActive: typeof saveDebounceTimeout !== 'undefined' && saveDebounceTimeout !== null,
                syncInProgress: typeof _syncInProgress !== 'undefined' ? _syncInProgress : 'undefined'
            };
        });
        console.log('\nSync state after wait:', JSON.stringify(syncState2));

        // Force trigger a sync and see if it works
        console.log('\nManually triggering syncTerminalTabs()...');
        const manualSync = await page.evaluate(async () => {
            if (typeof syncTerminalTabs === 'function') {
                try {
                    await syncTerminalTabs();
                    return 'success';
                } catch (e) {
                    return 'error: ' + e.message;
                }
            }
            return 'function not found';
        });
        console.log('Manual sync result:', manualSync);

        // Check console for any sync-related logs
        console.log('\nRelevant console logs:');
        consoleLogs.filter(l =>
            l.text.includes('sync') || l.text.includes('Sync') ||
            l.text.includes('terminal') || l.text.includes('Terminal') ||
            l.text.includes('poll') || l.text.includes('interval')
        ).forEach(l => console.log(`  [${l.type}] ${l.text}`));

    } catch (err) {
        console.error('Test error:', err.message);
    } finally {
        await browser.close();
    }
}

test().catch(err => {
    console.error('Fatal error:', err);
    process.exit(1);
});
