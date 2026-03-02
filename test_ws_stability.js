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

    const consoleLogs = [];
    page.on('console', msg => {
        consoleLogs.push({ type: msg.type(), text: msg.text(), time: Date.now() });
    });

    try {
        await page.goto(BASE_URL, { waitUntil: 'networkidle2', timeout: 15000 });
        await sleep(5000); // Wait for all terminals to connect

        // Check for "Connexion perdue" or "disconnected" messages
        const disconnectLogs = consoleLogs.filter(l =>
            l.text.includes('disconnected') ||
            l.text.includes('Connexion perdue') ||
            l.text.includes('Reconnecting') ||
            l.text.includes('WebSocket error')
        );

        console.log('=== WebSocket Stability Check ===');
        console.log(`Total console messages: ${consoleLogs.length}`);
        console.log(`Terminal connected messages: ${consoleLogs.filter(l => l.text.includes('Terminal connected:')).length}`);
        console.log(`Disconnect/error messages: ${disconnectLogs.length}`);

        if (disconnectLogs.length > 0) {
            console.log('\nDisconnect/error details:');
            disconnectLogs.forEach(l => console.log(`  [${l.type}] ${l.text}`));
        }

        // Now wait 10 more seconds and check for any new disconnects
        console.log('\nWaiting 10 seconds for stability...');
        const beforeCount = consoleLogs.length;
        await sleep(10000);
        const newLogs = consoleLogs.slice(beforeCount);
        const newDisconnects = newLogs.filter(l =>
            l.text.includes('disconnected') ||
            l.text.includes('Connexion perdue') ||
            l.text.includes('Reconnecting') ||
            l.text.includes('WebSocket error')
        );

        console.log(`New messages in 10s: ${newLogs.length}`);
        console.log(`New disconnects: ${newDisconnects.length}`);

        if (newDisconnects.length > 0) {
            console.log('Spurious disconnects detected!');
            newDisconnects.forEach(l => console.log(`  [${l.type}] ${l.text}`));
        } else {
            console.log('No spurious disconnects - PASS');
        }

        // Check the page itself for "Connexion perdue" text
        const pageHasDisconnect = await page.evaluate(() => {
            // Check all xterm terminal buffers
            const xtermViewports = document.querySelectorAll('.xterm-screen');
            const bodyText = document.body.innerText;
            return {
                bodyHasConnexionPerdue: bodyText.includes('Connexion perdue'),
                xtermScreenCount: xtermViewports.length
            };
        });
        console.log('\nPage text check:', JSON.stringify(pageHasDisconnect));

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
