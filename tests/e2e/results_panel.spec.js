const { test, expect } = require("@playwright/test");

const pages = [
  { name: "lease", path: "/", key: "lease" },
  { name: "buy", path: "/buy", key: "buy" },
];

for (const listingPage of pages) {
  test(`${listingPage.name} result click preserves zoom and opens that listing`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(listingPage.path, { waitUntil: "domcontentloaded" });

    const rows = page.locator(`[data-results-panel="${listingPage.key}"] .results-row`);
    await expect(rows.first()).toBeVisible({ timeout: 30_000 });
    const mls = await rows.first().getAttribute("data-mls");
    expect(mls).toBeTruthy();

    const initialZoom = await page.evaluate(() => window.larentals.map.getZoom());
    await rows.first().click();
    await page.waitForFunction((expectedMls) => {
      const popup = window.larentals?.map?._popup;
      return popup && String(popup.larentalsMls) === String(expectedMls);
    }, mls, { timeout: 15_000 });
    await expect(page.locator(".leaflet-popup")).toBeVisible();
    expect(await page.evaluate(() => window.larentals.map.getZoom())).toBe(initialZoom);
    await expect(page.locator(`.results-row[data-mls="${mls}"]`)).toHaveClass(/is-open/);
    await expect(page.locator(".leaflet-popup .listing-popup__zoom")).toHaveCount(0);
  });

  test(`${listingPage.name} popup pane stacks above overlay controls`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(listingPage.path, { waitUntil: "domcontentloaded" });

    const row = page.locator(`[data-results-panel="${listingPage.key}"] .results-row`).first();
    await expect(row).toBeVisible({ timeout: 30_000 });
    await row.click();
    await expect(page.locator(".leaflet-popup")).toBeVisible();

    const stacking = await page.evaluate(() => {
      const pane = document.querySelector(".leaflet-popup-pane");
      const controls = document.querySelector(".leaflet-top");
      return {
        popupPane: Number.parseInt(getComputedStyle(pane).zIndex, 10),
        controls: Number.parseInt(getComputedStyle(controls).zIndex, 10),
      };
    });
    expect(stacking.popupPane).toBeGreaterThan(stacking.controls);
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
    const initialZoom = await page.evaluate(() => window.larentals.map.getZoom());

    await page.evaluate((rowSelector) => {
      document.querySelectorAll(rowSelector).forEach((row, index) => {
        if (index < 6) row.click();
      });
    }, selector);
    const expectedMls = listingIds[listingIds.length - 1];
    await page.waitForFunction((mls) => {
      const map = window.larentals?.map;
      return map?._popup && String(map._popup.larentalsMls) === String(mls);
    }, expectedMls, { timeout: 15_000 });
    await expect(page.locator(".leaflet-popup")).toHaveCount(1);
    await expect(page.locator(".leaflet-popup")).toBeVisible();
    expect(await page.evaluate(() => window.larentals.map.getZoom())).toBe(initialZoom);
  });
}

test("listing popup paints above overlay controls when they overlap", async ({ page }) => {
  await page.setViewportSize({ width: 627, height: 1004 });
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => window.larentals?.map && document.querySelector(".leaflet-top .leaflet-control"));

  await page.evaluate(() => {
    const map = window.larentals.map;
    const container = map.getContainer();
    const control = document.querySelector(".leaflet-top .leaflet-control");
    const rect = control.getBoundingClientRect();
    const containerRect = container.getBoundingClientRect();
    const point = map.containerPointToLatLng([
      rect.left + rect.width / 2 - containerRect.left,
      rect.top + rect.height / 2 - containerRect.top,
    ]);
    window.larentals.popups.openAt(point, { subtype: "Listing", list_price: 0 });
  });
  await expect(page.locator(".leaflet-popup")).toBeVisible();

  const overlapHit = await page.evaluate(() => {
    const popup = document.querySelector(".leaflet-popup");
    const popupRect = popup.getBoundingClientRect();
    const controls = [...document.querySelectorAll(".leaflet-top .leaflet-control")];
    for (const control of controls) {
      const rect = control.getBoundingClientRect();
      const left = Math.max(popupRect.left, rect.left);
      const top = Math.max(popupRect.top, rect.top);
      const right = Math.min(popupRect.right, rect.right);
      const bottom = Math.min(popupRect.bottom, rect.bottom);
      if (right <= left || bottom <= top) continue;
      const topmost = document.elementFromPoint(left + 3, top + 3);
      return topmost?.closest(".leaflet-popup") === popup;
    }
    return false;
  });
  expect(overlapHit).toBe(true);

  await page.evaluate(() => window.larentals.map.closePopup());
  await expect(page.locator(".leaflet-popup")).toHaveCount(0);
  const restoredControlZ = await page.locator(".leaflet-top.leaflet-left").evaluate((element) =>
    Number.parseInt(getComputedStyle(element).zIndex, 10),
  );
  expect(restoredControlZ).toBeGreaterThan(900);
});

test("lease popup listing links stay on canonical http(s) URLs", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/", { waitUntil: "domcontentloaded" });

  const rows = page.locator('[data-results-panel="lease"] .results-row');
  await expect(rows.first()).toBeVisible({ timeout: 30_000 });
  const mls = await rows.first().getAttribute("data-mls");
  expect(mls).toBeTruthy();

  await rows.first().click();
  await page.waitForFunction((expectedMls) => {
    const map = window.larentals?.map;
    return map?._popup &&
      String(map._popup.larentalsMls) === String(expectedMls) &&
      !document.querySelector(".leaflet-popup")?.innerText.includes("Loading listing details");
  }, mls, { timeout: 15_000 });

  const popupLinks = page.locator(".leaflet-popup .plausible-listing-link");
  await expect(popupLinks.first()).toBeVisible();
  const popupHrefs = await popupLinks.evaluateAll((elements) =>
    [...new Set(elements.map((element) => element.getAttribute("href")).filter(Boolean))],
  );
  expect(popupHrefs.length).toBeGreaterThan(0);
  for (const href of popupHrefs) {
    expect(href).toMatch(/^https?:\/\//);
  }
});
