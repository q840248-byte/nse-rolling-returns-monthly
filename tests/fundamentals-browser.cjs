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
    await page.evaluate(() => {
      Chart.defaults.animation = false;
      switchTab(9);
      window.installFundFixture = function(data) {
        fundAssetMode = 'stock'; fundSelectedStock = 'FIXTURE';
        fundCustomStockData.FIXTURE = {symbol: 'FIXTURE', ...data};
        fundTimeframe = 'MAX'; fundScaleType = 'linear';
        ['chkFundPrice','chkFundEps','chkFundPe','chkFundTrimmedEps'].forEach(id => document.getElementById(id).checked = true);
        renderFundamentalsTab();
      };
      window.compoundFixture = function() {
        const price = {}, eps = {}, pe = {}, dates = [];
        for (let i = 0; i <= 180; i++) {
          const d = addMonths('2010-01', i); dates.push(d);
          price[d] = 100 * Math.pow(1.2, i / 12);
          eps[d] = 10 * Math.pow(1.1, i / 12); pe[d] = price[d] / eps[d];
        }
        return {dates, price, eps, pe};
      };
    });
    await page.waitForTimeout(100);
    let passed = 0, failed = 0;
    async function check(name, fn) {
      try {await fn(); console.log('PASS ' + name); passed++;}
      catch (error) {console.error('FAIL ' + name + ': ' + error.message); failed++;}
    }
    await check('fresh Fundamentals defaults to Price/EPS/Trim with P/E unchecked',async()=>{
      const state=await page.evaluate(()=>({
        labels:[...document.querySelectorAll('#tabContent9 .fund-checkbox-label')].map(el=>el.textContent.trim()),
        pe:document.getElementById('chkFundPe').checked,
        peVisible:fundamentalsChartInstance.isDatasetVisible(2),axis:fundamentalsChartInstance.options.scales.yPe.display,
        entries:[...document.querySelectorAll('#fundHoverHud [data-fund-series]')].map(el=>el.dataset.fundSeries)
      }));
      assert.deepEqual(state.labels,['Price','EPS Value','P/E','Trim. EPS Value']);
      assert.equal(state.pe,false);assert.equal(state.peVisible,false);assert.equal(state.axis,false);
      assert.deepEqual(state.entries,['chkFundPrice','chkFundEps','chkFundTrimmedEps']);
    });
    await check('analytical 20% price, 10% EPS, 9.1% multiple CAGR decomposition', async () => {
      const data = await page.evaluate(() => {
        installFundFixture(compoundFixture());
        return {rows: [...document.querySelectorAll('#fundDecompTbody tr')].map(r => [...r.cells].map(c => c.textContent))};
      });
      for (const row of data.rows) {assert.equal(row[1], '+20.0%/yr'); assert.equal(row[2], '+10.0%/yr'); assert.equal(row[3], '+9.1%/yr');}
    });
    await check('all stock price/IV lines off hides the primary axis (no phantom trimmed series)', async () => {
      assert.equal(await page.evaluate(() => {
        installFundFixture(compoundFixture());
        document.getElementById('chkFundPrice').checked = false;
        document.getElementById('chkFundEps').checked = false;
        updateFundSeriesVisibility();
        return fundamentalsChartInstance.options.scales.y.display;
      }), false);
    });
    await check('empty cached dataset clears chart instead of crashing', async () => {
      assert.equal(await page.evaluate(() => {installFundFixture({dates: [], price: {}, eps: {}, pe: {}}); return fundamentalsChartInstance === null;}), true);
    });
    await check('unsorted duplicate cached dates are normalized', async () => {
      const labels = await page.evaluate(() => {
        const data = compoundFixture(); data.dates = [data.dates[10], data.dates[0], data.dates[10]];
        // The dates metadata must not hide valid entries in the price history.
        installFundFixture(data); return fundamentalsChartInstance.data.labels;
      });
      assert.equal(labels[0], '2010-01'); assert.equal(labels.at(-1), '2025-01'); assert.equal(labels.length, 181);
    });
    await check('no fabricated 20x IV for an asset without a positive P/E history', async () => {
      const values = await page.evaluate(() => {
        installFundFixture({price: {'2020-01': 100, '2021-01': 120}, eps: {'2020-01': -10, '2021-01': -12}, pe: {'2020-01': null, '2021-01': null}});
        return fundamentalsChartInstance.data.datasets[1].data;
      });
      assert.ok(values.every(v => v === null));
    });
    await check('rolling controls, dataset, axis, and heatmap plugin are completely removed', async () => {
      const state = await page.evaluate(() => {
        installFundFixture(compoundFixture());
        return {labels: fundamentalsChartInstance.data.datasets.map(ds=>ds.label),
          removedControls: ['chkFundRolling','chkFundHeatmap','fundHoriz1Y','fundHoriz3Y','fundHoriz5Y','fundHoriz10Y'].every(id=>!document.getElementById(id)),
          axes: Object.keys(fundamentalsChartInstance.options.scales), plugins: (fundamentalsChartInstance.config.plugins || []).map(p=>p.id)};
      });
      assert.deepEqual(state.labels,['Price','EPS Value','P/E','Trim. EPS Value']);
      assert.equal(state.removedControls,true);
      assert.ok(!state.axes.includes('yCagr'));
      assert.ok(!state.plugins.includes('pePercentileHeatmap'));
    });
    await check('three-year decomposition does not substitute a four-year window', async () => {
      const row = await page.evaluate(() => {
        installFundFixture({price: {'2020-01': 100, '2024-01': 200}, eps: {'2020-01': 10, '2024-01': 20}, pe: {'2020-01': 10, '2024-01': 10}});
        return document.querySelector('#fundDecompTbody tr').textContent;
      });
      assert.match(row, /Insufficient|Missing/);
    });
    await check('zoomed axis labels resolve category values, not local tick positions', async () => {
      const labels = await page.evaluate(() => {
        installFundFixture(compoundFixture());
        return {actual: fundamentalsChartInstance.options.scales.x.ticks.callback(120, 0), expected: '2020'};
      });
      assert.equal(labels.actual, labels.expected);
    });
    await check('scale switch synchronizes HUD to restored zoom window', async () => {
      const data = await page.evaluate(() => {
        installFundFixture(compoundFixture());
        fundamentalsChartInstance.zoomScale('x', {min: 10, max: 40}, 'none');
        setFundScaleType('logarithmic');
        return {date: fundamentalsChartInstance.data.labels[40], hud: document.getElementById('fundHoverHud').textContent};
      });
      assert.ok(data.hud.includes(data.date));
    });
    await check('reset zoom retains selected timeframe rather than falling back to MAX', async () => {
      assert.equal(await page.evaluate(() => {
        installFundFixture(compoundFixture()); setFundTimeframe('5Y');
        fundamentalsChartInstance.zoomScale('x', {min: 5, max: 20}, 'none');
        resetFundZoom(); return fundTimeframe;
      }), '5Y');
    });
    await check('no-data chart clearing removes stale mouseleave HUD callbacks', async () => {
      const text = await page.evaluate(() => {
        installFundFixture(compoundFixture()); fundSelectedStock = 'UNAVAILABLE'; renderFundamentalsTab();
        const canvas = document.getElementById('fundamentalsChart');
        canvas.dispatchEvent(new MouseEvent('mouseleave'));
        return document.getElementById('fundHoverHud').textContent;
      });
      assert.ok(!text.includes('FIXTURE'));
    });
    await check('index with no matching PE/trim dates clears an unrelated chart', async () => {
      assert.equal(await page.evaluate(() => {
        installFundFixture(compoundFixture());
        RAW['Fixture Index'] = {'2020-01': 100}; RAW_PE['Fixture Index'] = {'2021-01': 20};
        try {
          fundAssetMode = 'index'; renderFundamentalsTab();
          document.getElementById('fundIndexSelect').value = 'Fixture Index'; renderFundamentalsTab();
          return fundamentalsChartInstance === null;
        } finally {delete RAW['Fixture Index']; delete RAW_PE['Fixture Index'];}
      }), true);
    });
    await check('missing trimmed observation remains unavailable, not silently extrapolated', async () => {
      assert.equal(await page.evaluate(() => {
        RAW['Fixture Index'] = {'2020-01': 100, '2020-02': 110};
        RAW_PE['Fixture Index'] = {'2020-01': 10, '2020-02': 10};
        ALL_INDICES_TRIMMED_EPS['Fixture Index'] = {'2020-01': 8};
        try {
          fundAssetMode = 'index'; renderFundamentalsTab();
          document.getElementById('fundIndexSelect').value = 'Fixture Index'; renderFundamentalsTab();
          return fundamentalsChartInstance.data.datasets[3].data.at(-1);
        } finally {delete RAW['Fixture Index']; delete RAW_PE['Fixture Index']; delete ALL_INDICES_TRIMMED_EPS['Fixture Index'];}
      }), null);
    });
    await check('IV rebasing preserves Price/IV and the full-history median across timeframes', async () => {
      const data = await page.evaluate(() => {
        const fixture = compoundFixture(); installFundFixture(fixture);
        const multiples = Object.values(fixture.pe).sort((a,b) => a-b);
        const median = multiples[Math.floor(multiples.length / 2)];
        function latest() {return fundamentalsChartInstance.data.datasets.slice(0,2).map(ds => ds.data.at(-1));}
        const max = latest(); setFundTimeframe('3Y'); const short = latest();
        return {max, short, expected: fixture.pe['2025-01'] / median};
      });
      assert.ok(Math.abs(data.max[0] / data.max[1] - data.expected) < .0002);
      assert.ok(Math.abs(data.short[0] / data.short[1] - data.expected) < .0002);
    });
    await check('loss/zero EPS: no valid P/E, log gaps, negative linear IV, no invented bridge', async () => {
      const data = await page.evaluate(() => {
        installFundFixture({price: {'2020-01': 100, '2020-02': 100, '2020-03': 100, '2020-04': 100}, eps: {'2020-01': 10, '2020-02': -10, '2020-03': 0, '2020-04': 10}});
        const linear = fundamentalsChartInstance.data.datasets[1].data.slice();
        const pe = fundamentalsChartInstance.data.datasets[2].data.slice();
        setFundScaleType('logarithmic');
        return {linear, pe, log: fundamentalsChartInstance.data.datasets[1].data, spanGaps: fundamentalsChartInstance.data.datasets[1].spanGaps};
      });
      assert.deepEqual(data.linear, [100,-100,0,100]);
      assert.deepEqual(data.pe, [10,null,null,10]);
      assert.deepEqual(data.log, [100,null,null,100]);
      assert.equal(data.spanGaps, false);
    });
    await check('P/E legend shows only a multiple, without percentile or rolling values', async () => {
      const values = await page.evaluate(() => {
        installFundFixture({price:{'2020-01':100,'2020-02':100,'2020-03':100},eps:{'2020-01':10,'2020-02':20,'2020-03':5}});
        return [0,1,2].map(index=>{
          fundamentalsChartInstance.options.onHover({native:{}},[{index}]);
          return document.querySelector('[data-fund-series="chkFundPe"]').textContent;
        });
      });
      assert.deepEqual(values,['P/E: 10.0x','P/E: 5.0x','P/E: 20.0x']);
    });
    await check('hidden valuation lines do not continue emitting an IV gap badge', async () => {
      const hud = await page.evaluate(() => {
        installFundFixture(compoundFixture()); document.getElementById('chkFundEps').checked = false; updateFundSeriesVisibility();
        return document.getElementById('fundHoverHud').textContent;
      });
      assert.doesNotMatch(hud, /Overvalued|Undervalued|Fairly Priced/);
    });
    await check('negative trimmed EPS remains readable without extra valuation badges', async () => {
      const hud = await page.evaluate(() => {
        RAW['Fixture Index'] = {'2020-01': 100, '2020-02': 110}; RAW_PE['Fixture Index'] = {'2020-01': 10, '2020-02': 10};
        ALL_INDICES_TRIMMED_EPS['Fixture Index'] = {'2020-01': 8, '2020-02': -8};
        try {
          fundAssetMode = 'index'; renderFundamentalsTab(); document.getElementById('fundIndexSelect').value = 'Fixture Index';
          document.getElementById('chkFundTrimmedEps').checked = true; document.getElementById('chkFundEps').checked = false; renderFundamentalsTab();
          return document.getElementById('fundHoverHud').textContent;
        } finally {delete RAW['Fixture Index']; delete RAW_PE['Fixture Index']; delete ALL_INDICES_TRIMMED_EPS['Fixture Index'];}
      });
      assert.match(hud, /Trim\. EPS Value: ₹-80\.0 \(-80\)/);
      assert.doesNotMatch(hud, /Net Loss|Overvalued|Undervalued|Fairly Priced/);
    });
    await check('legend currency and rebased values track hover and timeframe changes',async()=>{
      const result=await page.evaluate(()=>{
        installFundFixture({price:{'2020-01':100,'2024-01':200},eps:{'2020-01':10,'2024-01':20}});
        function values(){return [...document.querySelectorAll('#fundHoverHud [data-fund-series]')].map(e=>e.textContent);}
        const latest=values();
        fundamentalsChartInstance.options.onHover({native:{}},[{index:0}]);const first=values();
        setFundTimeframe('3Y');const short=values();
        return {latest,first,short};
      });
      assert.deepEqual(result.latest,['Price: ₹200.0 (200)','EPS Value: ₹200.0 (200)','P/E: 10.0x']);
      assert.deepEqual(result.first,['Price: ₹100.0 (100)','EPS Value: ₹100.0 (100)','P/E: 10.0x']);
      assert.deepEqual(result.short,['Price: ₹200.0 (100)','EPS Value: ₹200.0 (100)','P/E: 10.0x']);
    });
    await check('all embedded indices, Indian stocks and US stocks render finite datasets', async () => {
      const counts = await page.evaluate(() => {
        fundTimeframe = 'MAX'; fundScaleType = 'logarithmic';
        ['chkFundPrice','chkFundEps','chkFundPe','chkFundTrimmedEps'].forEach(id => document.getElementById(id).checked = true);
        function validate(key) {
          const c = fundamentalsChartInstance;
          if (!c || !c.data.labels.length) throw new Error('Missing chart for ' + key);
          for (const ds of c.data.datasets) {
            if (ds.data.length !== c.data.labels.length || ds.data.some(v => v !== null && !Number.isFinite(v))) throw new Error('Invalid dataset: ' + key + ' / ' + ds.label);
          }
          if (/NaN|Infinity|undefined/.test(document.getElementById('fundHoverHud').textContent + document.getElementById('fundDecompTbody').textContent)) throw new Error('Invalid text for ' + key);
        }
        fundAssetMode = 'index'; renderFundamentalsTab();
        const indices = [...document.getElementById('fundIndexSelect').options].map(o => o.value);
        for (const key of indices) {document.getElementById('fundIndexSelect').value = key; renderFundamentalsTab(); validate(key);}
        fundAssetMode = 'stock';
        for (const key of Object.keys(TOP_STOCKS_DATA)) {fundSelectedStock = key; renderFundamentalsTab(); validate(key);}
        fundAssetMode = 'us_stock';
        for (const key of Object.keys(READY_US_STOCKS)) {fundSelectedUsStock = key; renderFundamentalsTab(); validate(key);}
        return {indices: indices.length, indian: Object.keys(TOP_STOCKS_DATA).length, us: Object.keys(READY_US_STOCKS).length};
      });
      assert.deepEqual(counts, {indices: 56, indian: 67, us: 9});
      console.log('  Catalog sweep:', JSON.stringify(counts));
    });
    await check('all series toggles and axes behave in each of the three asset modes', async () => {
      await page.evaluate(() => {
        const toggles = ['chkFundPrice','chkFundEps','chkFundPe','chkFundTrimmedEps'];
        for (const mode of ['index','stock','us_stock']) {
          switchFundAssetMode(mode);
          for (let i = 0; i < toggles.length; i++) {
            document.getElementById(toggles[i]).checked = false; updateFundSeriesVisibility();
            if (fundamentalsChartInstance.isDatasetVisible(i)) throw new Error(mode + ': failed to hide ' + toggles[i]);
            if (document.querySelector('[data-fund-series="'+toggles[i]+'"]')) throw new Error(mode+': hidden legend entry remains');
          }
          if (fundamentalsChartInstance.options.scales.y.display || fundamentalsChartInstance.options.scales.yPe.display) throw new Error('Axis still visible: ' + mode);
          toggles.forEach(id => document.getElementById(id).checked = true); updateFundSeriesVisibility();
          if (mode !== 'index' && fundamentalsChartInstance.isDatasetVisible(3)) throw new Error('Stock trimmed series visible');
          const entries=[...document.querySelectorAll('#fundHoverHud [data-fund-series]')];
          if (entries.length !== (mode==='index'?4:3)) throw new Error('Missing selected legend entry');
          if (mode==='us_stock' && !entries[0].textContent.includes('$')) throw new Error('US currency incorrect');
        }
      });
    });
    await check('every checkbox combination has exactly the matching legend entries',async()=>{
      await page.evaluate(()=>{
        const ids=['chkFundPrice','chkFundEps','chkFundPe','chkFundTrimmedEps'];
        for(const mode of ['index','stock','us_stock']) {
          switchFundAssetMode(mode);
          for(let mask=0;mask<16;mask++) {
            ids.forEach((id,i)=>document.getElementById(id).checked=Boolean(mask&(1<<i)));
            updateFundSeriesVisibility();
            const expected=ids.filter((id,i)=>Boolean(mask&(1<<i))&&(i!==3||mode==='index'));
            const actual=[...document.querySelectorAll('#fundHoverHud [data-fund-series]')].map(el=>el.dataset.fundSeries);
            if(JSON.stringify(actual)!==JSON.stringify(expected))throw new Error(mode+' '+mask+': '+actual);
            fundamentalsChartInstance.options.onHover({native:{}},[{index:0}]);
            const hovered=[...document.querySelectorAll('#fundHoverHud [data-fund-series]')].map(el=>el.dataset.fundSeries);
            if(JSON.stringify(hovered)!==JSON.stringify(expected))throw new Error('Hover restored hidden entries');
          }
        }
      });
    });
    await check('P/E stays unchecked through rerenders until the user enables it',async()=>{
      const state=await page.evaluate(()=>{
        document.getElementById('chkFundPe').checked=false;
        for(const mode of ['index','stock','us_stock']) {
          switchFundAssetMode(mode);setFundTimeframe('5Y');setFundScaleType('linear');resetFundZoom();
          if(fundamentalsChartInstance.isDatasetVisible(2)||document.querySelector('[data-fund-series="chkFundPe"]'))throw new Error('P/E unexpectedly enabled');
        }
        document.getElementById('chkFundPe').checked=true;updateFundSeriesVisibility();
        return {visible:fundamentalsChartInstance.isDatasetVisible(2),axis:fundamentalsChartInstance.options.scales.yPe.display};
      });
      assert.deepEqual(state,{visible:true,axis:true});
    });
    await check('US ticker suggestions survive focusing the search input', async () => {
      await page.evaluate(() => switchFundAssetMode('us_stock'));
      await page.locator('#fundStockInput').focus();
      const options = await page.locator('#fundStockDatalist option').evaluateAll(nodes => nodes.map(n => n.value));
      assert.ok(options.includes('AAPL')); assert.ok(!options.includes('RELIANCE'));
    });
    await check('real mouse wheel zoom and drag pan update the visible window', async () => {
      await page.evaluate(() => {installFundFixture(compoundFixture());});
      const canvas = page.locator('#fundamentalsChart');
      await canvas.scrollIntoViewIfNeeded();
      const box = await canvas.boundingBox();
      const x = box.x + box.width * 0.55, y = box.y + box.height * 0.5;
      await page.mouse.move(x, y); await page.mouse.wheel(0, -500); await page.waitForTimeout(200);
      assert.equal(await page.evaluate(() => fundamentalsChartInstance.isZoomedOrPanned()), true);
      const before = await page.evaluate(() => fundamentalsChartInstance.scales.x.min);
      await page.mouse.move(x, y); await page.mouse.down(); await page.mouse.move(x - 90, y, {steps: 12}); await page.mouse.up();
      await page.waitForTimeout(100);
      const after = await page.evaluate(() => fundamentalsChartInstance.scales.x.min);
      assert.notEqual(after, before);
      await page.evaluate(() => {resetFundZoom(); switchFundAssetMode('index');});
    });
    fs.mkdirSync(path.join(root, 'artifacts'), {recursive: true});
    await page.evaluate(()=>{document.getElementById('chkFundPe').checked=false;document.getElementById('fundIndexSelect').value='Nifty 50';setFundTimeframe('MAX');setFundScaleType('logarithmic');updateFundSeriesVisibility();document.getElementById('panel9').scrollIntoView({block:'start'});});
    await page.screenshot({path: path.join(root, 'artifacts/fundamentals-focused-desktop.png')});
    await page.setViewportSize({width: 390, height: 844});
    await page.waitForTimeout(150);
    await check('390px Fundamentals layout fits viewport and precedes the sidebar', async () => {
      const bounds = await page.evaluate(() => ({viewport: innerWidth, width: document.documentElement.scrollWidth,
        tabTop: document.getElementById('tabContent9').getBoundingClientRect().top,
        sidebarTop: document.querySelector('.sidebar').getBoundingClientRect().top}));
      assert.ok(bounds.width <= bounds.viewport + 1, JSON.stringify(bounds));
      assert.ok(bounds.tabTop < bounds.sidebarTop);
    });
    await page.locator('#tabContent9').scrollIntoViewIfNeeded();
    await page.screenshot({path: path.join(root, 'artifacts/fundamentals-focused-mobile.png')});
    console.log(`Fundamentals checks: ${passed} passed, ${failed} failed`);
    assert.equal(failed, 0, 'Fundamentals regression failures');
    assert.deepEqual(errors, [], 'Uncaught page errors');
  } finally {
    if (browser) await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => {console.error(error); process.exitCode = 1;});
