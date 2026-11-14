const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const html = fs.readFileSync('rolling_returns.html', 'utf8');

// Extracts top-level function bodies so the mobile stock-fetch hardening can be
// unit tested without a browser.
const FUND_HELPERS = [
  'fundGetProxyUrl', 'fundSetProxyUrl', 'fundTimeoutSignal', 'fundIsTransientError',
  'fundDescribeFetchError', 'fundStockFetchOptions', 'fetchStockProxyJson', 'buildStockProxyUrl',
];

function fundamentals(globals = {}) {
  const context = vm.createContext({
    FUND_DEFAULT_PROXY_URL: 'https://proxy.example.dev',
    FUND_PROXY_TIMEOUT_MS: 75000,
    setTimeout, clearTimeout, Promise, URL, console,
    ...globals,
  });
  for (const name of FUND_HELPERS) {
    const source = html.match(new RegExp('(?:async )?function ' + name + '\\([^]*?\\n\\}'));
    assert.ok(source, 'Missing function: ' + name);
    vm.runInContext(source[0], context);
  }
  // Async functions declared in a vm context are not attached to the context
  // object's own properties, so expose them explicitly for awaiting.
  for (const name of FUND_HELPERS) {
    const source = html.match(new RegExp('(?:async )?function ' + name + '\\([^]*?\\n\\}'));
    context[name] = vm.runInContext('(' + source[0] + ')', context);
  }
  return context;
}

function throwingStorage() {
  const fail = () => {throw new Error('SecurityError: localStorage is not available');};
  return {getItem: fail, setItem: fail, removeItem: fail};
}

test('private-mode localStorage cannot abort a stock lookup', () => {
  const ctx = fundamentals({localStorage: throwingStorage()});
  assert.equal(ctx.fundGetProxyUrl(), 'https://proxy.example.dev');
  // Saving settings in an in-app browser must stay a no-op, not throw.
  assert.doesNotThrow(() => ctx.fundSetProxyUrl('https://other.dev'));
  assert.doesNotThrow(() => ctx.fundSetProxyUrl(''));
});

test('a saved proxy URL still wins when localStorage works', () => {
  const store = {'fund_stock_proxy_url': '  https://saved.dev  '};
  const ctx = fundamentals({localStorage: {getItem: k => store[k] ?? null, setItem() {}, removeItem() {}}});
  assert.equal(ctx.fundGetProxyUrl(), 'https://saved.dev');
});

test('timeout signal degrades gracefully when AbortSignal.timeout is missing', () => {
  function FakeController() {
    this.signal = {aborted: false, abortedBy: 'controller'};
    this.abort = () => {this.signal.aborted = true;};
  }
  const timers = [];
  const ctx = fundamentals({
    AbortSignal: {}, // No .timeout, as on older Android WebViews / iOS Safari.
    AbortController: FakeController,
    setTimeout: fn => {timers.push(fn); return timers.length;},
  });
  const signal = ctx.fundTimeoutSignal(1000);
  assert.equal(signal.abortedBy, 'controller');
  assert.equal(timers.length, 1);
  timers[0]();
  assert.equal(signal.aborted, true);
});

test('timeout helper prefers the native AbortSignal.timeout when present', () => {
  const native = {abortedBy: 'native'};
  const ctx = fundamentals({AbortSignal: {timeout: ms => {native.ms = ms; return native;}}});
  assert.equal(ctx.fundTimeoutSignal(1234), native);
  assert.equal(native.ms, 1234);
});

test('only genuinely transient failures are retried', () => {
  const ctx = fundamentals();
  assert.equal(ctx.fundIsTransientError({name: 'TypeError', message: 'Failed to fetch'}), true);
  assert.equal(ctx.fundIsTransientError({name: 'AbortError'}), true);
  assert.equal(ctx.fundIsTransientError({name: 'TimeoutError'}), true);
  assert.equal(ctx.fundIsTransientError({status: 502}), true);
  assert.equal(ctx.fundIsTransientError({status: 429}), true);
  // A missing symbol must not be retried: it will never start succeeding.
  assert.equal(ctx.fundIsTransientError({status: 404}), false);
  assert.equal(ctx.fundIsTransientError({name: 'Error', message: 'not found on Screener'}), false);
});

test('a flaky first request is retried once and then succeeds', async () => {
  const calls = [];
  const ctx = fundamentals({
    fetch: async url => {
      calls.push(url);
      if (calls.length === 1) throw new TypeError('Failed to fetch');
      return {ok: true, status: 200, json: async () => ({datasets: []})};
    },
  });
  const data = await ctx.fetchStockProxyJson('https://proxy.example.dev/api/stock?symbol=X', true);
  assert.equal(calls.length, 2);
  assert.deepEqual(data, {datasets: []});
});

test('cached first lookups allow revalidation while explicit refreshes bypass the cache', () => {
  const ctx = fundamentals();
  assert.equal(ctx.fundStockFetchOptions(true).cache, 'default');
  assert.equal(ctx.fundStockFetchOptions(false).cache, 'no-store');
  assert.equal(ctx.fundStockFetchOptions(false).headers.Accept, 'application/json');
});

test('HTTP failures surface the status and are not retried on 4xx', async () => {
  let calls = 0;
  const ctx = fundamentals({
    fetch: async () => {calls++; return {ok: false, status: 404, json: async () => ({})};},
  });
  await assert.rejects(
    ctx.fetchStockProxyJson('https://proxy.example.dev/api/stock?symbol=NOPE'),
    err => err.status === 404 && /HTTP 404/.test(err.message),
  );
  assert.equal(calls, 1);
});

test('persistent network failure eventually rejects instead of hanging', async () => {
  let calls = 0;
  const ctx = fundamentals({fetch: async () => {calls++; throw new TypeError('Failed to fetch');}});
  await assert.rejects(ctx.fetchStockProxyJson('https://proxy.example.dev/api/stock?symbol=X'));
  assert.equal(calls, 2);
});

test('mobile "Failed to fetch" explains the likely causes and next step', () => {
  const ctx = fundamentals();
  const message = ctx.fundDescribeFetchError(new TypeError('Failed to fetch'), 'ABCDEF');
  assert.match(message, /Could not reach the stock proxy for ABCDEF/);
  assert.match(message, /private DNS|ad-blocker/);
  assert.match(message, /Test Connection/);
  // Provider-side messages must pass through unchanged, not be rewritten.
  assert.equal(ctx.fundDescribeFetchError(new Error('Indian symbol "X" not found on Screener'), 'X'),
    'Indian symbol "X" not found on Screener');
});

test('aborted requests report a retryable timeout rather than a bare AbortError', () => {
  const ctx = fundamentals();
  const err = new Error('signal timed out');
  err.name = 'TimeoutError';
  const message = ctx.fundDescribeFetchError(err, 'ABCDEF');
  assert.match(message, /timed out after 75s for ABCDEF/);
  assert.match(message, /tap Fetch/);
});

test('stock proxy URLs stay well formed for the configured base', () => {
  const ctx = fundamentals();
  assert.equal(ctx.buildStockProxyUrl('https://proxy.example.dev', 'RELIANCE'),
    'https://proxy.example.dev/api/stock?symbol=RELIANCE');
  assert.equal(ctx.buildStockProxyUrl('https://proxy.example.dev/api', 'TCS'),
    'https://proxy.example.dev/api/stock?symbol=TCS');
});
