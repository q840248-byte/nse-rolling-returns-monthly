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

    await page.evaluate(() => { Chart.defaults.animation = false; });
    let passed = 0, failed = 0;
    async function check(name, fn) {
      try { await fn(); console.log('PASS ' + name); passed++; }
      catch (err) { console.error('FAIL ' + name + ': ' + err.message); failed++; }
    }
    const valuationCharts = ['rawPeChartInstance','harmPeChartInstance','dynPeChartInstance','yieldGapChartInstance','capeChartInstance'];
    await check('all ten tabs open, remain finite, and have unique document IDs', async () => {
      for (let tab=0;tab<10;tab++) {
        await page.locator('#tabBtn'+tab).click();
        await page.waitForTimeout(100);
        assert.ok(await page.locator('#tabContent'+tab).isVisible());
        const bad = await page.locator('#tabContent'+tab).innerText();
        assert.ok(!/\b(?:NaN|Infinity|undefined)\b/.test(bad), 'Invalid visible number in tab '+tab);
      }
      const duplicates=await page.evaluate(()=>{
        const ids=[...document.querySelectorAll('[id]')].map(e=>e.id);
        return ids.filter((id,i)=>ids.indexOf(id)!==i);
      });
      assert.deepEqual(duplicates,[]);
    });
    await check('category ticks use category values after axis zoom in Growth and all valuation tabs',async()=>{
      await page.evaluate(()=>{selected.add('Nifty 50');weights['Nifty 50']=100;switchTab(2);}); await page.waitForTimeout(100);
      for(const name of ['priceChart',...valuationCharts]) {
        const result=await page.evaluate(name=>{
          const c=name === 'priceChart' ? priceChart : window[name]; const labels=c.data.labels;
          const i=labels.findIndex((d,i)=>i>12 && d.endsWith('-01'));
          const callback=c.options.scales.x.ticks.callback;
          return {actual:callback.call(c.scales.x,i,0),expected:labels.length>60?labels[i].slice(0,4):labels[i]};
        },name);
        assert.equal(result.actual,result.expected,name);
      }
    });
    await check('P/E log axes include values below 8x',async()=>{
      const result=await page.evaluate(()=>{
        const saved=[...selected]; const old=RAW_PE['Nifty 50'];
        try {
          selected.clear();selected.add('Nifty 50'); RAW_PE['Nifty 50']={'2025-01':3,'2025-02':4};
          renderRawPeTab();renderHarmonizedPeTab();
          return [rawPeChartInstance.scales.y.min,harmPeChartInstance.scales.y.min];
        }finally{RAW_PE['Nifty 50']=old;selected.clear();saved.forEach(k=>selected.add(k));renderRawPeTab();renderHarmonizedPeTab();}
      });
      assert.ok(result.every(v=>v<=3),JSON.stringify(result));
    });
    await check('dynamic bands have no short-history five-year statistics or false fair-value badge',async()=>{
      await page.evaluate(()=>setDynPeTimeframe('MAX'));
      assert.equal(await page.evaluate(()=>dynPeChartInstance.data.datasets[2].data[0]),null);
      await page.evaluate(()=>dynPeChartInstance.options.plugins.tooltip.external({tooltip:{dataPoints:[{dataIndex:0}]}}));
      assert.match(await page.locator('#dynPeHoverHud').innerText(),/Incomplete/);
    });
    await check('empty valuation histories destroy stale chart instances',async()=>{
      const result=await page.evaluate(()=>{
        const old={...RAW_PE};
        try {
          Object.keys(RAW_PE).forEach(k=>delete RAW_PE[k]);
          renderRawPeTab();renderHarmonizedPeTab();renderDynamicBandsTab();renderYieldGapTab();renderCapeTab();
          return [rawPeChartInstance,harmPeChartInstance,dynPeChartInstance,yieldGapChartInstance,capeChartInstance].map(c=>c===null);
        }finally{Object.assign(RAW_PE,old);renderRawPeTab();renderHarmonizedPeTab();renderDynamicBandsTab();renderYieldGapTab();renderCapeTab();}
      });
      assert.deepEqual(result,[true,true,true,true,true]);
    });
    await check('valuation selectors refresh when index names change but count stays the same',async()=>{
      const result=await page.evaluate(()=>{
        const pe={...RAW_PE}, raw={...RAW};
        try {
          Object.keys(RAW_PE).forEach(k=>delete RAW_PE[k]);
          RAW_PE['Fixture A']={'2025-01':20}; RAW['Fixture A']={'2025-01':100};
          renderYieldGapTab();renderCapeTab();
          delete RAW_PE['Fixture A']; delete RAW['Fixture A'];
          RAW_PE['Fixture B']={'2025-01':20}; RAW['Fixture B']={'2025-01':100};
          renderYieldGapTab();renderCapeTab();
          return ['yieldGapIndexSelect','capeIndexSelect'].map(id=>document.getElementById(id).value);
        }finally{Object.keys(RAW_PE).forEach(k=>delete RAW_PE[k]);Object.assign(RAW_PE,pe);delete RAW['Fixture B'];Object.assign(RAW,raw);renderYieldGapTab();renderCapeTab();}
      });
      assert.deepEqual(result,['Fixture B','Fixture B']);
    });
    await check('every index renders across all five valuation tabs and timeframe/window controls',async()=>{
      const result=await page.evaluate(()=>{
        const saved=[...selected]; let count=0;
        try {
          for(const key of Object.keys(ALL_INDICES_TRIMMED_EPS)){
            selected.clear();selected.add(key);
            renderRawPeTab();renderHarmonizedPeTab();renderDynamicBandsTab();
            for(const [id,render]of [['yieldGapIndexSelect',renderYieldGapTab],['capeIndexSelect',renderCapeTab]]){
              document.getElementById(id).value=key;render();
            }
            for(const c of [rawPeChartInstance,harmPeChartInstance,dynPeChartInstance,yieldGapChartInstance,capeChartInstance]) {
              if(!c)continue;
              for(const ds of c.data.datasets){
                if(ds.data.length!==c.data.labels.length)throw new Error(key+' length mismatch');
                if(ds.data.some(v=>v!==null&&!Number.isFinite(v)))throw new Error(key+' invalid chart value');
              }
            }
            count++;
          }
          selected.clear();selected.add('Nifty 50');
          for(const tf of ['1Y','3Y','5Y','10Y','MAX']){setRawPeTimeframe(tf);setHarmPeTimeframe(tf);setYieldGapTimeframe(tf);}
          for(const tf of ['3Y','5Y','10Y','MAX']){setDynPeTimeframe(tf);setCapeTimeframe(tf);}
          for(const scale of [false,true]){setRawPeScale(scale);setHarmPeScale(scale);}
          for(const w of [36,60])setCapeWindow(w);
          return count;
        }finally{selected.clear();saved.forEach(k=>selected.add(k));}
      });
      assert.equal(result,56);
    });
    await check('main and Growth chart empty selection clears prior data',async()=>{
      await page.evaluate(()=>{selected.clear();renderMain();renderPriceChart([]);});
      assert.equal(await page.evaluate(()=>priceChart),null);
      assert.equal(await page.evaluate(()=>simChart),null);
      await page.evaluate(()=>{selected.add('Nifty 50');weights['Nifty 50']=100;renderMain();});
    });
    await check('Excel export builds five worksheets and restores button using an offline writer fixture',async()=>{
      const result=await page.evaluate(()=>{
        const original=window.XLSX; let written=null;
        try {
          window.XLSX={utils:{book_new:()=>({sheets:[]}),aoa_to_sheet:rows=>rows,book_append_sheet:(wb,rows,name)=>wb.sheets.push({name,rows})},writeFile:(wb,name)=>{written={wb,name};}};
          exportXLSX();return written;
        }finally{window.XLSX=original;}
      });
      assert.equal(result.wb.sheets.length,5);
      assert.ok(result.wb.sheets.every(s=>s.rows.length>0));
      assert.match(result.name,/\.xlsx$/);
    });
    await check('search-filtered selection, all indices, and mixed commodity allocations render',async()=>{
      await page.evaluate(()=>{
        document.getElementById('idxSearch').value='';selectAllIndices();
        if(selected.size<50)throw new Error('Select-all missed indices');
        const total=[...selected].reduce((n,k)=>n+weights[k],0);
        if(Math.abs(total-100)>1e-6)throw new Error('Weights not normalized');
        deselectAllIndices();
        document.getElementById('idxSearch').value='Nifty 50';selectAllIndices();
        if(!selected.has('Nifty 50'))throw new Error('Filtered select failed');
        document.getElementById('idxSearch').value='';
        selected.clear();selected.add('Nifty 50');selected.add('Gold (INR)');weights['Nifty 50']=60;weights['Gold (INR)']=40;renderMain();
        toggleAlphaMode();toggleAlphaMode();
        selected.delete('Gold (INR)');weights['Nifty 50']=100;renderMain();
      });
    });
    await check('cashflow invalid inputs clear prior results instead of running negative/default capital',async()=>{
      await page.evaluate(()=>{switchTab(3);setCashflowMode('sip');document.getElementById('cfSipAmount').value='-100';runCashflowSim();});
      assert.equal(await page.evaluate(()=>cashflowChart),null);
      assert.match(await page.locator('#cfNoData').innerText(),/valid/);
      await page.evaluate(()=>{document.getElementById('cfSipAmount').value='10000';runCashflowSim();});
    });
    await check('cashflow actual-tenure badge matches selected dates, not an unused shortcut',async()=>{
      await page.evaluate(()=>{setCashflowView('single');document.getElementById('cfStartDate').value='2020-01';document.getElementById('cfEndDate').value='2021-07';document.getElementById('cfYears').value='10';runCashflowSim();});
      assert.equal(await page.locator('#cfYearsBadge').textContent(),'1.5 Yrs actual');
    });
    await check('keyboard collapse announces state and tabs announce active selection',async()=>{
      await page.evaluate(()=>switchTab(6));await page.waitForTimeout(100);
      assert.equal(await page.locator('#tabBtn6').getAttribute('aria-pressed'),'true');
      const button=page.locator('#tabContent6 .collapse-toggle-btn').first();
      await button.focus();await page.keyboard.press('Enter');
      assert.equal(await button.getAttribute('aria-expanded'),'false');
      await page.keyboard.press('Enter');assert.equal(await button.getAttribute('aria-expanded'),'true');
    });
    await check('390px layout: all tabs fit viewport with internal table scrolling',async()=>{
      await page.setViewportSize({width:390,height:844});
      fs.mkdirSync(path.join(root,'artifacts'),{recursive:true});
      for(let tab=0;tab<10;tab++) {
        await page.evaluate(tab=>switchTab(tab),tab);await page.waitForTimeout(100);
        const width=await page.evaluate(()=>({body:document.documentElement.scrollWidth,viewport:innerWidth,overflow:[...document.querySelectorAll('body *')].filter(e=>e.getBoundingClientRect().right>innerWidth+2 && getComputedStyle(e).position!=='fixed').slice(0,12).map(e=>({tag:e.tagName,id:e.id,cls:e.className,width:e.getBoundingClientRect().width}))}));
        assert.ok(width.body<=width.viewport+2,'Tab '+tab+' overflow '+JSON.stringify(width));
        if(tab===6) assert.ok(await page.locator('#dynPeHoverHud').evaluate(e=>e.scrollWidth<=e.clientWidth+2), 'Dynamic HUD clipping');
        if([0,1,3,6,9].includes(tab))await page.locator('#tabContent'+tab).screenshot({path:path.join(root,'artifacts',`review-mobile-tab${tab}.png`)});
      }
    });
    await check('no uncaught browser errors across review scenarios',async()=>assert.deepEqual(errors,[]));
    console.log(`Project browser review: ${passed} passed, ${failed} failed`);
    if(failed)process.exitCode=1;
  } finally {
    if (browser) await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => {console.error(error); process.exitCode = 1;});
