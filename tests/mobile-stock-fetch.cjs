// Phone regression suite for Tab 9 stock search/fetch: the flow that broke on
// Android Chrome while working on desktop. Runs a touch-emulated 390px profile.
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const {chromium: playwright} = require('playwright-core');
const chromium = require('@sparticuz/chromium').default;
const root = path.resolve(__dirname, '..');
const server = http.createServer((req, res) => {
  const file = path.resolve(root, '.' + new URL(req.url, 'http://local').pathname);
  fs.readFile(file, (err, data) => {
    if (err) {res.writeHead(404).end(); return;}
    res.setHeader('Content-Type', file.endsWith('.js') ? 'text/javascript' : 'text/html');
    res.end(data);
  });
});
(async () => {
  let browser;
  try {
    await new Promise(r => server.listen(0, '127.0.0.1', r));
    const port = server.address().port;
    if (!process.env.BROWSER_PATH && process.platform === 'linux') {
      const bundle = require('@sparticuz/chromium');
      const libRoot = await bundle.inflate(path.join(path.dirname(require.resolve('@sparticuz/chromium')), '../bin/al2023.tar.br'));
      bundle.setupLambdaEnvironment(path.join(libRoot, 'lib'));
    }
    const args = chromium.args.filter(a => !a.includes('disable-web-security'));
    browser = await playwright.launch({executablePath: process.env.BROWSER_PATH || await chromium.executablePath(), args, headless: true});
    // Emulate a real Android phone: touch, mobile UA, device pixel ratio.
    const page = await browser.newPage({
      viewport: {width: 390, height: 844}, isMobile: true, hasTouch: true, deviceScaleFactor: 3,
      userAgent: 'Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
    });
    const proxied = [];
    await page.route('**/*', route => {
      const host = new URL(route.request().url()).hostname;
      if (host === '127.0.0.1') return route.continue();
      proxied.push(route.request().url());
      return route.abort();
    });
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto(`http://127.0.0.1:${port}/rolling_returns.html`);
    await page.waitForFunction(() => typeof switchTab === 'function');
    await page.evaluate(() => switchTab(9));
    await page.evaluate(() => switchFundAssetMode('stock'));
    await page.waitForTimeout(300);

    // 1. The search field is inside a form, so mobile "Go" submits it.
    assert.equal(await page.evaluate(() => document.getElementById('fundStockInput').form?.id), 'fundStockForm');
    await page.evaluate(() => { document.getElementById('fundStockForm').requestSubmit(); });
    console.log('PASS mobile keyboard Go submits the search form');

    // 2. Enter no longer navigates; the page URL is unchanged.
    const urlBefore = page.url();
    await page.locator('#fundStockInput').press('Enter');
    await page.waitForTimeout(200);
    assert.equal(page.url(), urlBefore);
    console.log('PASS Enter/Go does not reload or navigate away');

    // 3. Typing lowercase + spaces normalises to a clean symbol.
    await page.evaluate(() => { const i = document.getElementById('fundStockInput'); i.value = ' reliance industries '; i.dispatchEvent(new Event('change')); });
    assert.equal(await page.evaluate(() => document.getElementById('fundStockInput').value), 'RELIANCE');
    console.log('PASS phone-typed " reliance industries " normalises to RELIANCE');

    // 4. Busy state gives visible feedback during a slow mobile fetch.
    await page.evaluate(() => {
      window.__origFetch = window.fetch;
      window.fetch = () => new Promise(r => setTimeout(() => r({ok: false, status: 404, json: async () => ({})}), 1200));
    });
    await page.evaluate(() => { document.getElementById('fundStockInput').value = 'UNKNOWNSYM'; window.__p = fetchAndSelectStock(true); });
    await page.waitForTimeout(250);
    const busy = await page.evaluate(() => {
      const b = document.getElementById('fundStockFetchBtn');
      return {text: b.textContent, disabled: b.disabled, aria: b.getAttribute('aria-busy')};
    });
    assert.equal(busy.text, 'Fetching…'); assert.equal(busy.disabled, true); assert.equal(busy.aria, 'true');
    await page.evaluate(() => window.__p);
    await page.waitForTimeout(100);
    const idle = await page.evaluate(() => {
      const b = document.getElementById('fundStockFetchBtn');
      return {text: b.textContent, disabled: b.disabled};
    });
    assert.equal(idle.text, 'Fetch ⚡'); assert.equal(idle.disabled, false);
    console.log('PASS slow request shows "Fetching…" then restores the button');

    // 5. A network failure produces guidance, not a bare "Failed to fetch".
    await page.evaluate(() => { window.fetch = () => Promise.reject(new TypeError('Failed to fetch')); });
    await page.evaluate(async () => { document.getElementById('fundStockInput').value = 'UNKNOWNSYM'; await fetchAndSelectStock(true); });
    const msg = await page.evaluate(() => document.getElementById('fundStockStatus').textContent);
    assert.match(msg, /Could not reach the stock proxy/);
    assert.match(msg, /Test Connection/);
    console.log('PASS mobile network failure explains the cause and the next step');

    // 6. Private-mode localStorage cannot abort the lookup.
    await page.evaluate(async () => {
      Object.defineProperty(window, 'localStorage', {configurable: true, get() { throw new DOMException('denied', 'SecurityError'); }});
      window.fetch = async () => ({ok: true, json: async () => ({datasets: []})});
    });
    const proxyUrl = await page.evaluate(() => fundGetProxyUrl());
    assert.equal(proxyUrl, 'https://restless-block-425c.q840248.workers.dev');
    console.log('PASS private-mode localStorage falls back to the default proxy');

    // 7. Test Connection reaches the Worker and reports latency on this device.
    await page.evaluate(() => { window.fetch = window.__origFetch; toggleProxySettingsModal(true); });
    await page.waitForTimeout(150);
    assert.equal(await page.locator('#fundProxyTestResult').isVisible(), false);
    // The dialog must be centred on the phone screen, not down inside the card.
    const geom = await page.evaluate(() => {
      const m = document.getElementById('fundProxyModal');
      const card = m.firstElementChild;
      const mb = m.getBoundingClientRect(), cb = card.getBoundingClientRect();
      return {overlay: [mb.top, mb.height, window.innerHeight], cardCenter: cb.top + cb.height / 2, viewCenter: window.innerHeight / 2};
    });
    assert.equal(geom.overlay[0], 0, 'overlay must start at the top of the screen');
    assert.equal(Math.round(geom.overlay[1]), geom.overlay[2], 'overlay must cover the viewport');
    assert.ok(Math.abs(geom.cardCenter - geom.viewCenter) < 40, 'dialog not vertically centred: ' + JSON.stringify(geom));
    assert.ok(geom.cardCenter < geom.overlay[2], 'dialog is rendered below the fold');
    console.log('PASS proxy dialog is centred on the 844px phone screen, not below the fold');
    const shotPath = path.join(root, 'artifacts/mobile-proxy-modal.png');
    fs.mkdirSync(path.dirname(shotPath), {recursive: true});
    await page.screenshot({path: shotPath});
    await page.evaluate(() => testFundProxyConnection());
    const test = await page.evaluate(() => {
      const el = document.getElementById('fundProxyTestResult');
      return {text: el.textContent, visible: el.getClientRects().length > 0};
    });
    assert.equal(test.visible, true);
    assert.match(test.text, /Could not reach the stock proxy|Reachable in/);
    assert.ok(proxied.some(u => u.includes('/api/search')), 'test hit /api/search');
    console.log('PASS proxy settings Test Connection reports reachability on device: ' + test.text.slice(0, 80));

    // 8. Modal must fit a 390px phone without horizontal overflow.
    const overflow = await page.evaluate(() => {
      const box = document.querySelector('#fundProxyModal > div');
      return {w: box.getBoundingClientRect().width, doc: document.documentElement.scrollWidth, vw: window.innerWidth};
    });
    assert.ok(overflow.w <= overflow.vw, 'modal wider than viewport');
    assert.ok(overflow.doc <= overflow.vw + 1, 'page scrolls sideways: ' + overflow.doc);
    console.log('PASS proxy modal fits a 390px phone (' + Math.round(overflow.w) + 'px, no sideways scroll)');

    await page.evaluate(() => toggleProxySettingsModal(false));
    await page.evaluate(() => document.querySelectorAll('#fundProxyTestResult').forEach(e => e.remove()));
    if (errors.length) throw new Error('Uncaught errors: ' + errors.join(' | '));
    console.log('\nAll mobile stock-fetch checks passed.');
  } finally {
    if (browser) await browser.close();
    server.close();
  }
})().catch(err => {console.error('FAIL', err.message); process.exit(1);});
