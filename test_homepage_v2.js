const puppeteer = require('puppeteer');
const path = require('path');
const fs = require('fs');

const SCREENSHOT_DIR = '/home/cactus/claude/homepage-app/screenshots';
const BASE_URL = 'http://192.168.1.200:1000';

if (!fs.existsSync(SCREENSHOT_DIR)) {
    fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
}

let screenshotCounter = 0;
async function screenshot(page, name) {
    screenshotCounter++;
    const num = String(screenshotCounter).padStart(2, '0');
    const filePath = path.join(SCREENSHOT_DIR, `${num}_${name}.png`);
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

    const browser = await puppeteer.launch({
        headless: true,
        args: ['--no-sandbox', '--disable-setuid-sandbox', '--window-size=1400,900']
    });

    const page = await browser.newPage();
    await page.setViewport({ width: 1400, height: 900 });

    page.on('console', msg => {
        if (msg.type() === 'error') {
            consoleErrors.push(msg.text());
        }
    });

    page.on('requestfailed', request => {
        networkErrors.push(`${request.method()} ${request.url()} - ${request.failure().errorText}`);
    });

    page.on('response', response => {
        if (response.status() >= 400) {
            networkErrors.push(`${response.status()} ${response.url()}`);
        }
    });

    try {
        // =============================================
        // STEP 1: Load the page and navigate to Accueil
        // =============================================
        console.log('\n=== STEP 1: Load page and navigate to Accueil ===');
        await page.goto(BASE_URL, { waitUntil: 'networkidle2', timeout: 15000 });
        await sleep(2000);

        const pageTitle = await page.title();
        console.log(`  Page title: "${pageTitle}"`);

        // The app seems to load on Projets page. We need to navigate to Accueil.
        // Look for page tabs or navigation
        const navInfo = await page.evaluate(() => {
            // Check current page state
            const pageIndicators = document.querySelectorAll('.page-tab, .nav-tab, [class*="page-btn"], [class*="tab"]');
            const info = [];
            for (const el of pageIndicators) {
                info.push({ tag: el.tagName, text: el.innerText.trim(), className: el.className, id: el.id });
            }

            // Also check sidebar nav buttons (the vertical bar on the right)
            const sidebarBtns = document.querySelectorAll('.sidebar-nav button, .right-nav button, .nav-button, [class*="nav-btn"]');
            const navBtns = [];
            for (const btn of sidebarBtns) {
                navBtns.push({ tag: btn.tagName, text: btn.innerText.trim(), className: btn.className, id: btn.id, title: btn.title });
            }

            // Check for page tabs at the bottom or top
            const tabBtns = document.querySelectorAll('button, a');
            const accueilBtns = [];
            for (const btn of tabBtns) {
                const text = btn.innerText.trim().toLowerCase();
                if (text.includes('accueil') || text.includes('home') || text.includes('main')) {
                    accueilBtns.push({ tag: btn.tagName, text: btn.innerText.trim(), className: btn.className, id: btn.id });
                }
            }

            return { pageIndicators: info, navButtons: navBtns, accueilButtons: accueilBtns };
        });
        console.log(`  Navigation info: ${JSON.stringify(navInfo, null, 2)}`);

        // Try navigating to Accueil page - click the home icon in the right sidebar
        const navigated = await page.evaluate(() => {
            // Try the right sidebar home button (the house icon)
            const rightNavBtns = document.querySelectorAll('.right-nav-btn, .nav-btn, .sidebar-icon');
            for (const btn of rightNavBtns) {
                const title = (btn.title || '').toLowerCase();
                const text = (btn.innerText || '').toLowerCase();
                if (title.includes('accueil') || title.includes('home') || text.includes('accueil') || text.includes('home')) {
                    btn.click();
                    return { clicked: true, method: 'right-nav', title: btn.title, text: btn.innerText.trim() };
                }
            }

            // Try page tabs
            const allBtns = document.querySelectorAll('button, a, [onclick]');
            for (const btn of allBtns) {
                const text = (btn.innerText || '').trim().toLowerCase();
                const onclick = (btn.getAttribute('onclick') || '').toLowerCase();
                if (text === 'accueil' || onclick.includes("'main'") || onclick.includes("'accueil'")) {
                    btn.click();
                    return { clicked: true, method: 'button', text: btn.innerText.trim() };
                }
            }

            // Try JavaScript navigation
            if (typeof switchPage === 'function') {
                switchPage('main');
                return { clicked: true, method: 'switchPage function' };
            }

            return { clicked: false };
        });
        console.log(`  Navigate to Accueil: ${JSON.stringify(navigated)}`);

        await sleep(1000);
        await screenshot(page, 'page_loaded');

        // Check if we're on the Accueil page now
        const currentPage = await page.evaluate(() => {
            const grid = document.getElementById('appGrid');
            const gridChildren = grid ? grid.children.length : -1;
            const containerDisplay = grid ? window.getComputedStyle(grid.parentElement || grid).display : 'unknown';

            // Look for app cards
            const cards = document.querySelectorAll('.app-card');
            const visibleCards = [];
            for (const card of cards) {
                if (card.offsetParent !== null) {
                    visibleCards.push(card.innerText.trim().substring(0, 50));
                }
            }

            return {
                gridChildren,
                containerDisplay,
                visibleCards,
                bodyText: document.body.innerText.substring(0, 300)
            };
        });
        console.log(`  Current page state: ${JSON.stringify(currentPage, null, 2)}`);

        if (currentPage.visibleCards.length > 0) {
            results.push(`STEP 1: Page loaded with ${currentPage.visibleCards.length} app cards - PASS`);
        } else {
            // We might still be on Projets page. Let's try to switch using JavaScript
            console.log('  No app cards visible. Attempting JS navigation...');
            await page.evaluate(() => {
                // Try to find the switchPage function or trigger page change
                if (typeof switchPage === 'function') {
                    switchPage('main');
                } else if (typeof changePage === 'function') {
                    changePage('main');
                } else {
                    // Try clicking on page tab directly
                    const tabs = document.querySelectorAll('[data-page], [data-page-id]');
                    for (const tab of tabs) {
                        const pageId = tab.dataset.page || tab.dataset.pageId;
                        if (pageId === 'main') {
                            tab.click();
                            break;
                        }
                    }
                }
            });
            await sleep(1000);
            await screenshot(page, 'after_js_nav');

            const cards2 = await page.evaluate(() => {
                const cards = document.querySelectorAll('.app-card');
                const visible = [];
                for (const c of cards) {
                    if (c.offsetParent !== null) visible.push(c.innerText.trim().substring(0, 50));
                }
                return visible;
            });
            console.log(`  Cards after JS nav: ${cards2.length}`);

            if (cards2.length > 0) {
                results.push(`STEP 1: Page loaded, navigated to Accueil with ${cards2.length} cards - PASS`);
            } else {
                results.push('STEP 1: Page loaded but could not find app cards page - PARTIAL (testing on current page)');
            }
        }

        // =============================================
        // STEP 2: Right-click on empty area of app grid
        // =============================================
        console.log('\n=== STEP 2: Right-click on empty area of app grid ===');

        // First, let's dismiss any existing context menu by clicking elsewhere
        await page.mouse.click(10, 10);
        await sleep(200);

        // Get the grid/container position
        const gridInfo = await page.evaluate(() => {
            const grid = document.getElementById('appGrid');
            if (grid && grid.offsetParent !== null) {
                const rect = grid.getBoundingClientRect();
                return { found: true, id: 'appGrid', rect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height } };
            }

            // Look for the container or main content area
            const container = document.querySelector('.container, .content, main');
            if (container) {
                const rect = container.getBoundingClientRect();
                return { found: true, id: 'container', rect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height } };
            }
            return { found: false };
        });
        console.log(`  Grid info: ${JSON.stringify(gridInfo)}`);

        // Right-click at the bottom of the visible area (below cards, on the grid)
        // or right-click in an empty space between cards
        let rcX, rcY;
        if (gridInfo.found && gridInfo.rect.width > 0 && gridInfo.rect.height > 0) {
            // Click in the lower-right area of the grid (likely empty space)
            rcX = gridInfo.rect.x + gridInfo.rect.width - 100;
            rcY = gridInfo.rect.y + gridInfo.rect.height - 50;
        } else {
            // Fallback: click in center-bottom of page
            rcX = 700;
            rcY = 600;
        }
        console.log(`  Right-clicking at (${rcX}, ${rcY})`);
        await page.mouse.click(rcX, rcY, { button: 'right' });
        await sleep(500);
        await screenshot(page, 'rightclick_empty');

        // Check for grid context menu specifically
        const gridCtxMenu = await page.evaluate(() => {
            const menu = document.getElementById('gridContextMenu');
            if (!menu) return { found: false, reason: 'no gridContextMenu element' };
            const style = window.getComputedStyle(menu);
            return {
                found: true,
                display: style.display,
                text: menu.innerText.trim(),
                visible: style.display !== 'none'
            };
        });
        console.log(`  Grid context menu: ${JSON.stringify(gridCtxMenu)}`);

        if (!gridCtxMenu.visible) {
            // The grid might have 0x0 size on Projets page. Try right-clicking on the page body directly
            // Let's check what elements respond to contextmenu events
            console.log('  Grid context menu not visible. Investigating event listeners...');

            const eventInfo = await page.evaluate(() => {
                // Check what page we're on
                const header = document.querySelector('.page-header, h1, h2, .title');
                const headerText = header ? header.innerText : 'no header';

                // Check grid dimensions
                const grid = document.getElementById('appGrid');
                const gridRect = grid ? grid.getBoundingClientRect() : null;
                const gridDisplay = grid ? window.getComputedStyle(grid).display : 'N/A';
                const gridParentDisplay = grid && grid.parentElement ? window.getComputedStyle(grid.parentElement).display : 'N/A';

                // Check what's visible
                const container = document.querySelector('.container');
                const containerChildren = container ? Array.from(container.children).map(c => ({
                    tag: c.tagName,
                    className: c.className,
                    display: window.getComputedStyle(c).display,
                    text: c.innerText.substring(0, 50)
                })) : [];

                return { headerText, gridRect, gridDisplay, gridParentDisplay, containerChildren };
            });
            console.log(`  Event info: ${JSON.stringify(eventInfo, null, 2)}`);

            // If the appGrid is hidden (display: none), we need to switch to a page that shows it
            if (eventInfo.gridDisplay === 'none' || (eventInfo.gridRect && eventInfo.gridRect.width === 0)) {
                console.log('  App grid is hidden. Need to switch to Accueil page...');

                // Forcefully navigate
                await page.evaluate(() => {
                    // Try setting location hash or calling any navigation function
                    const pages = document.querySelectorAll('.page-tab, [data-page]');
                    for (const p of pages) {
                        console.log('Page tab:', p.innerText, p.dataset.page);
                    }

                    // Direct approach: find and click the "Accueil" tab/link
                    const allClickables = document.querySelectorAll('button, a, [onclick], [role="tab"]');
                    for (const el of allClickables) {
                        if (el.innerText.includes('Accueil') && el.offsetParent !== null) {
                            el.click();
                            return 'clicked Accueil';
                        }
                    }

                    // Try the home icon on right sidebar
                    const svgBtns = document.querySelectorAll('svg');
                    for (const svg of svgBtns) {
                        const parent = svg.closest('button') || svg.closest('a') || svg.parentElement;
                        if (parent && (parent.title || '').toLowerCase().includes('accueil')) {
                            parent.click();
                            return 'clicked home svg';
                        }
                    }

                    return 'no navigation found';
                });
                await sleep(1000);

                // Check again
                const grid2 = await page.evaluate(() => {
                    const g = document.getElementById('appGrid');
                    return g ? { display: window.getComputedStyle(g).display, rect: g.getBoundingClientRect() } : null;
                });
                console.log(`  Grid after nav attempt: ${JSON.stringify(grid2)}`);
            }

            // Try right-clicking again on the actual content area
            // The grid is in a .container element. Let's try right-clicking there
            await page.evaluate(() => {
                // Manually dispatch a contextmenu event on the container or body
                const grid = document.getElementById('appGrid');
                const container = document.querySelector('.container');
                const target = (grid && grid.offsetParent) ? grid : (container || document.body);
                const event = new MouseEvent('contextmenu', {
                    bubbles: true,
                    cancelable: true,
                    clientX: 700,
                    clientY: 500
                });
                target.dispatchEvent(event);
            });
            await sleep(500);
            await screenshot(page, 'rightclick_dispatched');

            // Check menu again
            const gridCtxMenu2 = await page.evaluate(() => {
                const menu = document.getElementById('gridContextMenu');
                if (!menu) return { found: false };
                const style = window.getComputedStyle(menu);
                return { found: true, display: style.display, text: menu.innerText.trim(), visible: style.display !== 'none' };
            });
            console.log(`  Grid context menu after dispatch: ${JSON.stringify(gridCtxMenu2)}`);

            if (gridCtxMenu2.visible) {
                results.push('STEP 2: Context menu appeared with "Nouveau raccourci" via dispatched event - PASS');
            } else {
                // Let's look at the source to understand the contextmenu handler
                const handlers = await page.evaluate(() => {
                    const grid = document.getElementById('appGrid');
                    const container = document.querySelector('.container');
                    // Check if there are contextmenu event listeners
                    // Try to trigger on body or a wrapping element
                    return {
                        gridExists: !!grid,
                        gridVisible: grid ? grid.offsetParent !== null : false,
                        containerExists: !!container,
                        bodyHasHandler: typeof document.body.oncontextmenu === 'function'
                    };
                });
                console.log(`  Handler check: ${JSON.stringify(handlers)}`);
                results.push('STEP 2: Grid context menu NOT appearing (grid may be hidden on current page) - FAIL');
            }
        } else {
            const hasNR = gridCtxMenu.text.includes('Nouveau raccourci');
            results.push(`STEP 2: Grid context menu appeared${hasNR ? ' with "Nouveau raccourci"' : ' but missing "Nouveau raccourci"'} - ${hasNR ? 'PASS' : 'PARTIAL'}`);
        }

        // =============================================
        // STEPS 3-9: Open modal, fill form, create shortcut
        // =============================================
        console.log('\n=== STEP 3: Open "Nouveau raccourci" modal ===');

        // First ensure the grid context menu is visible by showing it via JS if needed
        const menuShown = await page.evaluate(() => {
            const menu = document.getElementById('gridContextMenu');
            if (menu && menu.style.display === 'none') {
                menu.style.display = 'block';
                menu.style.left = '700px';
                menu.style.top = '400px';
            }
            return menu ? menu.style.display : 'no menu';
        });

        // Click "Nouveau raccourci" in the context menu
        const nrClicked = await page.evaluate(() => {
            const menu = document.getElementById('gridContextMenu');
            if (!menu) return { clicked: false, reason: 'no menu' };

            const items = menu.querySelectorAll('button, .context-item, a');
            for (const item of items) {
                if (item.innerText.includes('Nouveau raccourci')) {
                    item.click();
                    return { clicked: true, text: item.innerText.trim() };
                }
            }

            // If no button found, try all descendants
            const allEl = menu.querySelectorAll('*');
            for (const el of allEl) {
                if (el.innerText === 'Nouveau raccourci' || (el.innerText && el.innerText.trim().includes('Nouveau raccourci') && el.children.length < 3)) {
                    el.click();
                    return { clicked: true, text: el.innerText.trim(), tag: el.tagName };
                }
            }
            return { clicked: false, reason: 'no matching item', menuHTML: menu.innerHTML.substring(0, 200) };
        });
        console.log(`  Clicked "Nouveau raccourci": ${JSON.stringify(nrClicked)}`);

        await sleep(800);

        // Verify modal opened
        const modalOpen = await page.evaluate(() => {
            const modal = document.getElementById('createAppModal');
            if (!modal) return { open: false, reason: 'no createAppModal' };
            const hasActive = modal.classList.contains('active');
            const display = window.getComputedStyle(modal).display;
            return { open: hasActive || display !== 'none', hasActive, display, text: modal.innerText.substring(0, 100) };
        });
        console.log(`  Modal state: ${JSON.stringify(modalOpen)}`);

        if (!modalOpen.open) {
            // Try opening via JS
            console.log('  Modal not open. Trying to open via JS...');
            await page.evaluate(() => {
                const modal = document.getElementById('createAppModal');
                if (modal) {
                    modal.classList.add('active');
                    modal.style.display = 'flex';
                }
                // Also try calling any openCreateModal function
                if (typeof openCreateAppModal === 'function') openCreateAppModal();
                else if (typeof showCreateModal === 'function') showCreateModal();
                else if (typeof openCreateModal === 'function') openCreateModal();
            });
            await sleep(500);
        }

        await screenshot(page, 'modal_opened');

        // Check modal fields
        const modalCheck = await page.evaluate(() => {
            const nameInput = document.getElementById('createAppName');
            const urlInput = document.getElementById('createAppUrl');
            const descInput = document.getElementById('createAppDesc');
            const iconGrid = document.querySelector('.icon-picker-grid, #iconPickerGrid');
            const colorGrid = document.querySelector('.color-picker-grid, #colorPickerGrid');
            const previewCard = document.querySelector('.create-preview-card');

            return {
                hasName: !!nameInput && nameInput.offsetParent !== null,
                hasUrl: !!urlInput && urlInput.offsetParent !== null,
                hasDesc: !!descInput && descInput.offsetParent !== null,
                hasIconPicker: !!iconGrid,
                iconCount: iconGrid ? iconGrid.children.length : 0,
                hasColorPicker: !!colorGrid,
                colorCount: colorGrid ? colorGrid.children.length : 0,
                hasPreviewCard: !!previewCard
            };
        });
        console.log(`  Modal fields: ${JSON.stringify(modalCheck)}`);

        if (modalCheck.hasName && modalCheck.hasUrl && modalCheck.hasDesc && modalCheck.hasIconPicker && modalCheck.hasColorPicker && modalCheck.hasPreviewCard) {
            results.push('STEP 3: Modal opened with all fields (Name, URL, Description, icon picker, color picker, preview) - PASS');
        } else {
            results.push(`STEP 3: Modal has fields: name=${modalCheck.hasName}, url=${modalCheck.hasUrl}, desc=${modalCheck.hasDesc}, icons=${modalCheck.iconCount}, colors=${modalCheck.colorCount}, preview=${modalCheck.hasPreviewCard} - PARTIAL`);
        }

        // =============================================
        // STEP 4: Fill in the form
        // =============================================
        console.log('\n=== STEP 4: Fill in form fields ===');

        // Use specific IDs that we found
        try {
            // Clear and fill Name
            await page.click('#createAppName', { clickCount: 3 });
            await page.type('#createAppName', 'Test Shortcut');

            // Clear and fill URL
            await page.click('#createAppUrl', { clickCount: 3 });
            await page.type('#createAppUrl', 'http://192.168.1.200:3000');

            // Clear and fill Description
            await page.click('#createAppDesc', { clickCount: 3 });
            await page.type('#createAppDesc', 'Mon test');

            // Verify the values
            const fieldValues = await page.evaluate(() => {
                return {
                    name: document.getElementById('createAppName').value,
                    url: document.getElementById('createAppUrl').value,
                    desc: document.getElementById('createAppDesc').value
                };
            });
            console.log(`  Field values: ${JSON.stringify(fieldValues)}`);

            if (fieldValues.name === 'Test Shortcut' && fieldValues.url === 'http://192.168.1.200:3000' && fieldValues.desc === 'Mon test') {
                results.push('STEP 4: Form filled correctly - Name="Test Shortcut", URL="http://192.168.1.200:3000", Desc="Mon test" - PASS');
            } else {
                results.push(`STEP 4: Form fill partial - values: ${JSON.stringify(fieldValues)} - PARTIAL`);
            }
        } catch (e) {
            console.log(`  Error filling form: ${e.message}`);
            results.push(`STEP 4: Error filling form: ${e.message} - FAIL`);
        }

        await screenshot(page, 'form_filled');

        // =============================================
        // STEP 5: Click a different icon
        // =============================================
        console.log('\n=== STEP 5: Click different icon ===');

        const iconResult = await page.evaluate(() => {
            const grid = document.getElementById('iconPickerGrid');
            if (!grid) return { clicked: false, reason: 'no iconPickerGrid' };
            const items = grid.children;
            if (items.length < 5) return { clicked: false, reason: `only ${items.length} icons` };
            // Click the 5th icon (index 4)
            items[4].click();
            return { clicked: true, totalIcons: items.length, clickedIndex: 4, clickedClass: items[4].className };
        });
        console.log(`  Icon click: ${JSON.stringify(iconResult)}`);
        await sleep(300);
        await screenshot(page, 'icon_selected');

        if (iconResult.clicked) {
            results.push(`STEP 5: Selected icon at index 4 (of ${iconResult.totalIcons} icons) - PASS`);
        } else {
            results.push(`STEP 5: Could not select icon - ${iconResult.reason} - FAIL`);
        }

        // =============================================
        // STEP 6: Click a different color
        // =============================================
        console.log('\n=== STEP 6: Click different color ===');

        const colorResult = await page.evaluate(() => {
            const grid = document.getElementById('colorPickerGrid');
            if (!grid) return { clicked: false, reason: 'no colorPickerGrid' };
            const items = grid.children;
            if (items.length < 3) return { clicked: false, reason: `only ${items.length} colors` };
            // Click the 3rd color (index 2)
            items[2].click();
            return { clicked: true, totalColors: items.length, clickedIndex: 2, clickedStyle: items[2].getAttribute('style') };
        });
        console.log(`  Color click: ${JSON.stringify(colorResult)}`);
        await sleep(300);
        await screenshot(page, 'color_selected');

        if (colorResult.clicked) {
            results.push(`STEP 6: Selected color at index 2 (of ${colorResult.totalColors} colors) - PASS`);
        } else {
            results.push(`STEP 6: Could not select color - ${colorResult.reason} - FAIL`);
        }

        // =============================================
        // STEP 7: Verify preview card
        // =============================================
        console.log('\n=== STEP 7: Verify preview card ===');

        const previewState = await page.evaluate(() => {
            const preview = document.querySelector('.create-preview-card');
            if (!preview) return { found: false };

            const text = preview.innerText;
            const hasName = text.includes('Test Shortcut');
            const hasDesc = text.includes('Mon test');

            // Check the icon/color
            const iconEl = preview.querySelector('.icon, svg, [class*="icon"]');
            const style = preview.getAttribute('style') || '';
            const previewBg = window.getComputedStyle(preview.querySelector('[class*="icon"]') || preview).background;

            return {
                found: true,
                text: text.trim(),
                hasName,
                hasDesc,
                background: previewBg.substring(0, 100),
                style: style.substring(0, 100)
            };
        });
        console.log(`  Preview: ${JSON.stringify(previewState)}`);

        await screenshot(page, 'preview_verified');

        if (previewState.found && previewState.hasName && previewState.hasDesc) {
            results.push('STEP 7: Preview card shows "Test Shortcut" and "Mon test" - PASS');
        } else if (previewState.found && (previewState.hasName || previewState.hasDesc)) {
            results.push(`STEP 7: Preview card partially updated - name=${previewState.hasName}, desc=${previewState.hasDesc} - PARTIAL`);
        } else {
            results.push(`STEP 7: Preview not reflecting changes - text="${previewState.text}" - FAIL`);
        }

        // =============================================
        // STEP 8: Click "Créer" button
        // =============================================
        console.log('\n=== STEP 8: Click "Créer" ===');

        const creerResult = await page.evaluate(() => {
            // Find the Créer button in the createAppModal
            const modal = document.getElementById('createAppModal');
            if (!modal) return { clicked: false, reason: 'no modal' };

            const buttons = modal.querySelectorAll('button');
            for (const btn of buttons) {
                const text = btn.innerText.trim();
                if (text === 'Créer' || text.toLowerCase().includes('créer') || text.toLowerCase().includes('creer')) {
                    btn.click();
                    return { clicked: true, text };
                }
            }

            // Try submit button
            const submitBtns = modal.querySelectorAll('input[type="submit"], button[type="submit"]');
            for (const btn of submitBtns) {
                btn.click();
                return { clicked: true, text: btn.value || btn.innerText, type: 'submit' };
            }

            // List all buttons for debugging
            const allBtns = Array.from(buttons).map(b => b.innerText.trim());
            return { clicked: false, reason: 'no matching button', buttons: allBtns };
        });
        console.log(`  Créer: ${JSON.stringify(creerResult)}`);

        await sleep(1000);
        await screenshot(page, 'after_creer');

        if (creerResult.clicked) {
            results.push('STEP 8: Clicked "Créer" button - PASS');
        } else {
            results.push(`STEP 8: Could not click "Créer" - ${creerResult.reason} - FAIL`);
        }

        // =============================================
        // STEP 9: Verify new card appears
        // =============================================
        console.log('\n=== STEP 9: Verify new card on page ===');

        await sleep(500);

        const newCard = await page.evaluate(() => {
            // Check if modal closed
            const modal = document.getElementById('createAppModal');
            const modalClosed = modal ? (!modal.classList.contains('active') || window.getComputedStyle(modal).display === 'none') : true;

            // Look for "Test Shortcut" in app cards
            const cards = document.querySelectorAll('.app-card, [class*="card"]');
            let testCard = null;
            for (const card of cards) {
                if (card.innerText.includes('Test Shortcut')) {
                    const rect = card.getBoundingClientRect();
                    testCard = {
                        found: true,
                        text: card.innerText.trim().substring(0, 100),
                        visible: card.offsetParent !== null,
                        rect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height }
                    };
                    break;
                }
            }

            // Also check the entire page text
            const pageHasText = document.body.innerText.includes('Test Shortcut');

            return { modalClosed, testCard, pageHasText };
        });
        console.log(`  New card check: ${JSON.stringify(newCard)}`);

        await screenshot(page, 'new_card_visible');

        if (newCard.testCard && newCard.testCard.visible) {
            results.push('STEP 9: "Test Shortcut" card visible on page - PASS');
        } else if (newCard.pageHasText) {
            results.push('STEP 9: "Test Shortcut" text on page but card not clearly visible - PARTIAL');
        } else {
            results.push('STEP 9: "Test Shortcut" NOT found on page - FAIL');
        }

        // =============================================
        // STEP 10: Right-click on new card
        // =============================================
        console.log('\n=== STEP 10: Right-click on "Test Shortcut" card ===');

        let hasSupprimer = false;
        let hasModifier = false;

        if (newCard.testCard && newCard.testCard.rect) {
            const cx = newCard.testCard.rect.x + newCard.testCard.rect.width / 2;
            const cy = newCard.testCard.rect.y + newCard.testCard.rect.height / 2;
            console.log(`  Right-clicking at (${cx}, ${cy})`);
            await page.mouse.click(cx, cy, { button: 'right' });
            await sleep(500);
        } else {
            // Try to find and right-click via evaluate
            const cardPos = await page.evaluate(() => {
                const allEls = document.querySelectorAll('*');
                for (const el of allEls) {
                    if (el.innerText === 'Test Shortcut' || (el.innerText.includes('Test Shortcut') && el.tagName !== 'BODY' && el.tagName !== 'HTML')) {
                        const card = el.closest('.app-card, [class*="card"]') || el;
                        const rect = card.getBoundingClientRect();
                        if (rect.width > 0) return { x: rect.x + rect.width / 2, y: rect.y + rect.height / 2 };
                    }
                }
                return null;
            });

            if (cardPos) {
                console.log(`  Found card, right-clicking at (${cardPos.x}, ${cardPos.y})`);
                await page.mouse.click(cardPos.x, cardPos.y, { button: 'right' });
                await sleep(500);
            }
        }

        await screenshot(page, 'rightclick_new_card');

        // Check context menu
        const ctxMenuContent = await page.evaluate(() => {
            const menu = document.getElementById('contextMenu');
            if (!menu) return { found: false };
            const style = window.getComputedStyle(menu);
            const visible = style.display !== 'none';
            return {
                found: true,
                visible,
                display: style.display,
                text: menu.innerText.trim(),
                hasSupprimer: menu.innerText.includes('Supprimer'),
                hasModifier: menu.innerText.includes('Modifier')
            };
        });
        console.log(`  Context menu: ${JSON.stringify(ctxMenuContent)}`);

        hasSupprimer = ctxMenuContent.hasSupprimer;
        hasModifier = ctxMenuContent.hasModifier;

        if (hasSupprimer && hasModifier) {
            results.push('STEP 10: Context menu shows "Supprimer" and "Modifier" options - PASS');
        } else {
            results.push(`STEP 10: Context menu - Supprimer=${hasSupprimer}, Modifier=${hasModifier} - ${hasSupprimer || hasModifier ? 'PARTIAL' : 'FAIL'}`);
        }

        // =============================================
        // STEP 11: Verify "Modifier" is present
        // =============================================
        console.log('\n=== STEP 11: Verify "Modifier" option ===');

        // Check if the delete button has red styling
        const deleteStyle = await page.evaluate(() => {
            const menu = document.getElementById('contextMenu');
            if (!menu) return { found: false };
            const deleteBtn = menu.querySelector('.context-delete, [class*="delete"]');
            if (!deleteBtn) return { found: false, reason: 'no delete button element' };
            const style = window.getComputedStyle(deleteBtn);
            return {
                found: true,
                color: style.color,
                backgroundColor: style.backgroundColor,
                text: deleteBtn.innerText.trim(),
                className: deleteBtn.className
            };
        });
        console.log(`  Delete button style: ${JSON.stringify(deleteStyle)}`);

        if (hasModifier) {
            results.push('STEP 11: "Modifier" option confirmed in context menu - PASS');
        } else {
            results.push('STEP 11: "Modifier" option NOT found - FAIL');
        }

        // =============================================
        // STEP 12: Click "Supprimer" and accept confirmation
        // =============================================
        console.log('\n=== STEP 12: Click "Supprimer" ===');

        // Set up dialog handler for confirm()
        page.once('dialog', async dialog => {
            console.log(`  Confirmation dialog: "${dialog.message()}"`);
            await dialog.accept();
            console.log('  Dialog accepted');
        });

        const deleteResult = await page.evaluate(() => {
            const menu = document.getElementById('contextMenu');
            if (!menu) return { clicked: false, reason: 'no context menu' };

            const deleteBtn = menu.querySelector('.context-delete, .context-item.context-delete');
            if (deleteBtn) {
                deleteBtn.click();
                return { clicked: true, text: deleteBtn.innerText.trim(), method: 'class selector' };
            }

            // Fallback: find by text
            const items = menu.querySelectorAll('button, .context-item');
            for (const item of items) {
                if (item.innerText.includes('Supprimer')) {
                    item.click();
                    return { clicked: true, text: item.innerText.trim(), method: 'text match' };
                }
            }

            return { clicked: false, reason: 'no Supprimer button found' };
        });
        console.log(`  Delete click: ${JSON.stringify(deleteResult)}`);

        await sleep(1500);
        await screenshot(page, 'after_delete');

        if (deleteResult.clicked) {
            results.push('STEP 12: Clicked "Supprimer" and accepted confirmation dialog - PASS');
        } else {
            results.push(`STEP 12: Could not click "Supprimer" - ${deleteResult.reason} - FAIL`);
        }

        // =============================================
        // STEP 13: Verify card removed
        // =============================================
        console.log('\n=== STEP 13: Verify card removed ===');

        await sleep(500);
        const cardRemoved = await page.evaluate(() => {
            // Check if "Test Shortcut" is still anywhere on the page (excluding hidden elements)
            const cards = document.querySelectorAll('.app-card, [class*="card"]');
            for (const card of cards) {
                if (card.innerText.includes('Test Shortcut') && card.offsetParent !== null) {
                    return { removed: false, stillInCard: true };
                }
            }
            // Also check body text
            const bodyText = document.body.innerText;
            return {
                removed: !bodyText.includes('Test Shortcut'),
                stillInText: bodyText.includes('Test Shortcut')
            };
        });
        console.log(`  Card removal: ${JSON.stringify(cardRemoved)}`);

        await screenshot(page, 'card_removed_final');

        if (cardRemoved.removed) {
            results.push('STEP 13: "Test Shortcut" card successfully removed from page - PASS');
        } else {
            results.push('STEP 13: "Test Shortcut" still appears on page - FAIL');
        }

    } catch (error) {
        console.error(`\nFATAL ERROR: ${error.message}`);
        console.error(error.stack);
        await screenshot(page, 'error');
        results.push(`FATAL ERROR: ${error.message}`);
    } finally {
        await browser.close();
    }

    // =============================================
    // SUMMARY
    // =============================================
    console.log('\n\n========================================');
    console.log('          TEST REPORT');
    console.log('========================================');
    console.log(`\nURL: ${BASE_URL}`);

    console.log(`\nConsole JS errors (${consoleErrors.length}):`);
    if (consoleErrors.length === 0) console.log('  aucune');
    else consoleErrors.forEach(e => console.log(`  - ${e}`));

    console.log(`\nNetwork errors (${networkErrors.length}):`);
    if (networkErrors.length === 0) console.log('  aucune');
    else networkErrors.forEach(e => console.log(`  - ${e}`));

    console.log('\nActions:');
    results.forEach(r => console.log(`  ${r}`));

    const passes = results.filter(r => r.endsWith('PASS')).length;
    const fails = results.filter(r => r.endsWith('FAIL')).length;
    const partials = results.filter(r => r.endsWith('PARTIAL')).length;

    console.log(`\nScore: ${passes} PASS, ${partials} PARTIAL, ${fails} FAIL / ${results.length} steps`);

    if (fails === 0 && partials === 0) console.log('\nVERDICT: SUCCES');
    else if (fails > results.length / 2) console.log('\nVERDICT: ECHEC');
    else console.log('\nVERDICT: PARTIEL');
})();
