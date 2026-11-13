// Portable, offline browser checks: serve real files, block external providers.
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const {chromium: playwright} = require('playwright-core');
const chromium = require('@sparticuz/chromium').default;
const root = path.resolve(__dirname, '..');
const server = http.createServer((req, res) => {
  const file = path.resolve(root, '.' + new URL(req.url, 'http://local').pathname);
  if (!file.startsWith(root + path.sep)) {res.writeHead(403).end(); return;}
  fs.readFile(file, (err, data) => {
    if (err) {res.writeHead(404).end(); return;}
    res.setHeader('Content-Type', file.endsWith('.js') ? 'text/javascript' : 'text/html');
    res.end(data);
  });
});
(async () => {
  let browser;
  try {
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    const port = server.address().port;
    if (!process.env.BROWSER_PATH && process.platform === 'linux') {
      const bundle = require('@sparticuz/chromium');
      const libRoot = await bundle.inflate(path.join(path.dirname(require.resolve('@sparticuz/chromium')), '../bin/al2023.tar.br'));
      bundle.setupLambdaEnvironment(path.join(libRoot, 'lib'));
    }
    const args = chromium.args.filter(arg => !arg.includes('disable-web-security') && !arg.includes('allow-running-insecure-content'));
    browser = await playwright.launch({executablePath: process.env.BROWSER_PATH || await chromium.executablePath(), args, headless: true});
    const page = await browser.newPage({viewport: {width: 1440, height: 1000}});
    await page.route('**/*', route => new URL(route.request().url()).hostname === '127.0.0.1' ? route.continue() : route.abort());
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(`http://127.0.0.1:${port}/rolling_returns.html`);
    await page.waitForFunction(() => typeof switchTab === 'function' && typeof Chart === 'function');
    for (let tab = 0; tab < 10; tab++) {
      await page.locator('#tabBtn' + tab).click();
      await page.waitForTimeout(300);
      assert.equal(await page.locator('#tabContent' + tab).isVisible(), true, `Tab ${tab}`);
      console.log(`PASS tab ${tab} opens`);
    }
    await page.evaluate(() => {
      const date = Object.keys(RAW_PE['Nifty 50']).sort().at(-1);
      const saved = GSEC_10Y[date];
      delete GSEC_10Y[date];
      try {
        document.getElementById('yieldGapIndexSelect').value = 'Nifty 50';
        renderYieldGapTab();
        if (yieldGapChartInstance.data.datasets[1].data.at(-1) !== null) throw new Error('Fabricated bond yield');
        if (!document.getElementById('yieldGapHoverHud').textContent.includes('unavailable')) throw new Error('False yield-gap signal');
      } finally {if (saved !== undefined) GSEC_10Y[date] = saved;}
      setCapeTimeframe('MAX');
      if (capeChartInstance.data.datasets[0].data[0] !== null) throw new Error('Incomplete smoothing window accepted');
      capeChartInstance.options.plugins.tooltip.external({tooltip: {dataPoints: [{dataIndex: 0}]}});
      if (!document.getElementById('capeHoverHud').textContent.includes('Incomplete')) throw new Error('Missing smoothing warning');
    });
    console.log('PASS missing bond yield and incomplete smoothed-P/E window warnings');
    await page.evaluate(() => switchFundAssetMode('stock'));
    await page.waitForTimeout(150);
    assert.ok(await page.evaluate(() => fundamentalsChartInstance.data.labels.length > 12));
    await page.evaluate(() => {setFundTimeframe('5Y'); setFundScaleType('linear');});
    assert.equal(await page.evaluate(() => fundamentalsChartInstance.options.scales.y.type), 'linear');
    await page.evaluate(() => {setFundScaleType('logarithmic'); resetFundZoom();});
    assert.equal(await page.evaluate(() => fundamentalsChartInstance.options.scales.y.type), 'logarithmic');
    await page.evaluate(() => {
      const chart = fundamentalsChartInstance;
      chart.zoomScale('x', {min: 10, max: 40}, 'none');
      const before = chart.scales.x.min;
      setFundScaleType('linear');
      if (fundamentalsChartInstance.scales.x.min !== before) throw new Error('Scale switch lost zoom window');
      fundamentalsChartInstance.pan({x: -40}, undefined, 'none');
      if (!fundamentalsChartInstance.isZoomedOrPanned()) throw new Error('Pan/zoom state lost');
      resetFundZoom();
      if (fundamentalsChartInstance.isZoomedOrPanned()) throw new Error('Reset did not clear zoom');
    });
    console.log('PASS fundamentals zoom, pan, scale-switch retention and reset');
    await page.evaluate(() => switchFundAssetMode('us_stock'));
    assert.ok(await page.evaluate(() => fundamentalsChartInstance.data.labels.length > 12));
    console.log('PASS cached Indian/US fundamentals and scale/timeframe controls');
    fs.mkdirSync(path.join(root, 'artifacts'), {recursive: true});
    await page.screenshot({path: path.join(root, 'artifacts/fundamentals.png')});
    await page.evaluate(() => {
      document.getElementById('fundStockInput').value = 'UNKNOWN';
      return fetchAndSelectStock(false);
    });
    assert.equal(await page.evaluate(() => fundamentalsChartInstance), null);
    assert.equal(await page.locator('#fundDecompTbody').textContent(), '');
    console.log('PASS unavailable stock clears previous chart and decomposition');
    await page.evaluate(async () => {
      switchFundAssetMode('stock');
      const original = fetchCustomStock;
      try {
        let finish;
        fetchCustomStock = () => new Promise(resolve => {finish = resolve;});
        document.getElementById('fundStockInput').value = 'DELAYED';
        const pending = fetchAndSelectStock(true);
        selectStockChip('TCS');
        finish({...TOP_STOCKS_DATA.RELIANCE, symbol: 'DELAYED'});
        await pending;
        if (fundSelectedStock !== 'TCS') throw new Error('Late response replaced newer selection');
        let calls = 0;
        fetchCustomStock = async () => {calls++; throw new Error('<img src=x onerror="window.injected=true">');};
        document.getElementById('fundStockInput').value = 'TCS';
        await fetchAndSelectStock(true);
        if (calls !== 1) throw new Error('Force refresh skipped the default proxy');
        if (document.querySelector('#fundStockStatus img') || window.injected) throw new Error('Unsafe error rendering');
        if (!document.getElementById('fundStockStatus').textContent.includes('showing cached data')) throw new Error('Missing refresh failure warning');
        if (document.getElementById('fundStockFetchBtn').disabled) throw new Error('Fetch button stuck disabled');
      } finally {fetchCustomStock = original;}
    });
    console.log('PASS late-request race, force refresh, cached fallback and safe error text');
    await page.evaluate(async () => {
      const status = document.getElementById('fundStockStatus');
      const button = document.getElementById('fundStockFetchBtn');
      function silent(stage) {
        if (status.textContent || !status.hidden || status.getClientRects().length) throw new Error(stage + ': status occupies layout');
      }
      function errorVisible(stage) {
        if (!status.textContent || status.hidden || !status.getClientRects().length) throw new Error(stage + ': missing visible error');
      }
      errorVisible('refresh failure');
      const original = fetchCustomStock;
      try {
        let finish;
        fetchCustomStock = () => new Promise(resolve => {finish = resolve;});
        document.getElementById('fundStockInput').value = 'TCS';
        const pending = fetchAndSelectStock(true);
        silent('fetch pending clears old error');
        if (!button.disabled) throw new Error('Fetch button must remain disabled during request');
        finish({...TOP_STOCKS_DATA.TCS, symbol:'TCS'}); await pending;
        silent('live success');
        if (button.disabled) throw new Error('Fetch button not restored after success');
        await fetchAndSelectStock(false); silent('Indian cache hit');
        fetchCustomStock = async () => {throw new Error('Test provider unavailable');};
        document.getElementById('fundStockInput').value = 'NOCACHEERROR';
        await fetchAndSelectStock(true); errorVisible('uncached provider failure');
        if (!status.textContent.includes('Test provider unavailable')) throw new Error('Error detail lost');
        selectStockChip('TCS'); silent('chip selection clears error');
        switchFundAssetMode('us_stock');
        document.getElementById('fundStockInput').value = 'UNKNOWN';
        await fetchAndSelectStock(false); errorVisible('unknown US ticker');
        document.getElementById('fundStockInput').value = 'AAPL';
        await fetchAndSelectStock(false); silent('US cache hit clears error');
        document.getElementById('fundStockInput').value = 'UNKNOWN';
        await fetchAndSelectStock(false); errorVisible('US error before mode switch');
        switchFundAssetMode('stock'); silent('mode switch clears error');
        let fail;
        fetchCustomStock = () => new Promise((resolve,reject) => {fail=reject;});
        document.getElementById('fundStockInput').value = 'STALEERROR';
        const stale = fetchAndSelectStock(true);
        selectStockChip('TCS');fail(new Error('Old request failed'));await stale;
        silent('stale failure does not overwrite selection');
      } finally {fetchCustomStock = original;}
    });
    console.log('PASS error-only stock status: no loading/success layout, preserved errors and reset/race behavior');
    await page.evaluate(async () => {
      const original = window.fetch;
      window.fetch = async () => ({ok: true, json: async () => ({datasets: [
        {metric: 'Price', values: ['06','05','04','03','02','01'].flatMap(m => [[`2024-${m}-28`, 200], [`2024-${m}-01`, 100]])},
        {metric: 'EPS', values: [['2024-01-01', 10]]},
      ]})});
      try {
        const data = await fetchCustomStock('FIXTURE');
        if (data.price['2024-01'] !== 200 || data.price['2024-06'] !== 200) throw new Error('Price aggregation depends on response order');
      } finally {window.fetch = original;}
    });
    console.log('PASS live price aggregation uses chronological month end');
    await page.evaluate(() => {
      selected.clear(); selected.add('Nifty 50'); selected.add('Nifty Next 50');
      weights['Nifty 50'] = 75; weights['Nifty Next 50'] = 25;
      document.getElementById('cfStartDate').value = '2010-01';
      document.getElementById('cfEndDate').value = '2025-12';
      document.getElementById('cfYears').value = '5';
      switchTab(3);
    });
    await page.waitForTimeout(150);
    for (const view of ['single', 'rolling']) {
      for (const mode of ['sip', 'swp', 'lumpsum']) {
        await page.evaluate(({view, mode}) => {
          currentCashflowView = view; currentCashflowMode = mode; runCashflowSim();
          if (!cashflowChart || !cashflowChart.data.labels.length) throw new Error('Missing cashflow chart');
          if (/NaN|Infinity|undefined/.test(document.getElementById('cfSummaryGrid').textContent)) throw new Error('Invalid KPI');
        }, {view, mode});
      }
    }
    await page.evaluate(() => {selected.clear(); runCashflowSim();});
    assert.equal(await page.evaluate(() => cashflowChart), null);
    assert.match(await page.locator('#cfNoData').textContent(), /positive-weight portfolio/);
    await page.evaluate(() => {selected.add('Nifty 50'); weights['Nifty 50'] = 100; renderMain();});
    console.log('PASS all six cashflow mode/view combinations and empty selection');
    await page.setViewportSize({width: 390, height: 844});
    await page.evaluate(() => switchTab(0));
    await page.waitForTimeout(200);
    assert.ok(await page.locator('#tabContent0').isVisible());
    assert.deepEqual(errors, [], 'Uncaught page errors');
    console.log('PASS mobile viewport and no uncaught JavaScript exceptions');
  } finally {
    if (browser) await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => {console.error(error); process.exitCode = 1;});
