const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const code = fs.readFileSync('stock-proxy-worker.js', 'utf8').replace('export default {', 'globalThis.worker = {');
function proxy(fetch) {
  const ctx = vm.createContext({fetch, Request, Response, URL, AbortSignal});
  vm.runInContext(code, ctx);
  return ctx;
}
test('preflight works and unsupported methods do not contact upstream', async () => {
  const p = proxy(() => {throw new Error('unexpected fetch');});
  assert.equal((await p.worker.fetch(new Request('https://proxy/api/stock', {method: 'OPTIONS'}))).status, 204);
  assert.equal((await p.worker.fetch(new Request('https://proxy/api/stock', {method: 'POST'}))).status, 405);
});
test('reject path/query injection and unbounded day requests before fetch', async () => {
  const p = proxy(() => {throw new Error('unexpected fetch');});
  for (const suffix of ['id=../search', 'id=1%3Fq=evil', 'id=0', 'id=1&days=Infinity', 'id=1&days=99999', 'id=1&days=0', 'id=1&days=2%26q=EPS']) {
    assert.equal((await p.worker.fetch(new Request('https://proxy/api/stock?' + suffix))).status, 400, suffix);
  }
});
test('consolidated data survives failed standalone response and receives timeouts', async () => {
  const p = proxy(async (url, options) => {
    assert.ok(options.signal);
    if (!url.includes('consolidated=true')) return new Response('rate limit', {status: 429});
    return Response.json({datasets: [{metric: 'EPS', values: [['2024-01-31', 10]]}, {metric: 'Price', values: [['2024-01-31', 100]]}]});
  });
  const response = await p.worker.fetch(new Request('https://proxy/api/stock?symbol=RELIANCE'));
  assert.equal(response.status, 200);
  assert.equal(response.headers.get('Access-Control-Allow-Origin'), '*');
  const data = await response.json();
  assert.equal(data.epsBasis, 'consolidated');
  assert.equal(data.datasets[0].values[0][1], 10);
});
test('malformed EPS points cannot pollute financial output', () => {
  const p = proxy();
  const values = p.sanitizeEpsValues([['2024-01-01', 10], ['2024-02-01', Infinity], ['2024-03-01', 'bad'], ['junk', 1], null]);
  assert.equal(JSON.stringify(values), JSON.stringify([['2024-01-01', 10]]));
});
test('both upstream failures return explicit 502 rather than empty success', async () => {
  const p = proxy(async () => new Response('unavailable', {status: 503}));
  assert.equal((await p.worker.fetch(new Request('https://proxy/api/stock?id=2726'))).status, 502);
});

test('proxy rejects impossible dates, boolean EPS, and malformed observation collections', () => {
  const p=proxy();
  const values=p.sanitizeEpsValues([['2024-02-30',10],['2024-01-01',true],['2024-01-01',[]],['2024-01-01',{}],['2024-02-29',0]]);
  assert.equal(JSON.stringify(values),JSON.stringify([['2024-02-29',0]]));
  assert.equal(JSON.stringify(p.sanitizeEpsValues({bad:true})), '[]');
});

test('search variants run concurrently instead of serially so slow mobile links time out less', async () => {
  const started = [];
  let inFlight = 0, maxConcurrentSearches = 0;
  const p = proxy(async url => {
    started.push(url);
    if (url.includes('/api/company/search')) {
      inFlight++;
      maxConcurrentSearches = Math.max(maxConcurrentSearches, inFlight);
      await new Promise(r => setTimeout(r, 20));
      inFlight--;
      // Both variants are in flight together; only the spaced form matches.
      if (url.includes('q=SOMEX%20ABC')) return Response.json([{id: 4242, name: 'Somex ABC', url: '/company/SOMEX-ABC/'}]);
      return Response.json([{id: 1, name: 'Unrelated', url: '/company/OTHER/'}]);
    }
    return Response.json({datasets: [{metric: 'EPS', values: [['2024-01-31', 10]]}, {metric: 'Price', values: [['2024-01-31', 100]]}]});
  });
  const response = await p.worker.fetch(new Request('https://proxy/api/stock?symbol=SOMEX-ABC'));
  assert.equal(response.status, 200);
  assert.ok(started.some(u => u.includes('q=SOMEX-ABC')), 'hyphenated variant queried');
  assert.ok(started.some(u => u.includes('q=SOMEX%20ABC')), 'spaced variant queried');
  assert.equal(maxConcurrentSearches, 2, 'search variants must overlap, not queue up');
  const data = await response.json();
  assert.equal(data.resolvedId, 4242);
});

test('a failed search variant does not break lookup when another variant matches', async () => {
  const p = proxy(async url => {
    if (url.includes('q=SOMEX%20ABC')) throw new Error('network down');
    return Response.json([{id: 4242, name: 'Somex ABC', url: '/company/SOMEX-ABC/'}]);
  });
  const response = await p.worker.fetch(new Request('https://proxy/api/stock?symbol=SOMEX-ABC'));
  assert.equal(response.status, 200);
});

test('successful responses are cacheable, error responses are not', async () => {
  const p = proxy(async url => {
    if (url.includes('/chart/')) return Response.json({datasets: [{metric: 'EPS', values: [['2024-01-31', 10]]}, {metric: 'Price', values: [['2024-01-31', 100]]}]});
    return Response.json([{id: 2726, name: 'Reliance', url: '/company/RELIANCE/'}]);
  });
  const ok = await p.worker.fetch(new Request('https://proxy/api/stock?symbol=RELIANCE'));
  assert.match(ok.headers.get('Cache-Control') || '', /max-age=600/);
  const notFound = await proxy(async () => new Response('x', {status: 503}))
    .worker.fetch(new Request('https://proxy/api/stock?id=2726'));
  assert.equal(notFound.status, 502);
  assert.equal(notFound.headers.get('Cache-Control'), null);
});
