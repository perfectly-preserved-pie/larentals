(function () {
  "use strict";
  const root = window.larentals = window.larentals || {};
  const BINS = 44;

  /**
   * Count numeric listing fields using the slider's fixed display boundaries.
   * Overflow belongs in the last bar because the slider endpoint is open-ended;
   * missing fields contribute no bar rather than being interpreted as zero.
   * @param {Array<Object>} features Listings matching the other filters.
   * @param {string} field Numeric listing property.
   * @param {number} maximum Fixed slider display maximum, with a minimum of zero.
   * @returns {number[]} Counts ordered from low to high.
   */
  function counts(features, field, maximum) {
    const bins = Array(BINS).fill(0);
    if (!(maximum > 0)) return bins;
    for (const feature of features) {
      const raw = feature.properties[field];
      if (raw == null || String(raw).trim() === "") continue;
      const number = Number(raw);
      if (!Number.isFinite(number) || number < 0) continue;
      bins[Math.min(BINS - 1, Math.floor(number / maximum * BINS))]++;
    }
    return bins;
  }

  /**
   * Refresh each histogram from draft filters while leaving its own range open.
   * Reuse the listing engines so location, amenities, and missing-data rules stay
   * consistent with results. Quiet runs preserve the actual results' analytics
   * and debug report. Resolve the current namespace at call time because other
   * assets can replace it during startup; wait if engines are not registered yet.
   * Only bar children change, preserving drag masks and bins.
   * @param {"buy"|"lease"} page Listing mode whose controls are mounted.
   * @param {Object} state Current draft controls, including exact ranges.
   * @param {Object} source Unfiltered listing FeatureCollection.
   * @returns {void}
   */
  function update(page, state, source) {
    const engine = window.larentals?.filters?.[page === "buy" ? "filterBuyState" : "filterLeaseState"];
    if (typeof engine !== "function") return;
    const specs = [
      [page === "buy" ? "list_price_slider" : "rental_price_slider", "list_price", "priceRange", "priceUpperBound"],
      [`sqft_${page}`, "sqft", "sqftRange", "sqftUpperBound"],
    ];
    if (page === "buy") specs.push(["lot_size_slider", "lot_size", "lotSizeRange", "lotSizeUpperBound"]);
    for (const [id, field, range, upper] of specs) {
      const sample = engine({ ...state, [range]: [0, null] }, source, true);
      const bins = counts(sample.features, field, state[upper]);
      const peak = Math.max(...bins, 1);
      window.dash_clientside.set_props(`${id}_dist_bars`, {
        children: bins.map(count => ({
          namespace: "dash_html_components", type: "Div",
          props: { className: "dist__bar", style: {
            height: `${count ? Math.max(Math.sqrt(count / peak) * 100, 2).toFixed(1) : 0}%`,
          } },
        })),
      });
    }
  }

  root.distributions = { counts, update };
})();
