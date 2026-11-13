const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const html = fs.readFileSync('rolling_returns.html', 'utf8');
function engine(names, globals = {}) {
  const context = vm.createContext({console, ...globals});
  for (const name of names) {
    const source = html.match(new RegExp('function ' + name + '\\([^]*?\\n\\}'));
    assert.ok(source, name);
    vm.runInContext(source[0], context);
  }
  return context;
}
test('allocation redistribution preserves an already valid fully locked portfolio', () => {
  const e = engine(['redistributeWeights'], {selected: new Set(['A','B']), locked: new Set(['A','B']), weights: {A: 80, B: 20}});
  e.redistributeWeights();
  assert.equal(e.weights.A, 80);
  assert.equal(e.weights.B, 20);
});
test('all-locked selection changes normalize proportionally, never create negative allocations', () => {
  const keys = Array.from({length: 58}, (_, i) => 'A' + i);
  const e = engine(['redistributeWeights'], {selected: new Set(keys), locked: new Set(keys), weights: Object.fromEntries(keys.map(k => [k, 1]))});
  e.redistributeWeights();
  assert.ok(Object.values(e.weights).every(w => w >= 0));
  assert.ok(Math.abs(Object.values(e.weights).reduce((a,b) => a+b, 0) - 100) < 1e-8);
});
test('negative or invalid allocation entry cannot alter locked weights', () => {
  const e = engine(['applyWeightChange'], {selected: new Set(['A','B','C']), locked: new Set(['C']), weights: {A: 40, B: 40, C: 20}});
  e.applyWeightChange('A', -20);
  assert.equal(e.weights.A, 0);
  assert.equal(e.weights.B, 80);
  assert.equal(e.weights.C, 20);
  e.applyWeightChange('A', NaN);
  assert.equal(e.weights.C, 20);
  assert.equal(e.weights.B, 80);
});
test('drawdown durations count calendar months, not sparse observations', () => {
  const e = engine(['computeDrawdownAndRecovery']);
  const result = e.computeDrawdownAndRecovery([100, 80, 110], ['2020-01','2020-04','2021-01']);
  assert.equal(result.maxDrawdown, -20);
  assert.equal(result.recoveryMonths, 12);
});
test('portfolio drawdown ignores zero-weight unavailable assets and carries dates', () => {
  const e = engine(['computePortfolioNavSeries','getMonthlyValue'], {RAW: {A: {'2020-01':100,'2020-04':80,'2021-01':110}, B:{}}});
  const nav = e.computePortfolioNavSeries(['A','B'], {A:100,B:0});
  assert.ok(nav);
  assert.deepEqual(Array.from(nav), [100,80,110]);
  assert.deepEqual(Array.from(nav.dates), ['2020-01','2020-04','2021-01']);
});
test('five-year dynamic bands require 60 valid consecutive calendar months', () => {
  const e = engine(['addMonths','computeDynamicPeBands']);
  const dates = Array.from({length: 61}, (_, i) => e.addMonths('2020-01',i));
  const data = Object.fromEntries(dates.map(d => [d,20]));
  let result = e.computeDynamicPeBands(dates,data,60);
  assert.equal(result.mean[58], null);
  assert.equal(result.mean[59],20);
  assert.equal(result.z[59],null); // no measurable dispersion
  delete data[dates[5]];
  result = e.computeDynamicPeBands(dates,data,60);
  assert.equal(result.mean[60],null);
});
test('dynamic bands calculate population SD and current-value Z score correctly', () => {
  const e = engine(['addMonths','computeDynamicPeBands']);
  const dates = ['2020-01','2020-02','2020-03'];
  const result = e.computeDynamicPeBands(dates,{'2020-01':10,'2020-02':20,'2020-03':30},3);
  assert.equal(result.mean[2],20);
  assert.equal(result.upper[2],32.25);
  assert.equal(result.lower[2],7.75);
  assert.equal(result.z[2],1.22);
});
test('export failure restores its control and gives an actionable error', () => {
  const button = {textContent:'Export',disabled:false};
  const alerts=[];
  const e=engine(['exportXLSX'], {selected:new Set(['A']), document:{querySelector:()=>button}, window:{XLSX:{utils:{book_new(){throw new Error('fixture');}}}}, alert:msg=>alerts.push(msg)});
  assert.doesNotThrow(()=>e.exportXLSX());
  assert.equal(button.disabled,false);
  assert.match(alerts[0], /export/i);
});
test('stats decomposition uses exact common endpoints and supports fractional-year horizons', () => {
  const e=engine(['addMonths','getMonthlyValue','computeIndexDecomposition']);
  let d=e.computeIndexDecomposition({'2020-01':100,'2020-07':121},{'2020-01':10,'2020-07':11},.5);
  assert.equal(d.price,46.4);assert.equal(d.eps,21);assert.equal(d.multiple,21);
  d=e.computeIndexDecomposition({'2020-01':100,'2020-07':121},{'2020-01':10,'2020-06':11},.5);
  assert.equal(d.price,46.4);assert.equal(d.eps,null);
  d=e.computeIndexDecomposition({'2020-01':100,'2020-07':121},{},5);
  assert.equal(d.price,null);
});
test('cashflow date synchronization preserves a half-year instead of rounding to a year',()=>{
  const nodes={cfStartDate:{value:'2020-01'},cfEndDate:{value:'2020-07'},cfYears:{value:'1'}};
  const e=engine(['addMonths','syncCfYearsFromEnd','syncCfEndFromStart','syncCfEndFromYears'],{document:{getElementById:id=>nodes[id]}});
  e.syncCfYearsFromEnd(); assert.equal(Number(nodes.cfYears.value),.5);
  e.syncCfEndFromStart(); assert.equal(nodes.cfEndDate.value,'2020-07');
  e.syncCfEndFromYears(); assert.equal(nodes.cfEndDate.value,'2020-07');
});
