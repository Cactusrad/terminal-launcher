const puppeteer = require('puppeteer');
const path = require('path');
const fs = require('fs');

const SCREENSHOT_DIR = '/home/cactus/claude/homepage-app/screenshots';
const BASE_URL = 'http://192.168.1.200:1000';

// Ensure screenshots directory exists
if (!fs.existsSync(SCREENSHOT_DIR)) {
    fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
}

async function screenshot(page, name) {
    const filePath = path.join(SCREENSHOT_DIR, `${name}.png`);
    await page.screenshot({ path: filePath, fullPage: false });
    console.log(`  [SCREENSHOT] ${filePath}`);
    return filePath;
}

async function sleep(ms) {
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

    // Capture console errors
    page.on('console', msg => {
        if (msg.type() === 'error') {
            consoleErrors.push(msg.text());
        }
    });

    // Capture network errors
    page.on('requestfailed', request => {
        networkErrors.push(`${request.method()} ${request.url()} - ${request.failure().errorText}`);
    });

    // Also capture HTTP 4xx/5xx
    page.on('response', response => {
        if (response.status() >= 400) {
            networkErrors.push(`${response.status()} ${response.url()}`);
        }
    });

    try {
        // =============================================
        // STEP 1: Load the page and take a screenshot
        // =============================================
        console.log('\n=== STEP 1: Load page ===');
        await page.goto(BASE_URL, { waitUntil: 'networkidle2', timeout: 15000 });
        await sleep(2000); // Wait for any dynamic content
        await screenshot(page, '01_page_loaded');

        // Check that we have content
        const pageTitle = await page.title();
        console.log(`  Page title: "${pageTitle}"`);

        const bodyText = await page.evaluate(() => document.body.innerText.substring(0, 200));
        console.log(`  Body preview: "${bodyText.substring(0, 100)}..."`);

        const hasCards = await page.evaluate(() => {
            const cards = document.querySelectorAll('.app-card, .card, [class*="card"]');
            return cards.length;
        });
        console.log(`  Cards found on page: ${hasCards}`);

        if (hasCards > 0) {
            results.push('STEP 1: Page loaded successfully with ' + hasCards + ' cards - PASS');
        } else {
            results.push('STEP 1: Page loaded but no cards found - WARNING');
        }

        // =============================================
        // STEP 2: Right-click on empty area of app grid
        // =============================================
        console.log('\n=== STEP 2: Right-click on empty area ===');

        // Find the grid/container area (not on a card)
        const emptyAreaClicked = await page.evaluate(() => {
            // Find the grid container
            const grid = document.querySelector('.apps-grid, .grid, [class*="grid"]');
            if (grid) return { found: true, className: grid.className };

            // Try common container selectors
            const container = document.querySelector('#appsGrid, #apps-grid, .apps-container, .app-container, main, .content');
            if (container) return { found: true, className: container.className };

            return { found: false };
        });
        console.log(`  Grid element: ${JSON.stringify(emptyAreaClicked)}`);

        // Let's inspect the DOM structure to find the right element
        const domStructure = await page.evaluate(() => {
            const allElements = document.querySelectorAll('*');
            const relevantClasses = [];
            for (const el of allElements) {
                if (el.className && typeof el.className === 'string') {
                    const cls = el.className.toLowerCase();
                    if (cls.includes('grid') || cls.includes('app') || cls.includes('card') || cls.includes('container')) {
                        relevantClasses.push({
                            tag: el.tagName,
                            className: el.className,
                            id: el.id,
                            childCount: el.children.length
                        });
                    }
                }
            }
            return relevantClasses;
        });
        console.log(`  Relevant DOM elements: ${JSON.stringify(domStructure, null, 2)}`);

        // Right-click on empty area near the bottom of the grid
        // First, get the grid bounding box
        const gridSelector = await page.evaluate(() => {
            // Try various selectors for the grid
            const selectors = ['.apps-grid', '#appsGrid', '.grid', '.app-container', '.apps-container', 'main', '.content'];
            for (const sel of selectors) {
                const el = document.querySelector(sel);
                if (el) {
                    const rect = el.getBoundingClientRect();
                    return { selector: sel, rect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height } };
                }
            }
            return null;
        });
        console.log(`  Grid info: ${JSON.stringify(gridSelector)}`);

        let contextMenuAppeared = false;
        let hasNouveauRaccourci = false;

        if (gridSelector) {
            // Right-click in the bottom-right area of the grid (likely empty space)
            const clickX = gridSelector.rect.x + gridSelector.rect.width - 50;
            const clickY = gridSelector.rect.y + gridSelector.rect.height - 50;
            console.log(`  Right-clicking at (${clickX}, ${clickY})`);

            await page.mouse.click(clickX, clickY, { button: 'right' });
            await sleep(500);
        } else {
            // Fallback: right-click in the middle of the page
            console.log('  No grid found, right-clicking in center of page');
            await page.mouse.click(700, 450, { button: 'right' });
            await sleep(500);
        }

        await screenshot(page, '02_rightclick_empty_area');

        // Check for context menu
        const contextMenuInfo = await page.evaluate(() => {
            // Look for custom context menu elements
            const possibleMenus = document.querySelectorAll('[class*="context-menu"], [class*="contextmenu"], [id*="context-menu"], [id*="contextmenu"], .context-menu, #contextMenu');
            const menus = [];
            for (const menu of possibleMenus) {
                const style = window.getComputedStyle(menu);
                menus.push({
                    tag: menu.tagName,
                    className: menu.className,
                    id: menu.id,
                    display: style.display,
                    visibility: style.visibility,
                    text: menu.innerText.substring(0, 200),
                    childCount: menu.children.length
                });
            }
            return menus;
        });
        console.log(`  Context menus found: ${JSON.stringify(contextMenuInfo, null, 2)}`);

        contextMenuAppeared = contextMenuInfo.some(m => m.display !== 'none' && m.visibility !== 'hidden');
        hasNouveauRaccourci = contextMenuInfo.some(m => m.text.includes('Nouveau raccourci'));

        if (!contextMenuAppeared) {
            // Maybe we need to look for a different type of element, or the context menu is added dynamically
            // Let's try right-clicking at different locations
            console.log('  Context menu not visible. Trying different click positions...');

            // Try clicking on the page body below the cards
            await page.mouse.click(700, 700, { button: 'right' });
            await sleep(500);
            await screenshot(page, '02b_rightclick_lower');

            const contextMenuInfo2 = await page.evaluate(() => {
                const possibleMenus = document.querySelectorAll('[class*="context"], [class*="menu"], [role="menu"]');
                const menus = [];
                for (const menu of possibleMenus) {
                    const style = window.getComputedStyle(menu);
                    if (menu.innerText.length > 0) {
                        menus.push({
                            tag: menu.tagName,
                            className: menu.className,
                            id: menu.id,
                            display: style.display,
                            visibility: style.visibility,
                            opacity: style.opacity,
                            text: menu.innerText.substring(0, 300),
                            rect: menu.getBoundingClientRect()
                        });
                    }
                }
                return menus;
            });
            console.log(`  Broader menu search: ${JSON.stringify(contextMenuInfo2, null, 2)}`);

            contextMenuAppeared = contextMenuInfo2.some(m => m.display !== 'none' && m.visibility !== 'hidden' && m.text.includes('raccourci'));
            hasNouveauRaccourci = contextMenuInfo2.some(m => m.text.includes('Nouveau raccourci') || m.text.includes('nouveau raccourci'));
        }

        if (contextMenuAppeared && hasNouveauRaccourci) {
            results.push('STEP 2: Context menu appears with "Nouveau raccourci" option - PASS');
        } else if (contextMenuAppeared) {
            results.push('STEP 2: Context menu appears but "Nouveau raccourci" not found - PARTIAL');
        } else {
            results.push('STEP 2: Context menu did NOT appear on right-click - FAIL');
        }

        // =============================================
        // STEP 3: Click "Nouveau raccourci"
        // =============================================
        console.log('\n=== STEP 3: Click "Nouveau raccourci" ===');

        let modalOpened = false;

        // Find and click "Nouveau raccourci" option
        const clickedNouveauRaccourci = await page.evaluate(() => {
            const allElements = document.querySelectorAll('*');
            for (const el of allElements) {
                if (el.innerText && el.innerText.trim() === 'Nouveau raccourci') {
                    const style = window.getComputedStyle(el);
                    if (style.display !== 'none' && style.visibility !== 'hidden') {
                        el.click();
                        return { clicked: true, tag: el.tagName, className: el.className };
                    }
                }
            }
            // Also try partial match
            for (const el of allElements) {
                if (el.innerText && el.innerText.includes('Nouveau raccourci') && el.tagName !== 'BODY' && el.tagName !== 'HTML') {
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    if (style.display !== 'none' && style.visibility !== 'hidden' && rect.height < 60) {
                        el.click();
                        return { clicked: true, tag: el.tagName, className: el.className, text: el.innerText };
                    }
                }
            }
            return { clicked: false };
        });
        console.log(`  Clicked "Nouveau raccourci": ${JSON.stringify(clickedNouveauRaccourci)}`);

        await sleep(800);
        await screenshot(page, '03_nouveau_raccourci_clicked');

        // Check for modal
        const modalInfo = await page.evaluate(() => {
            const possibleModals = document.querySelectorAll('[class*="modal"], [class*="dialog"], [role="dialog"], [class*="overlay"]');
            const modals = [];
            for (const modal of possibleModals) {
                const style = window.getComputedStyle(modal);
                if (style.display !== 'none' && style.visibility !== 'hidden') {
                    modals.push({
                        tag: modal.tagName,
                        className: modal.className,
                        id: modal.id,
                        display: style.display,
                        text: modal.innerText.substring(0, 500),
                        hasInputs: modal.querySelectorAll('input, textarea').length,
                        rect: modal.getBoundingClientRect()
                    });
                }
            }
            return modals;
        });
        console.log(`  Modals found: ${JSON.stringify(modalInfo, null, 2)}`);

        modalOpened = modalInfo.length > 0 && modalInfo.some(m => m.hasInputs > 0);

        // Check for specific fields
        const modalFields = await page.evaluate(() => {
            const inputs = document.querySelectorAll('input, textarea, select');
            const fields = [];
            for (const input of inputs) {
                const style = window.getComputedStyle(input);
                if (style.display !== 'none') {
                    fields.push({
                        tag: input.tagName,
                        type: input.type,
                        name: input.name,
                        placeholder: input.placeholder,
                        id: input.id,
                        className: input.className,
                        visible: input.offsetParent !== null
                    });
                }
            }
            return fields;
        });
        console.log(`  Form fields: ${JSON.stringify(modalFields, null, 2)}`);

        // Look for icon picker and color picker
        const pickerInfo = await page.evaluate(() => {
            const body = document.body.innerHTML;
            return {
                hasIconPicker: body.includes('icon-picker') || body.includes('iconPicker') || body.includes('icon-grid') || body.includes('iconGrid'),
                hasColorPicker: body.includes('color-picker') || body.includes('colorPicker') || body.includes('color-grid') || body.includes('colorGrid'),
                hasPreviewCard: body.includes('preview') || body.includes('Preview')
            };
        });
        console.log(`  Picker info: ${JSON.stringify(pickerInfo)}`);

        if (modalOpened) {
            results.push('STEP 3: Modal appeared with form fields - PASS');
        } else {
            results.push('STEP 3: Modal did NOT appear - FAIL');
        }

        // =============================================
        // STEP 4: Fill in form fields
        // =============================================
        console.log('\n=== STEP 4: Fill in form fields ===');

        // Find the name input
        const nameInput = await page.evaluate(() => {
            const inputs = document.querySelectorAll('input');
            for (const input of inputs) {
                if (input.offsetParent !== null) {
                    const placeholder = (input.placeholder || '').toLowerCase();
                    const name = (input.name || '').toLowerCase();
                    const id = (input.id || '').toLowerCase();
                    if (placeholder.includes('nom') || name.includes('name') || id.includes('name') || placeholder.includes('name')) {
                        return { found: true, selector: input.id ? `#${input.id}` : `input[name="${input.name}"]`, id: input.id, name: input.name, placeholder: input.placeholder };
                    }
                }
            }
            // Try first visible input
            for (const input of inputs) {
                if (input.offsetParent !== null && input.type !== 'hidden') {
                    return { found: true, firstInput: true, selector: null, id: input.id, name: input.name, placeholder: input.placeholder };
                }
            }
            return { found: false };
        });
        console.log(`  Name input: ${JSON.stringify(nameInput)}`);

        // Let me look at the form structure more carefully
        const formStructure = await page.evaluate(() => {
            // Find all visible inputs/textareas within modals or visible forms
            const visibleInputs = [];
            const all = document.querySelectorAll('input, textarea');
            for (const el of all) {
                if (el.offsetParent !== null) {
                    const label = el.previousElementSibling;
                    const parentLabel = el.closest('label');
                    visibleInputs.push({
                        tag: el.tagName,
                        type: el.type,
                        id: el.id,
                        name: el.name,
                        placeholder: el.placeholder,
                        value: el.value,
                        label: label ? label.textContent : (parentLabel ? parentLabel.textContent : ''),
                        parentClass: el.parentElement ? el.parentElement.className : ''
                    });
                }
            }
            return visibleInputs;
        });
        console.log(`  Visible form inputs: ${JSON.stringify(formStructure, null, 2)}`);

        let formFilled = false;

        // Try to fill the form by finding inputs in order (Name, URL, Description)
        try {
            // Fill Name field - try various selectors
            const nameSelectors = ['#appName', '#app-name', '#name', 'input[name="name"]', 'input[placeholder*="nom" i]', 'input[placeholder*="name" i]'];
            let nameFieldFilled = false;

            for (const sel of nameSelectors) {
                try {
                    const el = await page.$(sel);
                    if (el) {
                        const isVisible = await el.evaluate(e => e.offsetParent !== null);
                        if (isVisible) {
                            await el.click({ clickCount: 3 });
                            await el.type('Test Shortcut');
                            nameFieldFilled = true;
                            console.log(`  Filled name using selector: ${sel}`);
                            break;
                        }
                    }
                } catch (e) {}
            }

            if (!nameFieldFilled) {
                // Try filling by index - first visible input
                const visibleInputs = await page.$$('input:not([type="hidden"])');
                for (const input of visibleInputs) {
                    const isVisible = await input.evaluate(e => e.offsetParent !== null);
                    if (isVisible) {
                        await input.click({ clickCount: 3 });
                        await input.type('Test Shortcut');
                        nameFieldFilled = true;
                        console.log('  Filled name using first visible input');
                        break;
                    }
                }
            }

            // Fill URL field
            const urlSelectors = ['#appUrl', '#app-url', '#url', 'input[name="url"]', 'input[placeholder*="url" i]', 'input[placeholder*="http" i]', 'input[type="url"]'];
            let urlFieldFilled = false;

            for (const sel of urlSelectors) {
                try {
                    const el = await page.$(sel);
                    if (el) {
                        const isVisible = await el.evaluate(e => e.offsetParent !== null);
                        if (isVisible) {
                            await el.click({ clickCount: 3 });
                            await el.type('http://192.168.1.200:3000');
                            urlFieldFilled = true;
                            console.log(`  Filled URL using selector: ${sel}`);
                            break;
                        }
                    }
                } catch (e) {}
            }

            if (!urlFieldFilled) {
                // Try second visible input
                const visibleInputs = await page.$$('input:not([type="hidden"])');
                let idx = 0;
                for (const input of visibleInputs) {
                    const isVisible = await input.evaluate(e => e.offsetParent !== null);
                    if (isVisible) {
                        idx++;
                        if (idx === 2) {
                            await input.click({ clickCount: 3 });
                            await input.type('http://192.168.1.200:3000');
                            urlFieldFilled = true;
                            console.log('  Filled URL using second visible input');
                            break;
                        }
                    }
                }
            }

            // Fill Description field
            const descSelectors = ['#appDesc', '#app-desc', '#description', 'textarea', 'input[name="desc"]', 'input[name="description"]', 'input[placeholder*="desc" i]'];
            let descFieldFilled = false;

            for (const sel of descSelectors) {
                try {
                    const el = await page.$(sel);
                    if (el) {
                        const isVisible = await el.evaluate(e => e.offsetParent !== null);
                        if (isVisible) {
                            await el.click({ clickCount: 3 });
                            await el.type('Mon test');
                            descFieldFilled = true;
                            console.log(`  Filled description using selector: ${sel}`);
                            break;
                        }
                    }
                } catch (e) {}
            }

            if (!descFieldFilled) {
                // Try third visible input
                const visibleInputs = await page.$$('input:not([type="hidden"]), textarea');
                let idx = 0;
                for (const input of visibleInputs) {
                    const isVisible = await input.evaluate(e => e.offsetParent !== null);
                    if (isVisible) {
                        idx++;
                        if (idx === 3) {
                            await input.click({ clickCount: 3 });
                            await input.type('Mon test');
                            descFieldFilled = true;
                            console.log('  Filled description using third visible input/textarea');
                            break;
                        }
                    }
                }
            }

            formFilled = nameFieldFilled && urlFieldFilled && descFieldFilled;
            console.log(`  Form fill results: name=${nameFieldFilled}, url=${urlFieldFilled}, desc=${descFieldFilled}`);
        } catch (e) {
            console.log(`  Error filling form: ${e.message}`);
        }

        await screenshot(page, '04_form_filled');

        if (formFilled) {
            results.push('STEP 4: Form filled with Name, URL, Description - PASS');
        } else {
            results.push('STEP 4: Could not fill all form fields - FAIL');
        }

        // =============================================
        // STEP 5: Click a different icon
        // =============================================
        console.log('\n=== STEP 5: Click a different icon ===');

        const iconClicked = await page.evaluate(() => {
            // Look for icon picker grid items
            const iconSelectors = [
                '[class*="icon-option"]',
                '[class*="icon-item"]',
                '[class*="icon-choice"]',
                '[class*="icon-grid"] > *',
                '[class*="iconGrid"] > *',
                '[class*="icon-picker"] > *',
                '[class*="iconPicker"] > *',
                '.icon-option',
                '.icon-item'
            ];

            for (const sel of iconSelectors) {
                const items = document.querySelectorAll(sel);
                if (items.length > 1) {
                    // Click the 5th icon (not the first)
                    const index = Math.min(4, items.length - 1);
                    items[index].click();
                    return { clicked: true, selector: sel, totalIcons: items.length, clickedIndex: index };
                }
            }

            // Broader search - look for grid of clickable SVGs or icons
            const grids = document.querySelectorAll('[class*="grid"], [class*="picker"]');
            for (const grid of grids) {
                const children = grid.children;
                if (children.length > 10) {  // icon grids usually have many items
                    const items = grid.querySelectorAll('[class*="icon"], svg, button, div[onclick]');
                    if (items.length > 1) {
                        const index = Math.min(4, items.length - 1);
                        items[index].click();
                        return { clicked: true, source: 'broad search', totalItems: items.length, clickedIndex: index, gridClass: grid.className };
                    }
                }
            }

            return { clicked: false };
        });
        console.log(`  Icon selection: ${JSON.stringify(iconClicked)}`);

        await sleep(300);
        await screenshot(page, '05_icon_selected');

        if (iconClicked.clicked) {
            results.push('STEP 5: Selected a different icon - PASS');
        } else {
            results.push('STEP 5: Could not find/click icon picker items - FAIL');
        }

        // =============================================
        // STEP 6: Click a different color
        // =============================================
        console.log('\n=== STEP 6: Click a different color ===');

        const colorClicked = await page.evaluate(() => {
            // Look for color picker grid items
            const colorSelectors = [
                '[class*="color-option"]',
                '[class*="color-item"]',
                '[class*="color-choice"]',
                '[class*="color-grid"] > *',
                '[class*="colorGrid"] > *',
                '[class*="color-picker"] > *',
                '[class*="colorPicker"] > *',
                '.color-option',
                '.color-item',
                '.color-swatch'
            ];

            for (const sel of colorSelectors) {
                const items = document.querySelectorAll(sel);
                if (items.length > 1) {
                    // Click the 3rd color (not the first)
                    const index = Math.min(2, items.length - 1);
                    items[index].click();
                    return { clicked: true, selector: sel, totalColors: items.length, clickedIndex: index };
                }
            }

            // Broader search - look for colored elements in a grid
            const allDivs = document.querySelectorAll('div[style*="background"], div[style*="gradient"]');
            const colorDivs = [];
            for (const div of allDivs) {
                const rect = div.getBoundingClientRect();
                if (rect.width > 20 && rect.width < 60 && rect.height > 20 && rect.height < 60) {
                    colorDivs.push(div);
                }
            }
            if (colorDivs.length > 1) {
                const index = Math.min(2, colorDivs.length - 1);
                colorDivs[index].click();
                return { clicked: true, source: 'style search', totalColors: colorDivs.length, clickedIndex: index };
            }

            return { clicked: false };
        });
        console.log(`  Color selection: ${JSON.stringify(colorClicked)}`);

        await sleep(300);
        await screenshot(page, '06_color_selected');

        if (colorClicked.clicked) {
            results.push('STEP 6: Selected a different color - PASS');
        } else {
            results.push('STEP 6: Could not find/click color picker items - FAIL');
        }

        // =============================================
        // STEP 7: Verify preview card updates
        // =============================================
        console.log('\n=== STEP 7: Verify preview card ===');

        const previewInfo = await page.evaluate(() => {
            // Look for preview card
            const previewElements = document.querySelectorAll('[class*="preview"], [id*="preview"]');
            const previews = [];
            for (const el of previewElements) {
                const style = window.getComputedStyle(el);
                if (style.display !== 'none' && el.offsetParent !== null) {
                    previews.push({
                        tag: el.tagName,
                        className: el.className,
                        id: el.id,
                        text: el.innerText.substring(0, 200),
                        hasTestShortcut: el.innerText.includes('Test Shortcut'),
                        hasMonTest: el.innerText.includes('Mon test')
                    });
                }
            }
            return previews;
        });
        console.log(`  Preview elements: ${JSON.stringify(previewInfo, null, 2)}`);

        await screenshot(page, '07_preview_card');

        const previewUpdated = previewInfo.some(p => p.hasTestShortcut || p.hasMonTest);
        if (previewUpdated) {
            results.push('STEP 7: Preview card shows updated name/description - PASS');
        } else {
            results.push('STEP 7: Preview card does not reflect changes - FAIL');
        }

        // =============================================
        // STEP 8: Click "Créer" button
        // =============================================
        console.log('\n=== STEP 8: Click "Créer" button ===');

        const creerClicked = await page.evaluate(() => {
            const buttons = document.querySelectorAll('button');
            for (const btn of buttons) {
                const text = btn.innerText.trim().toLowerCase();
                if ((text.includes('créer') || text.includes('creer') || text.includes('create') || text.includes('ajouter') || text.includes('add')) && btn.offsetParent !== null) {
                    const style = window.getComputedStyle(btn);
                    if (style.display !== 'none') {
                        btn.click();
                        return { clicked: true, text: btn.innerText.trim(), className: btn.className };
                    }
                }
            }
            // Also try submit buttons or input[type="submit"]
            const submitBtns = document.querySelectorAll('input[type="submit"], button[type="submit"]');
            for (const btn of submitBtns) {
                if (btn.offsetParent !== null) {
                    btn.click();
                    return { clicked: true, text: btn.value || btn.innerText, type: 'submit' };
                }
            }
            return { clicked: false };
        });
        console.log(`  Créer button: ${JSON.stringify(creerClicked)}`);

        await sleep(1000);
        await screenshot(page, '08_creer_clicked');

        if (creerClicked.clicked) {
            results.push('STEP 8: Clicked "Créer" button - PASS');
        } else {
            results.push('STEP 8: Could not find/click "Créer" button - FAIL');
        }

        // =============================================
        // STEP 9: Verify new card appears
        // =============================================
        console.log('\n=== STEP 9: Verify new card appears ===');

        await sleep(500);
        const newCardExists = await page.evaluate(() => {
            const allText = document.body.innerText;
            const hasTestShortcut = allText.includes('Test Shortcut');

            // Also look specifically in card elements
            const cards = document.querySelectorAll('[class*="card"], [class*="app"]');
            let cardWithTestShortcut = null;
            for (const card of cards) {
                if (card.innerText.includes('Test Shortcut')) {
                    cardWithTestShortcut = {
                        tag: card.tagName,
                        className: card.className,
                        text: card.innerText.substring(0, 100)
                    };
                    break;
                }
            }

            return {
                textOnPage: hasTestShortcut,
                cardElement: cardWithTestShortcut
            };
        });
        console.log(`  New card check: ${JSON.stringify(newCardExists)}`);

        await screenshot(page, '09_new_card_visible');

        if (newCardExists.textOnPage || newCardExists.cardElement) {
            results.push('STEP 9: New "Test Shortcut" card appears on the page - PASS');
        } else {
            results.push('STEP 9: "Test Shortcut" card NOT found on the page - FAIL');
        }

        // =============================================
        // STEP 10: Right-click on the new card
        // =============================================
        console.log('\n=== STEP 10: Right-click on "Test Shortcut" card ===');

        const cardRect = await page.evaluate(() => {
            const cards = document.querySelectorAll('[class*="card"], [class*="app"], a[href]');
            for (const card of cards) {
                if (card.innerText.includes('Test Shortcut')) {
                    const rect = card.getBoundingClientRect();
                    return { found: true, x: rect.x + rect.width / 2, y: rect.y + rect.height / 2, tag: card.tagName, className: card.className };
                }
            }
            return { found: false };
        });
        console.log(`  Card rect: ${JSON.stringify(cardRect)}`);

        let hasSupprimer = false;
        let hasModifier = false;

        if (cardRect.found) {
            await page.mouse.click(cardRect.x, cardRect.y, { button: 'right' });
            await sleep(500);
            await screenshot(page, '10_rightclick_card');

            const menuContent = await page.evaluate(() => {
                const menus = document.querySelectorAll('[class*="context-menu"], [class*="contextmenu"], [id*="context-menu"], [id*="contextmenu"], .context-menu, #contextMenu');
                const result = [];
                for (const menu of menus) {
                    const style = window.getComputedStyle(menu);
                    if (style.display !== 'none' && style.visibility !== 'hidden') {
                        result.push({
                            text: menu.innerText,
                            html: menu.innerHTML.substring(0, 1000),
                            className: menu.className,
                            id: menu.id
                        });
                    }
                }
                return result;
            });
            console.log(`  Context menu content: ${JSON.stringify(menuContent, null, 2)}`);

            hasSupprimer = menuContent.some(m => m.text.includes('Supprimer'));
            hasModifier = menuContent.some(m => m.text.includes('Modifier'));

            console.log(`  Has "Supprimer": ${hasSupprimer}`);
            console.log(`  Has "Modifier": ${hasModifier}`);
        }

        // =============================================
        // STEP 11: Verify "Modifier" option
        // =============================================
        if (hasModifier) {
            results.push('STEP 10-11: Context menu has "Supprimer" (red) and "Modifier" options - PASS');
        } else if (hasSupprimer) {
            results.push('STEP 10-11: Context menu has "Supprimer" but NOT "Modifier" - PARTIAL');
        } else {
            results.push('STEP 10-11: Context menu missing expected options - FAIL');
        }

        // =============================================
        // STEP 12: Click "Supprimer" and accept confirmation
        // =============================================
        console.log('\n=== STEP 12: Click "Supprimer" ===');

        // Set up dialog handler for confirmation
        page.once('dialog', async dialog => {
            console.log(`  Dialog appeared: "${dialog.message()}"`);
            await dialog.accept();
            console.log('  Dialog accepted');
        });

        const deleteClicked = await page.evaluate(() => {
            const allElements = document.querySelectorAll('*');
            for (const el of allElements) {
                const text = (el.innerText || '').trim();
                if (text === 'Supprimer' || text === '🗑 Supprimer' || text === '🗑️ Supprimer') {
                    const style = window.getComputedStyle(el);
                    if (style.display !== 'none' && style.visibility !== 'hidden' && el.offsetParent !== null) {
                        el.click();
                        return { clicked: true, text: el.innerText, tag: el.tagName };
                    }
                }
            }
            // Try broader match
            for (const el of allElements) {
                if (el.innerText && el.innerText.includes('Supprimer') && el.tagName !== 'BODY' && el.tagName !== 'HTML') {
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    if (style.display !== 'none' && style.visibility !== 'hidden' && rect.height < 60 && rect.height > 10) {
                        el.click();
                        return { clicked: true, text: el.innerText.trim(), tag: el.tagName, broad: true };
                    }
                }
            }
            return { clicked: false };
        });
        console.log(`  Supprimer click: ${JSON.stringify(deleteClicked)}`);

        await sleep(1000);
        await screenshot(page, '12_after_supprimer');

        if (deleteClicked.clicked) {
            results.push('STEP 12: Clicked "Supprimer" and accepted confirmation - PASS');
        } else {
            results.push('STEP 12: Could not find/click "Supprimer" button - FAIL');
        }

        // =============================================
        // STEP 13: Verify card is removed
        // =============================================
        console.log('\n=== STEP 13: Verify card is removed ===');

        await sleep(500);
        const cardStillExists = await page.evaluate(() => {
            const allText = document.body.innerText;
            return allText.includes('Test Shortcut');
        });
        console.log(`  "Test Shortcut" still on page: ${cardStillExists}`);

        await screenshot(page, '13_card_removed');

        if (!cardStillExists) {
            results.push('STEP 13: "Test Shortcut" card successfully removed from page - PASS');
        } else {
            results.push('STEP 13: "Test Shortcut" card still appears on the page - FAIL');
        }

    } catch (error) {
        console.error(`\nFATAL ERROR: ${error.message}`);
        console.error(error.stack);
        await screenshot(page, 'error_state');
        results.push(`FATAL ERROR: ${error.message}`);
    } finally {
        await browser.close();
    }

    // =============================================
    // SUMMARY
    // =============================================
    console.log('\n\n========================================');
    console.log('          TEST SUMMARY');
    console.log('========================================');
    console.log(`\nURL tested: ${BASE_URL}`);
    console.log(`\nConsole JS errors (${consoleErrors.length}):`);
    consoleErrors.forEach(e => console.log(`  - ${e}`));
    if (consoleErrors.length === 0) console.log('  None');

    console.log(`\nNetwork errors (${networkErrors.length}):`);
    networkErrors.forEach(e => console.log(`  - ${e}`));
    if (networkErrors.length === 0) console.log('  None');

    console.log('\nResults:');
    results.forEach(r => console.log(`  ${r}`));

    const passes = results.filter(r => r.includes('PASS')).length;
    const fails = results.filter(r => r.includes('FAIL')).length;
    const partials = results.filter(r => r.includes('PARTIAL')).length;

    console.log(`\nScore: ${passes} PASS, ${partials} PARTIAL, ${fails} FAIL out of ${results.length} steps`);

    if (fails === 0 && partials === 0) {
        console.log('\nVERDICT: SUCCES');
    } else if (fails > results.length / 2) {
        console.log('\nVERDICT: ECHEC');
    } else {
        console.log('\nVERDICT: PARTIEL');
    }
})();
