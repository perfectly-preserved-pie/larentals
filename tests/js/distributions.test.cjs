const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const { matrix, stateFor } = require('../e2e/fixtures/price_filter_matrix');

for (const page of ['buy', 'lease']) {
  test(`${page} histogram samples honor other filters and omit their own range`, () => {
    const updates = {};
    const context = vm.createContext({ window: { location: { pathname: '/' } } });
    vm.runInContext(fs.readFileSync(path.join(__dirname, '../../assets/js/distributions.js'), 'utf8'), context);
    // Startup may invoke the updater before engines register.
    assert.doesNotThrow(() => context.window.larentals.distributions.update(page, {}, {}));
    // The LAHD asset replaces the namespace before nested filter assets load.
    vm.runInContext(fs.readFileSync(path.join(__dirname, '../../assets/js/lahd_records.js'), 'utf8'), context);
    for (const asset of ['clientside_callbacks/geojson/helpers.js',
      'clientside_callbacks/geojson/01_filter_categories.js',
      `clientside_callbacks/geojson/filters_${page}.js`]) {
      vm.runInContext(fs.readFileSync(path.join(__dirname, '../../assets/js', asset), 'utf8'), context);
    }
    const root = context.window.larentals;
    root.analytics = new Proxy({}, { get() { return () => { throw Error('histogram emitted analytics'); }; } });
    root.filterDevtools = { createRunCollector() { throw Error('histogram replaced debug report'); } };
    context.window.dash_clientside.set_props = (id, props) => { updates[id] = props; };
    const { base, groups, source } = matrix(page);
    Object.assign(base, { priceUpperBound: page === 'buy' ? 1000000 : 4000,
      sqftUpperBound: 2000, lotSizeUpperBound: 10000 });
    const specs = [
      [page === 'buy' ? 'list_price_slider' : 'rental_price_slider', 'price', 'list_price', base.priceUpperBound],
      [`sqft_${page}`, 'sqft', 'sqft', base.sqftUpperBound],
    ];
    if (page === 'buy') specs.push(['lot_size_slider', 'lotSize', 'lot_size', base.lotSizeUpperBound]);
    // Activate each group alone, then every group together. The fixture records
    // independent exclusion reasons, so expected samples do not reuse the engine.
    for (const mask of [0, ...groups.map((_, i) => 2 ** i), 2 ** groups.length - 1]) {
      const state = stateFor(base, groups, mask);
      const before = JSON.stringify(state);
      root.distributions.update(page, state, source);
      assert.equal(JSON.stringify(state), before);
      for (const [id, own, field, maximum] of specs) {
        const ownIndex = groups.findIndex(([name]) => name === own);
        const expected = Array(44).fill(0);
        for (const feature of source.features) {
          if (feature.excludedBy >= 0 && feature.excludedBy !== ownIndex && (mask & 2 ** feature.excludedBy)) continue;
          expected[Math.min(43, Math.floor(feature.properties[field] / maximum * 44))]++;
        }
        const peak = Math.max(...expected, 1);
        assert.deepEqual(Array.from(updates[`${id}_dist_bars`].children, bar => bar.props.style.height),
          expected.map(n => `${n ? Math.max(Math.sqrt(n / peak) * 100, 2).toFixed(1) : 0}%`));
      }
    }
    root.distributions.update(page, { ...base, bedroomsRange: [99, 100] }, source);
    assert.ok(Object.values(updates).every(props => props.children.every(bar => bar.props.style.height === '0%')));
    const bins = root.distributions.counts([null, '', 'bad', -1, 0, 50, 100, 150].map(sqft => ({ properties: { sqft } })), 'sqft', 100);
    assert.equal(bins.reduce((a, b) => a + b, 0), 4);
    assert.equal(bins[43], 2);
  });
}
