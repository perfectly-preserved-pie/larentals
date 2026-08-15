const { test, expect } = require("@playwright/test");

const BASE_URL = "http://127.0.0.1:8050";
const DISCOVERY_STORAGE_KEY = "wttl.layers-control-discovery.v1";

test("layers control uses an explicit accessible disclosure", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.addInitScript((storageKey) => localStorage.removeItem(storageKey), DISCOVERY_STORAGE_KEY);
  await page.goto(BASE_URL, { waitUntil: "domcontentloaded" });

  const control = page.locator(".layers-control-disclosure");
  const button = control.locator(".layers-control-disclosure__button");
  const panel = control.locator(".leaflet-control-layers-list");

  await expect(button).toBeVisible();
  await expect(button).toHaveAccessibleName("Show map layers");
  await expect(button).toHaveAttribute("aria-expanded", "false");
  await expect(panel).toBeHidden();
  const discoveryHint = control.locator(".layers-control-discovery");
  await expect(discoveryHint).toContainText(
    "More map layers available",
  );

  const hintGeometry = await discoveryHint.boundingBox();
  const buttonGeometry = await button.boundingBox();
  expect(hintGeometry.x).toBeGreaterThan(buttonGeometry.x + buttonGeometry.width + 4);
  expect(hintGeometry.height).toBeLessThanOrEqual(40);

  await button.hover();
  await page.locator("#map").hover({ position: { x: 500, y: 400 } });
  await expect(button).toHaveAttribute("aria-expanded", "false");

  await button.click();
  await expect(button).toHaveAttribute("aria-expanded", "true");
  await expect(button).toHaveAccessibleName("Collapse map layers");
  await expect(panel).toBeVisible();
  await expect(control.locator(".layers-control-discovery")).toHaveCount(0);

  await page.keyboard.press("Escape");
  await expect(button).toHaveAttribute("aria-expanded", "false");
  await expect(button).toBeFocused();

  await button.click();
  await page.locator("#map").click({ position: { x: 500, y: 400 } });
  await expect(button).toHaveAttribute("aria-expanded", "false");

  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.locator(".layers-control-discovery")).toHaveCount(0);
});
