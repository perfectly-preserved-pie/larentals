const { test, expect } = require("@playwright/test");

for (const market of ["lease", "buy"]) {
const path = market === "lease" ? "/" : "/buy";
test(`${market} amenity requirements exclude absent or unknown features and intersect selections`, async ({ page }) => {
  await page.goto(path, { waitUntil: "domcontentloaded" });
  await page.waitForFunction((market) => window.larentals?.responsiveFilters?.defaults?.[market], market);
  const selections = await page.evaluate((market) => {
    const state = { ...window.larentals.responsiveFilters.defaults[market],
      pets: "any", terms: [], subtypes: [], furnished: [], laundry: [],
      sqftMissing: true, ppsqftMissing: true, parkingMissing: true, yearMissing: true,
      securityMissing: true, petDepositMissing: true, keyDepositMissing: true,
      otherDepositMissing: true, laundryMissing: true, dateMissing: true,
      ispMissing: true, rentControl: "any", zipBoundary: {},
      lotSizeMissing: true, hoaMissing: true, hoaFrequency: [],
    };
    const source = { type: "FeatureCollection", features: [
      ["both", "Yes", "Yes"], ["ac-only", "Yes", "No"],
      ["no-ac", "No", "Yes"], ["unknown", null, null],
    ].map(([mls_number, has_ac, has_dishwasher]) => ({
      type: "Feature", geometry: null,
      properties: { mls_number, has_ac, has_dishwasher,
        list_price: state.priceRange[0], bedrooms: state.bedroomsRange[0],
        total_bathrooms: state.bathroomsRange[0],
      },
    })) };
    const ids = (requiredAmenities) => window.larentals.filters[market === "lease" ? "filterLeaseState" : "filterBuyState"](
      { ...state, requiredAmenities }, source,
    ).features.map((feature) => feature.properties.mls_number);
    return { any: ids([]), yes: ids(["has_ac"]), dishwasher: ids(["has_dishwasher"]),
      both: ids(["has_ac", "has_dishwasher"]), legacy: ids(undefined) };
  }, market);
  expect(selections).toEqual({ any: ["both", "ac-only", "no-ac", "unknown"],
    yes: ["both", "ac-only"], dishwasher: ["both", "no-ac"],
    both: ["both"], legacy: ["both", "ac-only", "no-ac", "unknown"] });
});

test(`${market} phone amenity choices stage, apply, and reset with the other filters`, async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(path, { waitUntil: "domcontentloaded" });
  await page.waitForFunction((market) => window.larentals?.responsiveFilters?.defaults?.[market], market);
  await page.locator(`#${market}-filter-open-button`).click();
  const amenitiesSection = page.getByRole("button", { name: "Amenities" });
  if (await amenitiesSection.getAttribute("aria-expanded") !== "true") await amenitiesSection.click();
  if (market === "lease") {
    await expect(page.locator("#laundry_checklist")).toBeVisible();
    await expect(page.getByRole("button", { name: "Laundry", exact: true })).toHaveCount(0);
  }
  await page.getByRole("checkbox", { name: /Air conditioning/ }).check();
  await page.getByRole("checkbox", { name: /Dishwasher/ }).check();
  await page.waitForFunction((market) => window.larentals.responsiveFilters.drafts[market].requiredAmenities?.length === 2, market);
  expect(await page.evaluate((market) => window.larentals.responsiveFilters.applied[market].requiredAmenities, market)).toEqual([]);
  await page.locator(`#${market}-filter-apply-button`).click();
  await page.waitForFunction((market) => window.larentals.responsiveFilters.applied[market].requiredAmenities?.length === 2, market);
  await page.locator(`#${market}-filter-open-button`).click();
  await page.locator(`#${market}-filter-clear-button`).click();
  await page.waitForFunction((market) => window.larentals.responsiveFilters.drafts[market].requiredAmenities?.length === 0, market);
  if (await amenitiesSection.getAttribute("aria-expanded") !== "true") await amenitiesSection.click();
  await expect(page.getByRole("checkbox", { name: /Air conditioning/ })).not.toBeChecked();
  await expect(page.getByRole("checkbox", { name: /Dishwasher/ })).not.toBeChecked();
});

test(`${market} popup renders reported absence and unreported amenities`, async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.route(`**/api/${market}/listing-details/*`, async (route) => {
    const response = await route.fetch();
    const details = await response.json();
    await route.fulfill({ response, json: { ...details, has_ac: "No", has_dishwasher: null } });
  });
  await page.goto(path, { waitUntil: "domcontentloaded" });
  const row = page.locator(`[data-results-panel="${market}"] .results-row`).first();
  await expect(row).toBeVisible({ timeout: 30_000 });
  await row.click();
  const popup = page.locator(".leaflet-popup");
  await expect(popup.locator('.property-row').filter({ hasText: "Air Conditioning" })).toContainText("No (reported)");
  await expect(popup.locator('.property-row').filter({ hasText: "Dishwasher" })).toContainText("Not reported");
});

}
