const { test, expect } = require("@playwright/test");

const context = {
  address: "123 Example Ave",
  checked_at: "2026-10-25T20:00:00Z",
  fire: { status: "available", source_url: "https://osfm.fire.ca.gov/", zones: [{ designation: "Very High", responsibility: "LRA (2025 recommended)" }] },
  flood: { status: "available", source_url: "https://msc.fema.gov/portal/home", zones: [{ zone: "X", subtype: "0.2 PCT ANNUAL CHANCE FLOOD HAZARD", special_flood_hazard_area: "F" }] },
  zimas: {
    status: "available", source_url: "https://zimas.lacity.org/?pin=test", pin: "TEST PIN", apns: ["1234567890"],
    planning: [{ label: "Zoning", value: "[Q]R3-1", url: "https://zimas.lacity.org/" }, { label: "Specific Plan Area", value: "Example plan" }],
    hazards: [{ label: "Liquefaction", value: "Yes" }, { label: "Methane Hazard Site", value: "None" }],
    housing: [{ label: "Rent Stabilization Ordinance (RSO)", value: "Yes [APN: 1234567890]" }, { label: "Just Cause For Eviction Ordinance (JCO)", value: "Yes" }],
    cases: [{ label: "Environmental", value: "ENV-2026-EXAMPLE", url: "https://zimas.lacity.org/" }],
  },
  permits: { status: "available", source_url: "https://data.lacity.org/d/pi9x-tg5x", has_more: false, records: [
    { permit_nbr: "26016-10000-00001", permit_type: "Bldg-Alter/Repair", primary_address: "123 EXAMPLE AVE", work_desc: "Kitchen remodel", status_desc: "Permit Expired", issue_date: "2026-01-01T00:00:00", status_date: "2026-09-01T00:00:00", refresh_time: "2026-10-19T00:00:00" },
  ] },
};

for (const market of ["buy", "lease"]) {
  for (const mobile of [false, true]) {
    test(`${market} property drawer preserves source details on ${mobile ? "phone" : "desktop"}`, async ({ page }) => {
      await page.setViewportSize(mobile ? { width: 390, height: 844 } : { width: 1440, height: 900 });
      const errors = [];
      page.on("pageerror", error => errors.push(error.message));
      let requests = 0;
      await page.route(`**/api/${market}/listing-details/*`, route => route.fulfill({ json: { mls_number: "CONTEXT-TEST", full_street_address: "123 Example Ave", list_price: 5000, subtype: "Single Family Residence" } }));
      await page.route(`**/api/${market}/property-context/*`, route => {
        requests += 1;
        return route.fulfill({ json: context });
      });
      await page.goto(market === "buy" ? "/buy" : "/", { waitUntil: "domcontentloaded" });
      await page.waitForFunction(() => window.larentals?.map && window.larentals?.popups?.openAt);
      await page.evaluate(() => {
        window.larentals.map.setView([34.05, -118.25], 13);
        window.larentals.popups.openAt([34.05, -118.25], { mls_number: "CONTEXT-TEST" }, { centerInMap: true });
      });
      const summary = page.locator(".leaflet-popup .property-context-summary");
      await expect(summary).toContainText("Very High");
      await expect(summary).toContainText("0.2 PCT ANNUAL CHANCE FLOOD HAZARD");
      if (market === "buy") await expect(summary).toContainText("[Q]R3-1");
      await summary.getByRole("button", { name: "View property records" }).click();
      const drawer = page.getByRole("dialog", { name: "Property records & hazards" });
      await expect(drawer).toBeVisible();
      await expect(drawer).toContainText("Records checked");
      expect(requests).toBe(1);
      await expect(drawer.locator("details").first().locator("summary")).toHaveText(market === "lease" ? "Housing & tenant protections" : "Mapped hazards");
      if (market === "lease") {
        await expect(drawer).toContainText("Yes [APN: 1234567890]");
        await drawer.getByText("Building permit history", { exact: true }).click();
      }
      await expect(drawer).toContainText("Permit Expired");
      await expect(drawer).toContainText("An issued permit does not establish completed work");
      const box = await drawer.boundingBox();
      expect(box.x).toBeGreaterThanOrEqual(0);
      expect(box.x + box.width).toBeLessThanOrEqual(mobile ? 391 : 1441);
      await page.keyboard.press("Escape");
      await expect(drawer).not.toBeVisible();
      await expect(summary.getByRole("button")).toBeFocused();
      expect(errors).toEqual([]);
    });
  }
}

test("partial source failures keep flood facts and coverage visible without executable source markup", async ({ page }) => {
  await page.route("**/api/buy/listing-details/*", route => route.fulfill({ json: { mls_number: "PARTIAL", full_street_address: "123 Example Ave" } }));
  await page.route("**/api/buy/property-context/*", route => route.fulfill({ json: {
    ...context, address: '<img src=x onerror="window.injected=true">',
    fire: { status: "unavailable", zones: [] },
    zimas: { status: "outside_coverage", source_url: "javascript:window.injected=true" },
    permits: { status: "outside_coverage", records: [] },
  } }));
  await page.goto("/buy", { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => window.larentals?.map && window.larentals?.popups?.openAt);
  await page.evaluate(() => window.larentals.popups.openAt([34.05, -118.25], { mls_number: "PARTIAL" }, { centerInMap: true }));
  const summary = page.locator(".property-context-summary");
  await expect(summary).toContainText("Not available");
  await expect(summary).toContainText("Outside LA City coverage");
  await expect(summary).toContainText("0.2 PCT");
  await summary.getByRole("button").click();
  const drawer = page.getByRole("dialog");
  await expect(drawer).toContainText("This listing is outside that coverage");
  await expect(drawer.locator("img")).toHaveCount(0);
  await expect(drawer.locator('a[href^="javascript:"]')).toHaveCount(0);
  expect(await page.evaluate(() => window.injected)).toBeUndefined();
});

test("a late property response cannot replace the next home's drawer", async ({ page }) => {
  let releaseFirst;
  const firstResponse = new Promise(resolve => { releaseFirst = resolve; });
  await page.route("**/api/buy/listing-details/*", route => route.fulfill({ json: { full_street_address: "Listing details" } }));
  await page.route("**/api/buy/property-context/*", async route => {
    const slow = route.request().url().endsWith("SLOW");
    if (slow) await firstResponse;
    await route.fulfill({ json: { ...context, address: slow ? "Previous property" : "Next property" } });
  });
  await page.goto("/buy", { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => window.larentals?.map && window.larentals?.popups?.openAt);
  await page.evaluate(() => window.larentals.popups.openAt([34.05, -118.25], { mls_number: "SLOW" }, { centerInMap: true }));
  await page.locator(".property-context-open").click();
  await expect(page.getByRole("dialog")).toContainText("Loading official property records");
  await page.keyboard.press("Escape");
  await page.evaluate(() => window.larentals.popups.openAt([34.05, -118.25], { mls_number: "FAST" }, { centerInMap: true }));
  await page.locator('[data-property-id="FAST"] .property-context-open').click();
  const drawer = page.getByRole("dialog");
  await expect(drawer).toContainText("Next property");
  const lateResponse = page.waitForResponse(response => response.url().endsWith("/property-context/SLOW"));
  releaseFirst();
  await lateResponse;
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  await expect(drawer).not.toContainText("Previous property");
  await expect(drawer).toContainText("Next property");
});
