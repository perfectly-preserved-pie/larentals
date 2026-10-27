const { test, expect } = require("@playwright/test");
const { matrix } = require("./fixtures/price_filter_matrix");

/**
 * Wait for the production map and its CDN Turf bundle before checking geometry.
 * This also catches a stale CSP entry that would leave the library unavailable.
 * @param {import("@playwright/test").Page} page Browser page running the app.
 * @param {string} path Listing page to exercise.
 * @returns {Promise<void>}
 */
async function openMap(page, path = "/") {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto(path, { waitUntil: "networkidle" });
  await page.waitForFunction(() => window.larentals?.map && typeof window.turf?.convex === "function");
  await expect(page.locator('script[src*="@turf/turf@"]')).toHaveAttribute(
    "src", "https://cdn.jsdelivr.net/npm/@turf/turf@7.4.0/turf.min.js",
  );
}

for (const market of ["lease", "buy"]) {
  test(`${market} Turf ZIP filtering handles boundaries, holes, islands and ZIP fallbacks`, async ({ page }) => {
    await openMap(page, market === "lease" ? "/" : "/buy");
    const { base, source } = matrix(market);
    const selections = await page.evaluate(({ market, base, template }) => {
      const outer = [[-119, 33], [-117, 33], [-117, 35], [-119, 35], [-119, 33]];
      const hole = [[-118.6, 33.6], [-118.4, 33.6], [-118.4, 33.8], [-118.6, 33.8], [-118.6, 33.6]];
      const island = [[-116, 33], [-115, 33], [-115, 34], [-116, 34], [-116, 33]];
      const polygon = { type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [outer, hole] } };
      const multi = { ...polygon, geometry: { type: "MultiPolygon", coordinates: [[outer, hole], [island]] } };
      const features = [
        ["inside", [-118, 34]], ["outer-edge", [-119, 34]], ["outer-vertex", [-119, 33]],
        ["swapped", [34, -118]], ["hole", [-118.5, 33.7]], ["hole-edge", [-118.6, 33.7]],
        ["island", [-115.5, 33.5]], ["outside", [-120, 34]],
        ["missing", null], ["empty", []], ["invalid", ["bad", 34]],
      ].map(([id, coordinates]) => ({
        ...template,
        geometry: coordinates === null ? null : { type: "Point", coordinates },
        properties: { ...template.properties, mls_number: id, zip_code: "90012" },
      }));
      features.push({ ...features[7], properties: { ...template.properties, mls_number: "zip-fallback", zip_code: "90210-1234" } });
      const filter = window.larentals.filters[market === "lease" ? "filterLeaseState" : "filterBuyState"];
      const ids = (zipBoundary) => filter({ ...base, zipBoundary }, { type: "FeatureCollection", features })
        .features.map((feature) => feature.properties.mls_number);
      return {
        polygon: ids({ features: [polygon] }),
        multi: ids({ features: [multi] }),
        multiple: ids({ features: [polygon, { ...polygon, geometry: { type: "Polygon", coordinates: [island] } }] }),
        fallback: ids({ features: [polygon], zip_codes: ["90210"] }),
        zipOnly: ids({ zip_codes: ["90210"] }),
      };
    }, { market, base, template: source.features[0] });
    const contained = ["inside", "outer-edge", "outer-vertex", "swapped", "hole-edge"];
    expect(selections).toEqual({
      polygon: contained,
      multi: [...contained, "island"],
      multiple: [...contained, "island"],
      fallback: [...contained, "zip-fallback"],
      zipOnly: ["zip-fallback"],
    });
  });

  test(`${market} listing cluster hover draws and removes a real Turf hull`, async ({ page }) => {
    await openMap(page, market === "lease" ? "/" : "/buy");
    const cluster = page.locator("[data-cluster-count]").first();
    await expect(cluster).toBeVisible();
    await cluster.hover();
    await expect.poll(() => page.evaluate(() => {
      const hull = window.larentals.currentConvexHull;
      return Boolean(hull && window.larentals.map.hasLayer(hull) &&
        hull.toGeoJSON().features[0]?.geometry.type === "Polygon");
    })).toBe(true);
    // Leave the map entirely so its result overlay cannot retain marker hover.
    await page.getByRole("link", { name: "MCP setup instructions" }).hover();
    await expect.poll(() => page.evaluate(() => Boolean(window.larentals.currentConvexHull))).toBe(false);
  });
}

for (const renderer of ["listing", "drawSchoolCluster", "drawOilCluster", "drawAlprCameraCluster"]) {
  test(`Turf ${renderer} hull handles duplicates, missing points and degenerate clusters`, async ({ page }) => {
    await openMap(page);
    const cases = await page.evaluate((renderer) => {
      const map = window.larentals.map;
      const draw = renderer === "listing" ? window.dashExtensions.default.function0
        : window.myNamespace.mySubNamespace[renderer];
      const triangle = [[-118.5, 34], [-118, 34], [-118, 34.5]];
      const inputs = [
        triangle,
        [...triangle, triangle[0], [-118.1, 34.1]],
        [...triangle, null, []],
        [], [triangle[0]], triangle.slice(0, 2),
        [triangle[0], triangle[0], triangle[0]],
        [[-118.5, 34], [-118.25, 34], [-118, 34]],
      ];
      return inputs.map((coordinates) => {
        const leaves = coordinates.map((point) => ({
          type: "Feature", properties: { list_price: 3000 },
          geometry: point === null ? null : { type: "Point", coordinates: point },
        }));
        const feature = { type: "Feature", geometry: { type: "Point", coordinates: [-118, 34] },
          properties: { cluster_id: 0, point_count: leaves.length, point_count_abbreviated: leaves.length } };
        const context = { map };
        const marker = draw(feature, L.latLng(34, -118), { getLeaves: () => leaves }, context);
        marker.fire("mouseover");
        const hull = context.currentPolygon;
        const ring = hull?.toGeoJSON().features[0].geometry.coordinates[0];
        const outcome = {
          shown: Boolean(hull && map.hasLayer(hull)),
          vertices: ring ? [...new Set(ring.map((point) => JSON.stringify(point)))].sort() : [],
          closed: ring ? JSON.stringify(ring[0]) === JSON.stringify(ring.at(-1)) : false,
        };
        marker.fire("mouseout");
        outcome.removed = context.currentPolygon === null && (!hull || !map.hasLayer(hull));
        // Overlay renderers also expose hulls to keyboard users.
        if (renderer !== "listing") {
          marker.fire("focus");
          const focusedHull = context.currentPolygon;
          outcome.focusShown = Boolean(focusedHull && map.hasLayer(focusedHull));
          marker.fire("blur");
          outcome.blurRemoved = context.currentPolygon === null && (!focusedHull || !map.hasLayer(focusedHull));
        }
        marker.fire("mouseover");
        const removedHull = context.currentPolygon;
        marker.fire("remove");
        outcome.markerRemoved = context.currentPolygon === null && (!removedHull || !map.hasLayer(removedHull));
        return outcome;
      });
    }, renderer);
    const vertices = [[-118.5, 34], [-118, 34], [-118, 34.5]].map((point) => JSON.stringify(point)).sort();
    cases.forEach((outcome, index) => {
      const hasHull = index < 3;
      expect(outcome, `cluster case ${index}`).toEqual({
        shown: hasHull, vertices: hasHull ? vertices : [], closed: hasHull,
        removed: true, markerRemoved: true,
        ...(renderer === "listing" ? {} : { focusShown: hasHull, blurRemoved: true }),
      });
    });
  });
}
