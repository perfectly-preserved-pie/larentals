const { expect, test } = require("@playwright/test");

for (const { path, market, layout, priceId, category } of [
  {
    path: "/", market: "lease", layout: "bottom-sheet",
    priceId: "rental_price_maximum_input", category: "monthly_rent",
  },
  {
    path: "/buy", market: "buy", layout: "sidebar",
    priceId: "list_price_maximum_input", category: "list_price",
  },
]) {
  test(`${market} tracks price edits and commits on the ${layout}`, async ({ page }) => {
    const mobile = layout === "bottom-sheet";
    await page.setViewportSize(mobile ? { width: 390, height: 844 } : { width: 1360, height: 900 });
    await page.route("**/analytics/script.js?*", (route) => route.fulfill({
      contentType: "application/javascript",
      body: "window.analyticsEvents = []; window.rybbit = { event: (...args) => window.analyticsEvents.push(args) };",
    }));
    await page.goto(path, { waitUntil: "domcontentloaded" });
    await page.waitForFunction((key) =>
      Number.isFinite(window.larentals?.responsiveFilters?.appliedCounts?.[key]), market);
    const events = (name) => page.evaluate((eventName) =>
      window.analyticsEvents.filter(([name]) => name === eventName).map(([, properties]) => properties), name);

    if (mobile) {
      expect(await events("Filter Panel Viewed")).toEqual([]);
      await page.locator(`#${market}-filter-open-button`).click();
    }
    await expect.poll(() => events("Filter Panel Viewed")).toEqual([
      { page: market, layout, schema_version: 2 },
    ]);
    expect(await events("Filter Changed")).toEqual([]);
    expect(await events("Filter Section Opened")).toEqual([]);

    const bathrooms = page.locator(`#${market}-options-accordion`)
      .getByRole("button", { name: "Bathrooms", exact: true });
    await bathrooms.click();
    await expect(bathrooms).toHaveAttribute("aria-expanded", "true");
    await expect.poll(() => events("Filter Section Opened")).toEqual([
      { page: market, layout, schema_version: 2, section: "Bathrooms", section_id: "bathrooms", source: "header" },
    ]);

    await page.evaluate(({ market, priceId }) => {
      const defaults = window.larentals.responsiveFilters.defaults[market];
      window.dash_clientside.set_props(priceId, { value: Math.round(defaults.priceUpperBound / 2) });
    }, { market, priceId });
    await expect.poll(() => events("Filter Changed")).toEqual([
      { page: market, layout, schema_version: 2, category, section_id: category },
    ]);

    if (mobile) {
      expect(await events("Filter Search Committed")).toEqual([]);
      expect(await events("Filter Group Committed")).toEqual([]);
      await page.evaluate((key) => document.getElementById(`${key}-filter-apply-button`).click(), market);
    }
    await expect.poll(() => events("Filter Search Committed")).toEqual([
      expect.objectContaining({
        page: market, layout, schema_version: 2, commit_mode: mobile ? "explicit" : "automatic",
        active_filter_count: 1, has_active_filters: true,
      }),
    ]);
    expect(await events("Filters Applied")).toHaveLength(mobile ? 1 : 0);
    expect(await events("Filter Group Committed")).toEqual([{
      page: market, layout, schema_version: 2, category, section_id: category,
      commit_mode: mobile ? "explicit" : "automatic", is_active: true,
    }]);
  });
}

test("location analytics wait for the resolver and exclude search text", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.route("**/analytics/script.js?*", (route) => route.fulfill({
    contentType: "application/javascript",
    body: "window.analyticsEvents = []; window.rybbit = { event: (...args) => window.analyticsEvents.push(args) };",
  }));

  let releaseLookup;
  const lookupGate = new Promise((resolve) => { releaseLookup = resolve; });
  await page.route("**/_dash-update-component?*", async (route) => {
    const body = route.request().postDataJSON();
    if (body?.inputs?.some(({ id, value }) => id === "lease-location-input" && value?.includes("Downey"))) {
      await lookupGate;
    }
    await route.continue();
  });

  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => Number.isFinite(window.larentals?.responsiveFilters?.appliedCounts?.lease));
  await page.locator("#lease-filter-open-button").click();
  const input = page.locator("input#lease-location-input");
  const events = (name) => page.evaluate((eventName) =>
    window.analyticsEvents.filter(([name]) => name === eventName).map(([, properties]) => properties), name);

  await input.fill("Downey");
  await input.press("Enter");
  await expect.poll(() => events("Location Added")).toHaveLength(1);
  expect(await events("Location Resolved")).toEqual([]);
  await page.evaluate(() => document.getElementById("lease-filter-apply-button").click());
  expect(await events("Filter Search Committed")).toEqual([]);

  releaseLookup();
  await expect.poll(() => events("Location Resolved")).toEqual([
    {
      page: "lease", layout: "bottom-sheet", schema_version: 2,
      method: expect.stringMatching(/^(suggestion|free_form)_keyboard$/), outcome: "resolved",
    },
  ]);
  await expect.poll(() => events("Filter Search Committed")).toEqual([
    expect.objectContaining({ commit_mode: "explicit", has_active_filters: true, has_results: true }),
  ]);
  expect((await events("Filter Changed")).map(({ category }) => category)).toEqual(["location"]);
  expect(await events("Filter Group Committed")).toEqual([{
    page: "lease", layout: "bottom-sheet", schema_version: 2, category: "location",
    section_id: "location", commit_mode: "explicit", is_active: true,
  }]);
});
