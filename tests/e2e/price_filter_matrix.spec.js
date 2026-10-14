const { test, expect } = require("@playwright/test");
const vm = require("node:vm");
const fs = require("node:fs");
const path = require("node:path");
const { matrix, stateFor } = require("./fixtures/price_filter_matrix");

/**
 * Compare price colors with independently calculated ranks and fallback anchors.
 * Empty samples must discard earlier ranks, and fewer than five listings use
 * page-specific anchors rather than percentiles from an unstable small sample.
 * @param {object} scale Production price-scale API under test.
 * @param {Array} features Listings returned by the filter engine.
 * @param {"lease"|"buy"} key Listing mode determining fallback prices.
 * @returns {void}
 */
function assertPriceColors(scale, features, key) {
  const prices = features.map((feature) => Number(feature.properties.list_price)).sort((a, b) => a - b);
  scale.update(prices);
  const bands = ["#0d0887", "#7e03a8", "#cc4778", "#f89540", "#f0f921"];
  const [low, high] = key === "lease" ? [1950, 4000] : [449000, 949000];
  for (const price of prices) {
    const fraction = prices.length >= 5
      ? prices.filter((candidate) => candidate < price).length / (prices.length - 1)
      : Math.max(0, Math.min(1, (price - low) / (high - low)));
    const color = bands[Math.min(4, Math.floor(fraction * 5))];
    if (scale.colorFor(price) !== color) throw new Error(`${key}: price ${price} should be ${color}`);
  }
  if (!prices.length && scale.colorFor(high) !== bands[4]) throw new Error(`${key}: empty sample retained old ranks`);
}

for (const key of ["lease", "buy"]) {
  test(`${key} every active/inactive filter group combination preserves price ranks`, () => {
    test.setTimeout(180_000);
    const context = vm.createContext({ window: { location: { pathname: key === "buy" ? "/buy" : "/" } } });
    for (const asset of ["clientside_callbacks/geojson/helpers.js", "clientside_callbacks/geojson/01_filter_categories.js",
      `clientside_callbacks/geojson/filters_${key}.js`, "price_scale.js"]) {
      vm.runInContext(fs.readFileSync(path.join(__dirname, "../../assets/js", asset), "utf8"), context);
    }
    const { base, groups, source } = matrix(key);
    const responsiveSource = fs.readFileSync(path.join(__dirname, "../../assets/js/clientside_callbacks/responsive_filters.js"), "utf8");
    const configuredGroups = vm.runInNewContext(`(${responsiveSource.match(/const GROUPS = Object.freeze\(([\s\S]*?)\);\n/)[1]})`);
    expect(groups.map(([name]) => name).sort()).toEqual(Object.keys(configuredGroups[key]).sort());
    const filter = context.window.larentals.filters[key === "lease" ? "filterLeaseState" : "filterBuyState"];
    const scale = context.window.larentals.priceScale;
    const bands = ["#0d0887", "#7e03a8", "#cc4778", "#f89540", "#f0f921"];
    for (let mask = 0; mask < 2 ** groups.length; mask++) {
      const filtered = filter(stateFor(base, groups, mask), source).features;
      const expected = source.features.filter((feature) => feature.excludedBy < 0 || !(mask & 2 ** feature.excludedBy));
      if (filtered.length !== expected.length || filtered.some((feature, i) => feature !== expected[i])) {
        throw new Error(`${key} filter membership mismatch for mask ${mask}`);
      }
      const prices = expected.map((feature) => feature.properties.list_price).sort((a, b) => a - b);
      scale.update(filtered.map((feature) => feature.properties.list_price));
      // Check individual listings and cluster medians against a separately
      // calculated percentile, rather than comparing the scale to itself.
      for (const price of [...prices, prices[Math.floor((prices.length - 1) / 2)]]) {
        const rank = prices.filter((candidate) => candidate < price).length / (prices.length - 1);
        const color = bands[Math.min(4, Math.floor(rank * 5))];
        if (scale.colorFor(price) !== color) throw new Error(`${key} price color mismatch for mask ${mask}, price ${price}`);
      }
    }
    console.log(`${key}: ${2 ** groups.length} exhaustive filter combinations passed`);
  });

  test(`${key} filter value pairs cover missing data, bounds, categories and small samples`, () => {
    const context = vm.createContext({ window: { location: { pathname: key === "buy" ? "/buy" : "/" } } });
    for (const asset of ["clientside_callbacks/geojson/helpers.js", "clientside_callbacks/geojson/01_filter_categories.js",
      `clientside_callbacks/geojson/filters_${key}.js`, "price_scale.js"]) {
      vm.runInContext(fs.readFileSync(path.join(__dirname, "../../assets/js", asset), "utf8"), context);
    }
    const { base, groups, source } = matrix(key);
    const filter = context.window.larentals.filters[key === "lease" ? "filterLeaseState" : "filterBuyState"];
    const scale = context.window.larentals.priceScale;
    const variants = groups.map(([name, patch]) => ({ name, patch }));
    for (const [name, selected] of Object.entries(base)) {
      if (name.endsWith("Missing")) {
        variants.push({ name, patch: { [name]: false } }, { name, patch: { [name]: true } });
      } else if (name.endsWith("Range") && Array.isArray(selected)) {
        const active = groups.find(([, patch]) => patch[name])?.[1][name];
        if (active) for (const range of [[active[0], null], [0, active[1]], [active[0], active[0]], [1e10, 1e10]]) {
          // Bedroom, bathroom, year and ISP controls have finite maxima.
          if (range[1] !== null || ["priceRange", "sqftRange", "ppsqftRange", "lotSizeRange", "hoaRange",
            "securityRange", "petDepositRange", "keyDepositRange", "otherDepositRange"].includes(name)) {
            variants.push({ name, patch: { [name]: range } });
          }
        }
      }
    }
    const categories = {
      requiredAmenities: [[], ["has_ac"], ["has_dishwasher"], ["has_ac", "has_dishwasher"]],
      subtypes: [[], ["group:single_family"], ["group:apartment"], ["unknown"], ["group:other"]],
      ...(key === "lease" ? {
        pets: ["any", "allowed", "possible", "unknown", "prohibited"],
        terms: [[], ["12 Months"], ["Month To Month"]], furnished: [[], ["Unfurnished"], ["Furnished"]],
        laundry: [[], ["In Unit"], ["Unknown"]], rentControl: ["any", "rso", "not_rso", "unknown"],
      } : { hoaFrequency: [[], ["Monthly"], ["Annually"], ["N/A"]] }),
    };
    for (const [name, choices] of Object.entries(categories)) {
      for (const choice of choices) variants.push({ name, patch: { [name]: choice } });
    }
    for (const patch of [{ dateStart: "2026-10-10", dateEnd: "2026-10-10" },
      { dateStart: "2027-01-01", dateEnd: "2027-01-02" },
      { zipBoundary: { zip_codes: ["90210"] } }, { zipBoundary: { zip_codes: ["90012", "90210"] } }]) {
      variants.push({ name: "date-or-location", patch });
    }
    // Missing fields must be exercised with both positions of their switches.
    const missing = structuredClone(source.features[0]);
    missing.properties.mls_number = "missing-fields";
    for (const field of ["sqft", "ppsqft", "parking_spaces", "year_built", "terms", "furnished",
      "security_deposit", "pet_deposit", "key_deposit", "other_deposit", "laundry_category",
      "listed_date", "best_dn", "best_up", "lot_size", "hoa_fee", "hoa_fee_frequency", "pet_policy"]) {
      missing.properties[field] = null;
    }
    source.features.push(missing);
    const singles = variants.map(({ patch }) => new Set(filter({ ...base, ...patch }, source).features));
    let pairs = 0;
    for (let i = 0; i < variants.length; i++) {
      for (let j = i + 1; j < variants.length; j++) {
        const first = variants[i], second = variants[j];
        if (Object.keys(first.patch).some((name) => name in second.patch)) continue;
        const actual = filter({ ...base, ...first.patch, ...second.patch }, source).features;
        const expected = source.features.filter((feature) => singles[i].has(feature) && singles[j].has(feature));
        if (actual.length !== expected.length || actual.some((feature, index) => feature !== expected[index])) {
          throw new Error(`${key}: value pair ${i}, ${j} did not match the intersection of its filters`);
        }
        assertPriceColors(scale, actual, key);
        pairs++;
      }
    }
    for (const count of [0, 1, 4, 5, 7]) {
      const features = source.features.slice(0, count);
      assertPriceColors(scale, features, key);
      assertPriceColors(scale, features.map((feature) => ({ ...feature,
        properties: { ...feature.properties, list_price: key === "lease" ? 3000 : 700000 } })), key);
    }
    assertPriceColors(scale, source.features, key);
    console.log(`${key}: ${variants.length} value variants, ${pairs} compatible value pairs and sample boundaries passed`);
  });

  test(`${key} rendered pins and clusters refresh for every filter group and pair`, async ({ page }) => {
    test.setTimeout(180_000);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(key === "buy" ? "/" : "/buy");
    await expect(page.locator(".results-row").first()).toBeVisible({ timeout: 30_000 });
    await page.locator(`a[href="${key === "buy" ? "/buy" : "/"}"]`).first().click();
    await expect(page.locator(`[data-results-panel="${key}"] .results-row`).first()).toBeVisible({ timeout: 30_000 });
    const { base, groups, source } = matrix(key);
    const masks = [0];
    for (let i = 0; i < groups.length; i++) {
      masks.push(2 ** i);
      for (let j = i + 1; j < groups.length; j++) masks.push(2 ** i + 2 ** j);
    }
    masks.push(2 ** groups.length - 1);
    for (const mask of masks) {
      const state = stateFor(base, groups, mask);
      const count = source.features.filter((feature) => feature.excludedBy < 0 || !(mask & 2 ** feature.excludedBy)).length;
      await page.evaluate(({ key, state, source }) => {
        const filter = window.larentals.filters[key === "lease" ? "filterLeaseState" : "filterBuyState"];
        window.larentals.priceScale.update([1e9, 2e9, 3e9, 4e9, 5e9]);
        window.larentals.priceScale.repaint();
        window.dash_clientside.set_props(`${key}_geojson`, { data: filter(state, source) });
      }, { key, state, source });
      await expect(page.locator(`[data-results-panel="${key}"] .results-row`), `${key} mask ${mask}`).toHaveCount(count);
      await expect.poll(() => page.evaluate(() => {
        const prices = [...document.querySelectorAll(".results-row__price")]
          .map((row) => Number(row.textContent.replace(/[^0-9]/g, ""))).sort((a, b) => a - b);
        const bands = ["#0d0887", "#7e03a8", "#cc4778", "#f89540", "#f0f921"];
        const markers = [...document.querySelectorAll(".price-marker[data-price], [data-cluster-price]")];
        return markers.length > 0 && markers.every((marker) => {
          const price = Number(marker.dataset.price || marker.dataset.clusterPrice);
          const rank = prices.filter((candidate) => candidate < price).length / (prices.length - 1);
          const color = bands[Math.min(4, Math.floor(rank * 5))];
          const layers = marker.matches(".price-marker") ? [marker] : [...marker.querySelectorAll(".cluster-price-core, .cluster-price-ring")];
          return layers.every((layer) => {
            const probe = document.createElement("span");
            probe.style.backgroundColor = color;
            return layer.dataset.priceColor === color && layer.style.backgroundColor === probe.style.backgroundColor;
          });
        });
      }), { message: `${key} rendered colors for mask ${mask}` }).toBe(true);
    }
    console.log(`${key}: ${masks.length} rendered filter combinations passed`);
    // Emptying and repopulating a map must reset stale ranks, including either
    // side of the five-listing threshold for the page-specific fallback scale.
    for (const count of [0, 1, 4, 5, 7]) {
      const features = source.features.slice(0, count);
      await page.evaluate(({ key, features }) => {
        window.dash_clientside.set_props(`${key}_geojson`, { data: { type: "FeatureCollection", features } });
      }, { key, features });
      await expect(page.locator(`[data-results-panel="${key}"] .results-row`)).toHaveCount(count);
      await expect.poll(() => page.evaluate(({ key, count }) => {
        const scale = window.larentals.priceScale;
        const price = key === "lease" ? 4000 : 949000;
        if (count === 0) return scale.fractionFor(price) === 1;
        const lowest = key === "lease" ? 1600 : 350000;
        return scale.fractionFor(lowest) === 0 && (count < 5 || scale.fractionFor(price) > 0.8);
      }, { key, count })).toBe(true);
    }
  });
}
