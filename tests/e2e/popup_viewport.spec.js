const { test, expect } = require("@playwright/test");

for (const height of [900, 740, 600]) {
  test(`listing popups remain inside the map and accept clicks at 1440x${height}`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height });
    await page.goto("/", { waitUntil: "domcontentloaded" });
    const rows = page.locator('[data-results-panel="lease"] .results-row');
    await expect(rows.first()).toBeVisible({ timeout: 30_000 });
    for (let index = 0; index < 5; index++) {
      const row = rows.nth(index);
      const mls = await row.getAttribute("data-mls");
      await page.locator(`[data-results-panel="lease"] .results-row[data-mls="${mls}"]`).click();
      const popup = page.locator(".leaflet-popup");
      await expect(popup).toHaveCount(1);
      await expect(popup).toContainText("Listing ID (MLS#)");
      await expect.poll(() => page.evaluate(() => {
        const popup = document.querySelector(".leaflet-popup").getBoundingClientRect();
        const map = window.larentals.map.getContainer().getBoundingClientRect();
        return Math.min(popup.top - map.top, map.bottom - popup.bottom,
          popup.left - map.left, map.right - popup.right);
      })).toBeGreaterThanOrEqual(-1);
      const heightFraction = await popup.evaluate((element) => {
        const map = window.larentals.map.getContainer().getBoundingClientRect();
        const visibleHeight = Math.min(innerHeight, map.bottom) - Math.max(0, map.top);
        return element.getBoundingClientRect().height / visibleHeight;
      });
      expect(heightFraction).toBeLessThanOrEqual(0.8);
      await popup.locator('.property-row').first().click();
      await expect(popup).toContainText(mls);
    }
  });
}

test("open popup fits after browser height shrinks", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expect(page.locator('.results-row').first()).toBeVisible({ timeout: 30_000 });
  await page.locator('.results-row').first().click();
  await expect(page.locator('.leaflet-popup')).toContainText('Listing ID (MLS#)');
  await page.setViewportSize({ width: 1440, height: 600 });
  await expect.poll(() => page.evaluate(() => {
    const popup = document.querySelector('.leaflet-popup')?.getBoundingClientRect();
    const map = window.larentals.map.getContainer().getBoundingClientRect();
    return !!popup && popup.top >= map.top - 1 && popup.bottom <= map.bottom + 1;
  })).toBe(true);
});
