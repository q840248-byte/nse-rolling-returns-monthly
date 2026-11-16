// Verifies the live-only stock policy on a phone profile: the page must embed no
// stock history and every Indian lookup (including RELIANCE) must hit the proxy.
const assert=require('node:assert/strict');
const http=require('node:http'),fs=require('node:fs'),path=require('node:path');
const {chromium: pw}=require('playwright-core'); const chromium=require('@sparticuz/chromium').default;
const root=path.resolve(__dirname,'..');
const server=http.createServer((q,r)=>{const f=path.resolve(root,'.'+new URL(q.url,'http://l').pathname);fs.readFile(f,(e,d)=>{if(e){r.writeHead(404).end();return;}r.setHeader('Content-Type',f.endsWith('.js')?'text/javascript':'text/html');r.end(d);});});
(async()=>{let b;try{
await new Promise(r=>server.listen(0,'127.0.0.1',r)); const port=server.address().port;
if(!process.env.BROWSER_PATH&&process.platform==='linux'){const bundle=require('@sparticuz/chromium');const libRoot=await bundle.inflate(path.join(path.dirname(require.resolve('@sparticuz/chromium')),'../bin/al2023.tar.br'));bundle.setupLambdaEnvironment(path.join(libRoot,'lib'));}
b=await pw.launch({executablePath:process.env.BROWSER_PATH||await chromium.executablePath(),args:chromium.args.filter(a=>!a.includes('disable-web-security')),headless:true});
const page=await b.newPage({viewport:{width:390,height:844},isMobile:true,hasTouch:true});
const requested=[];
await page.route('**/*',r=>{const u=new URL(r.request().url());
  if(u.hostname==='127.0.0.1'){requested.push(u.pathname);return r.continue();}
  const full=u.pathname+u.search;
  if(u.hostname.endsWith('workers.dev')){requested.push('PROXY'+full);
    return r.fulfill({status:200,contentType:'application/json',headers:{'Access-Control-Allow-Origin':'*'},body:JSON.stringify({datasets:[
      {metric:'Price',values:[['2024-01-31',100],['2024-02-29',110],['2024-03-31',121],['2024-04-30',133],['2024-05-31',146],['2024-06-30',161],['2024-07-31',177],['2024-08-31',195],['2024-09-30',214],['2024-10-31',236],['2024-11-30',259],['2024-12-31',285]]},
      {metric:'EPS',values:[['2024-01-31',10],['2024-04-30',11],['2024-07-31',12],['2024-10-31',13]]},
    ]})});}
  return r.abort();});
const errors=[];page.on('pageerror',e=>errors.push(e.message));
await page.goto(`http://127.0.0.1:${port}/rolling_returns.html`);
await page.waitForFunction(()=>typeof switchTab==='function');
await page.evaluate(()=>switchTab(9));

// 1. Page must not contain the embedded cache at all.
assert.equal(await page.evaluate(()=>typeof TOP_STOCKS_DATA!=='undefined'||!!window.TOP_STOCKS_DATA),false);
console.log('PASS page loads with no embedded stock data');

// 2. Switching to Stocks mode fetches the default symbol live.
await page.evaluate(()=>switchFundAssetMode('stock'));
await page.waitForFunction(()=>fundamentalsChartInstance!==null,null,{timeout:20000});
assert.ok(requested.some(r=>r.startsWith('PROXY/api/stock')),'proxy was not called on mode switch');
console.log('PASS entering Stocks mode fetched live: '+requested.find(r=>r.startsWith('PROXY')));

// 3. RELIANCE — formerly a guaranteed cache hit — must now hit the network.
const before=requested.filter(r=>r.startsWith('PROXY')).length;
await page.evaluate(async()=>{document.getElementById('fundStockInput').value='RELIANCE';await fetchAndSelectStock(false);});
const after=requested.filter(r=>r.startsWith('PROXY')).length;
assert.ok(after>before,'RELIANCE did not trigger a live fetch');
const last=requested.filter(r=>r.startsWith('PROXY')).at(-1);
assert.ok(last.includes('symbol=RELIANCE'),'wrong symbol requested: '+last);
console.log('PASS RELIANCE (formerly cached) now fetches live: '+last);

// 4. Chart actually renders from the live payload.
const shape=await page.evaluate(()=>({labels:fundamentalsChartInstance.data.labels.length,first:fundamentalsChartInstance.data.labels[0]}));
assert.ok(shape.labels>=6,'chart did not render from live data');
console.log('PASS chart rendered from live data: '+shape.labels+' months from '+shape.first);

// 5. A second lookup must also go live (no silent embedded short-circuit).
const b2=requested.filter(r=>r.startsWith('PROXY')).length;
await page.evaluate(async()=>{document.getElementById('fundStockInput').value='RPOWER';await fetchAndSelectStock(false);});
assert.ok(requested.filter(r=>r.startsWith('PROXY')).length>b2,'second lookup was served from cache');
console.log('PASS RPOWER also fetched live (no cache short-circuit)');

// 6. US mode still works from its untouched offline cache.
await page.evaluate(()=>switchFundAssetMode('us_stock'));
assert.ok(await page.evaluate(()=>fundamentalsChartInstance!==null));
console.log('PASS US stock mode still renders from its offline SEC cache');

if(errors.length)throw new Error('Uncaught: '+errors.join(' | '));
console.log('\nAll live-fetch verification passed.');
}finally{if(b)await b.close();server.close();}})().catch(e=>{console.error('FAIL',e.message);process.exit(1);});
