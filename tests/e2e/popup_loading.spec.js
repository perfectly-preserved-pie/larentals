const { test, expect } = require("@playwright/test");

for (const market of ["lease", "buy"]) {
  const pagePath = market === "lease" ? "/" : "/buy";

  test(`${market} popup shows loading, handles failure, and retries on reopen`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    let pending;
    let requests = 0;
    await page.route(`**/api/${market}/listing-details/*`, (route) => {
      requests++;
      if (requests === 1) pending = route;
      else return route.continue();
    });
    await page.goto(pagePath, { waitUntil: "domcontentloaded" });
    const row = page.locator(`[data-results-panel="${market}"] .results-row`).first();
    await expect(row).toBeVisible({ timeout: 30_000 });
    const mls = await row.getAttribute("data-mls");
    await row.click();
    const popup = page.locator(".leaflet-popup");
    await expect(popup).toContainText("Loading listing details...");
    await expect(popup).toContainText(mls);
    await expect.poll(() => Boolean(pending)).toBe(true);
    await pending.fulfill({ status: 503, json: { error: "Temporary test failure" } });
    await expect(popup).toContainText("Could not load listing details right now.");
    await expect(popup).toContainText(mls);
    await popup.locator(".leaflet-popup-close-button").click();
    await expect(popup).toHaveCount(0);
    await row.click();
    await expect(popup).toContainText("Listing ID (MLS#)");
    await expect(popup).not.toContainText("Loading listing details...");
    await expect(popup).not.toContainText("Could not load listing details right now.");
    expect(requests).toBe(2);
  });

  test(`${market} a delayed earlier response does not replace the selected listing`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    let firstRequest;
    let firstResponse;
    await page.route(`**/api/${market}/listing-details/*`, async (route) => {
      const response = await route.fetch();
      const details = await response.json();
      if (!firstRequest) {
        firstRequest = route;
        firstResponse = { ...details, full_street_address: "FIRST DELAYED LISTING" };
      } else {
        await route.fulfill({ json: { ...details, full_street_address: "SECOND SELECTED LISTING" } });
      }
    });
    await page.goto(pagePath, { waitUntil: "domcontentloaded" });
    const rows = page.locator(`[data-results-panel="${market}"] .results-row`);
    await expect(rows.nth(1)).toBeVisible({ timeout: 30_000 });
    await rows.first().click();
    await expect(page.locator(".leaflet-popup")).toContainText("Loading listing details...");
    await expect.poll(() => Boolean(firstRequest)).toBe(true);
    await rows.nth(1).click();
    await expect(page.locator(".leaflet-popup")).toHaveCount(1);
    await expect(page.locator(".leaflet-popup")).toContainText(/second selected listing/i);
    const finished = page.waitForEvent("requestfinished", (request) => request.url() === firstRequest.request().url());
    await firstRequest.fulfill({ json: firstResponse });
    await finished;
    // Let the earlier fetch promise update its popup, if it incorrectly still owns one.
    await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    await expect(page.locator(".leaflet-popup")).toHaveCount(1);
    await expect(page.locator(".leaflet-popup")).toContainText(/second selected listing/i);
    await expect(page.locator(".leaflet-popup")).not.toContainText(/first delayed listing/i);
  });
}
