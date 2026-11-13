const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const html = fs.readFileSync('rolling_returns.html', 'utf8');
const ctx = vm.createContext({});
for (const name of ['normalizeFundamentalsStock', 'escapeFundText', 'parseFundObservation', 'formatFundLegendValue']) {
  const source = html.match(new RegExp('function ' + name + '\\([^]*?\\n\\}'));
  assert.ok(source, name); vm.runInContext(source[0], ctx);
}
test('stock normalization derives internally consistent P/E and preserves zero/loss EPS', () => {
  const out = ctx.normalizeFundamentalsStock({price: {'2024-01': 100, '2024-02': 110, '2024-03': 120}, eps: {'2024-01': 10, '2024-02': 0, '2024-03': -2}, pe: {'2024-01': 999, '2024-02': 50}});
  assert.equal(out.pe['2024-01'], 10); assert.equal(out.pe['2024-02'], null); assert.equal(out.pe['2024-03'], null);
  assert.equal(out.eps['2024-02'], 0); assert.equal(out.eps['2024-03'], -2);
});
test('stock normalization sorts valid months and rejects invalid/non-finite prices', () => {
  const out = ctx.normalizeFundamentalsStock({price: {'2024-02': 100, '2024-01': 110, '2024-13': 120, '2024-03': Infinity, junk: 100}, eps: {'2024-02': NaN}});
  assert.equal(JSON.stringify(out.dates), '["2024-01","2024-02"]');
  assert.equal(out.eps['2024-02'], null); assert.equal(out.pe['2024-02'], null);
});
test('source observations require real dates and complete finite numeric values', () => {
  for (const point of [null, ['2024-02-30', 10], ['2023-02-29', 10], ['2024-01-01', '12bad'], ['2024-01-01', Infinity], ['2024-01-01', ''], ['2024-01-01', null], ['2024-01-01', false]]) {
    assert.equal(ctx.parseFundObservation(point), null, JSON.stringify(point));
  }
  assert.equal(ctx.parseFundObservation(['2024-02-29', '-1.25']).value, -1.25);
  assert.equal(ctx.parseFundObservation(['2024-02-29T12:00:00Z', 0]).date, '2024-02-29');
});
test('dynamic fundamentals identifiers are escaped before HUD markup', () => {
  assert.equal(ctx.escapeFundText('<img src="x" onerror=\'bad\'>&'), '&lt;img src=&quot;x&quot; onerror=&#39;bad&#39;&gt;&amp;');
});

test('legend formatter uses actual currency plus rebased chart value and preserves missing/zero/loss values', () => {
  assert.equal(ctx.formatFundLegendValue(1226.9,126,'₹'),'₹1226.9 (126)');
  assert.equal(ctx.formatFundLegendValue(12.26,126.43,'$'),'$12.3 (126.4)');
  assert.equal(ctx.formatFundLegendValue(0,0,'₹'),'₹0.0 (0)');
  assert.equal(ctx.formatFundLegendValue(-8,-80,'₹'),'₹-8.0 (-80)');
  assert.equal(ctx.formatFundLegendValue(null,null,'₹'),'— (—)');
  assert.equal(ctx.formatFundLegendValue(10,null,'₹'),'₹10.0 (—)');
  assert.equal(ctx.formatFundLegendValue(Infinity,NaN,'₹'),'— (—)');
});
