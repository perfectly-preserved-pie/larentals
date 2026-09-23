const { test, expect } = require("@playwright/test");

const pages = [
  { name: "lease", path: "/", key: "lease" },
  { name: "buy", path: "/buy", key: "buy" },
];

for (const listingPage of pages) {
  test(`${listingPage.name} result click centers, zooms, and opens that listing`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(listingPage.path, { waitUntil: "domcontentloaded" });

    const rows = page.locator(`[data-results-panel="${listingPage.key}"] .results-row`);
    await expect(rows.first()).toBeVisible({ timeout: 30_000 });
    const mls = await rows.first().getAttribute("data-mls");
    expect(mls).toBeTruthy();

    await rows.first().click();
    await page.waitForFunction((expectedMls) => {
      const map = window.larentals?.map;
      const popup = map?._popup;
      return popup &&
        String(popup.larentalsMls) === String(expectedMls) &&
        map.getZoom() >= 16 &&
        map.distance(map.getCenter(), popup.getLatLng()) < 3000;
    }, mls, { timeout: 15_000 });
    const popup = page.locator(".leaflet-popup");
    await expect(popup).toBeVisible();
    await page.waitForFunction(() => {
      const mapEl = document.querySelector(".leaflet-container");
      const popupEl = document.querySelector(".leaflet-popup");
      if (!mapEl || !popupEl || popupEl.innerText.includes("Loading listing details")) return false;
      const map = mapEl.getBoundingClientRect();
      const card = popupEl.getBoundingClientRect();
      return Math.abs((card.left + card.width / 2) - (map.left + map.width / 2)) < 8 &&
        Math.abs((card.top + card.height / 2) - (map.top + map.height / 2)) < 8;
    }, null, { timeout: 15_000 });
  });

  test(`${listingPage.name} rapid result clicks leave the final listing focused`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(listingPage.path, { waitUntil: "domcontentloaded" });

    const selector = `[data-results-panel="${listingPage.key}"] .results-row`;
    await expect(page.locator(selector).first()).toBeVisible({ timeout: 30_000 });
    const listingIds = await page.locator(selector).evaluateAll((elements) =>
      elements.slice(0, 6).map((element) => element.dataset.mls),
    );
    expect(listingIds).toHaveLength(6);

    await page.evaluate((rowSelector) => {
      document.querySelectorAll(rowSelector).forEach((row, index) => {
        if (index < 6) row.click();
      });
    }, selector);
    const expectedMls = listingIds[listingIds.length - 1];
    await page.waitForFunction((mls) => {
      const map = window.larentals?.map;
      return map?._popup && String(map._popup.larentalsMls) === String(mls) && map.getZoom() >= 16;
    }, expectedMls, { timeout: 15_000 });
    await expect(page.locator(".leaflet-popup")).toBeVisible();
  });
}
