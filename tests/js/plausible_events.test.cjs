const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

const source = fs.readFileSync(path.join(__dirname,
  '../../assets/js/clientside_callbacks/plausible_events.js'), 'utf8');

for (const plausibleAvailable of [false, true]) {
  for (const rybbitAvailable of [false, true]) {
    test(`dispatch with Plausible=${plausibleAvailable}, Rybbit=${rybbitAvailable}`, () => {
      const plausibleCalls = [];
      const rybbitCalls = [];
      let callbackCalls = 0;
      const callback = () => { callbackCalls += 1; };
      const window = { location: { pathname: '/buy' } };
      if (plausibleAvailable) {
        window.plausible = (name, payload) => {
          plausibleCalls.push({ name, payload });
          payload.callback?.();
        };
      }
      if (rybbitAvailable) {
        window.rybbit = { event(name, props) {
          assert.equal(this, window.rybbit);
          rybbitCalls.push({ name, props });
        } };
      }
      vm.runInNewContext(source, { window });
      const analytics = window.larentals.analytics;
      const props = { category: 'bedrooms' };
      const options = { callback, interactive: false, props: { ignored: true } };
      analytics.trackEvent('Filter Changed', props, options);
      analytics.trackEvent('No Properties');
      analytics.trackReportListingSubmitted('Wrong Details');

      assert.equal(plausibleCalls.length, plausibleAvailable ? 3 : 0);
      assert.equal(rybbitCalls.length, rybbitAvailable ? 3 : 0);
      assert.equal(callbackCalls, plausibleAvailable ? 1 : 0);
      assert.deepEqual(options.props, { ignored: true });
      if (plausibleAvailable) {
        assert.equal(plausibleCalls[0].payload.callback, callback);
        assert.equal(plausibleCalls[0].payload.interactive, false);
        assert.equal(plausibleCalls[0].payload.props, props);
      }
      for (const calls of [plausibleCalls, rybbitCalls]) {
        if (!calls.length) continue;
        // JSON comparison permits objects created inside the VM context.
        assert.deepEqual(JSON.parse(JSON.stringify(calls.map(call => ({
          name: call.name, props: call.payload ? call.payload.props : call.props,
        })))), [
          { name: 'Filter Changed', props: { category: 'bedrooms' } },
          { name: 'No Properties', props: {} },
          { name: 'Report Listing Submitted', props: { page: 'buy', reason: 'Wrong Details' } },
        ]);
      }
    });
  }
}

test('ignore SDK globals without callable tracking methods', () => {
  const window = { plausible: {}, rybbit: { event: true } };
  vm.runInNewContext(source, { window });
  assert.doesNotThrow(() => window.larentals.analytics.trackEvent('Listing Opened'));
});
