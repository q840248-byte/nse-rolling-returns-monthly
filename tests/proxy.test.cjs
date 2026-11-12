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
