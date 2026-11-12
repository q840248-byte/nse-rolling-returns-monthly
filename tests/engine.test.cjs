const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const html = fs.readFileSync('rolling_returns.html', 'utf8');
function engine(names, globals = {}) {
  const context = vm.createContext({console, RAW: {}, ...globals});
  for (const name of names) {
    const source = html.match(new RegExp('(?:async )?function ' + name + '\\([^]*?\\n\\}'));
    assert.ok(source, 'Missing function: ' + name);
    vm.runInContext(source[0], context);
  }
  return context;
}
const core = ['addMonths', 'getMonthlyValue', 'computeRollingCAGR', 'computeRecoveryForKey'];
test('rolling CAGR uses calendar endpoints rather than count of observations', () => {
  const e = engine(core, {RAW: {sparse: {'2020-01': 100, '2021-01': 121}}});
  assert.equal(e.computeRollingCAGR('sparse', 1)['2021-01'], 21);
});
test('fractional-year horizons resolve to whole months', () => {
  const e = engine(core, {RAW: {short: {'2020-01': 100, '2020-08': 107}}});
  assert.equal(e.addMonths('2020-08', -(7 / 12) * 12), '2020-01');
  assert.ok(Number.isFinite(e.computeRollingCAGR('short', 7 / 12)['2020-08']));
});
test('invalid prices and horizons never produce infinite returns', () => {
  const e = engine(core, {RAW: {bad: {'2020-01': 100, '2021-01': Infinity}}});
  assert.equal(Object.keys(e.computeRollingCAGR('bad', 1)).length, 0);
  assert.equal(Object.keys(e.computeRollingCAGR('bad', 0)).length, 0);
});
test('recovery search can pass a missing observation without assuming no recovery', () => {
  const e = engine(core, {RAW: {sparse: {'2020-01': 100, '2021-01': 90, '2021-03': 120}}});
  assert.equal(e.computeRecoveryForKey('sparse', {'2021-01': -10}, 0, 1)[0].extraMonths, 2);
});
test('XIRR solves cashflows with reversed signs', () => {
  const e = engine(['calculateXIRR']);
  assert.ok(Math.abs(e.calculateXIRR([{amount: 100, t: 0}, {amount: -110, t: 1}]) - 10) < 1e-4);
});
test('XIRR handles large returns without a fabricated CAGR fallback', () => {
  const e = engine(['calculateXIRR']);
  assert.ok(Math.abs(e.calculateXIRR([{amount: -100, t: 0}, {amount: -100, t: 1}, {amount: 42000, t: 2}]) - 1900) < 1e-3);
});
module.exports = {engine};
const monthlyCore = ['addMonths', 'getMonthlyValue', 'getPortfolioMonthlyHistory', 'hasValidCashflowWindow'];
test('cashflow history preserves missing calendar months and allocated weights', () => {
  const e = engine(monthlyCore, {RAW: {
    A: {'2020-01': 100, '2020-02': 110, '2020-03': 121, '2020-04': 133.1},
    B: {'2020-01': 100, '2020-03': 100, '2020-04': 100},
  }});
  const h = e.getPortfolioMonthlyHistory(['A','B'], {A: 75, B: 25});
  assert.equal(h.dates.length, 4);
  assert.equal(h.monthlyReturns[0].r, null);
  assert.equal(h.monthlyReturns[1].r, null);
  assert.ok(Math.abs(h.monthlyReturns[2].r - .075) < 1e-10);
  assert.equal(e.hasValidCashflowWindow(h.monthlyReturns, 0, 3), false);
  assert.equal(e.hasValidCashflowWindow(h.monthlyReturns, 2, 1), true);
});
test('zero-weight assets neither shorten history nor silently become equal weights', () => {
  const e = engine(monthlyCore, {RAW: {A: {'2020-01': 100, '2020-02': 110}, B: {}}});
  assert.equal(e.getPortfolioMonthlyHistory(['A', 'B'], {A: 100, B: 0}).dates.length, 2);
  assert.equal(e.getPortfolioMonthlyHistory(['A'], {A: 0}).dates.length, 0);
});
function simulationGlobals(values = {}) {
  const elements = new Map();
  return {
    currentCashflowScale: 'linear', currentSwpType: 'fixed', cashflowChart: null,
    document: {getElementById(id) {
      if (!elements.has(id)) elements.set(id, {value: values[id] ?? '', checked: true, style: {}, innerHTML: '', textContent: ''});
      return elements.get(id);
    }},
    renderCashflowChart() {}, renderKpiCard: (label, value, sub) => label + ': ' + value + ' ' + sub + '\n',
    renderRollingSipInsights() {}, renderRollingSwpInsights() {},
  };
}
for (const mode of ['Sip', 'Swp', 'Lumpsum']) {
  test(`rolling ${mode} accepts exactly 12 returns for a one-year cohort`, () => {
    let chart;
    const e = engine(['addMonths','calculateXIRR','formatINR','formatBadgeINR','hasValidCashflowWindow','clearCashflowResults',`executeRolling${mode}Sim`], {
      ...simulationGlobals({cfYears: '1'}), renderCashflowChart: (...args) => {chart = args;},
    });
    const dates = Array.from({length: 13}, (_, i) => e.addMonths('2020-01', i));
    e[`executeRolling${mode}Sim`](['A'], dates, dates.slice(1).map(date => ({date, r: .01})));
    assert.equal(chart[0].length, 1);
    assert.equal(e.document.getElementById('cfNoData').style.display, 'none');
  });
}
test('rolling simulations with no complete windows clear stale output', () => {
  const e = engine(['hasValidCashflowWindow','clearCashflowResults','executeRollingLumpsumSim'], simulationGlobals({cfYears: '1'}));
  const returns = Array.from({length: 12}, (_, i) => ({date: '2020-01', r: i === 4 ? null : 0}));
  e.executeRollingLumpsumSim(['A'], Array(13).fill('2020-01'), returns);
  assert.match(e.document.getElementById('cfNoData').textContent, /No complete monthly windows/);
});
test('single SWP increases inflation only on the thirteenth withdrawal', () => {
  let chart;
  const e = engine(['formatINR','formatBadgeINR','executeSwpSim'], {
    ...simulationGlobals({cfSwpCorpus: '10000', cfSwpAmount: '100', cfSwpInflation: '10'}),
    renderCashflowChart: (...args) => {chart = args;},
  });
  e.executeSwpSim(['A'], ['2020-01'], Array.from({length: 13}, () => ({date: '2020-02', r: 0})));
  assert.equal(chart[1][0].data[12], 8800);
  assert.equal(chart[1][0].data[13], 8690);
});
test('STP residual liquid balance continues earning interest after month 12', () => {
  let chart;
  const e = engine(['formatINR','executeLumpsumSim'], {
    ...simulationGlobals({cfLumpAmount: '120000'}), renderCashflowChart: (...args) => {chart = args;},
  });
  e.executeLumpsumSim(['A'], ['2020-01'], Array.from({length: 24}, () => ({date: '2020-02', r: 0})));
  assert.ok(chart[1][1].data[24] > chart[1][1].data[12]);
});
test('XIRR rejects undefined/no-root inputs rather than fabricating a return', () => {
  const e = engine(['calculateXIRR']);
  assert.ok(Number.isNaN(e.calculateXIRR([{amount: -100, t: 0}, {amount: 100, t: 0}])));
  assert.ok(Number.isNaN(e.calculateXIRR([{amount: 100, t: 0}, {amount: 110, t: 1}])));
  assert.ok(Math.abs(e.calculateXIRR([{amount: -100, t: 0}, {amount: 1, t: 1}]) + 99) < 1e-5);
});
test('proxy URL builder preserves base query parameters and existing endpoints', () => {
  const e = engine(['buildStockProxyUrl'], {URL});
  let url = new URL(e.buildStockProxyUrl('https://proxy.example?token=value', 'M&M'));
  assert.equal(url.pathname, '/api/stock');
  assert.equal(url.searchParams.get('token'), 'value');
  assert.equal(url.searchParams.get('symbol'), 'M&M');
  url = new URL(e.buildStockProxyUrl('https://proxy.example/stock?symbol=OLD', 'TCS'));
  assert.equal(url.pathname, '/stock');
  assert.equal(url.searchParams.get('symbol'), 'TCS');
  assert.throws(() => e.buildStockProxyUrl('javascript:alert(1)', 'TCS'), /HTTP/);
});
test('SIP insight with only 119 returns reports no cohorts without crashing', () => {
  const e = engine(['hasValidCashflowWindow', 'renderRollingSipInsights'], {
    ...simulationGlobals(), weights: {A: 75, B: 25},
    getPortfolioMonthlyHistory: (keys, wts) => {
      assert.equal(wts.A, 75); assert.equal(wts.B, 25);
      return {dates: Array(120).fill('2020-01'), monthlyReturns: Array.from({length: 119}, () => ({r: .01}))};
    },
  });
  e.renderRollingSipInsights(['A','B']);
  assert.equal(e.document.getElementById('cfInsightsBox').innerHTML, '');
});
test('15-year retirement insight executes all 180 withdrawals, not 179', () => {
  const e = engine(['hasValidCashflowWindow', 'renderRollingSwpInsights'], {
    ...simulationGlobals(), weights: {A: 100},
    getPortfolioMonthlyHistory: () => ({dates: Array(181).fill('2020-01'), monthlyReturns: Array.from({length: 180}, () => ({r: 0}))}),
  });
  e.renderRollingSwpInsights(['A'], 1, 180, 0);
  assert.match(e.document.getElementById('cfInsightsBox').innerHTML, /0% Survival Rate/);
  assert.match(e.document.getElementById('cfInsightsBox').innerHTML, /0 out of 1/);
});
test('nominal smoothed P/E requires the full calendar window, with no warm-up substitution', () => {
  const e = engine(['addMonths', 'computeNominalSmoothedPe']);
  const dates = ['2024-01','2024-02','2024-03'];
  const price = {'2024-01': 200, '2024-02': 400, '2024-03': 600};
  const pe = Object.fromEntries(dates.map(d => [d, 20]));
  const result = e.computeNominalSmoothedPe(dates, price, pe, 3);
  assert.equal(result.values['2024-01'], null);
  assert.equal(result.values['2024-02'], null);
  assert.equal(result.smoothed['2024-03'], 20);
  assert.equal(result.values['2024-03'], 30);
  delete pe['2024-02'];
  assert.equal(e.computeNominalSmoothedPe(dates, price, pe, 3).values['2024-03'], null);
});
