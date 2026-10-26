const { test, expect } = require("@playwright/test");
const path = require("node:path");

const pages = [
  { path: "/", key: "lease", target: "#lease-map-main", title: "Where to Rent in LA" },
  { path: "/buy", key: "buy", target: "#buy-map-main", title: "Where to Buy in LA" },
  { path: "/mcp", target: "#mcp-page-title", title: "Connect WhereToLive.LA to Your AI Assistant" },
];

test("public pages expose canonical social previews without JavaScript", async ({ browser, request }) => {
  const context = await browser.newContext({ javaScriptEnabled: false });
  const page = await context.newPage();
  for (const entry of pages) {
    // Exercise the actual response on an alternate host, including tracking data.
    const response = await request.get(entry.path + "?utm_source=preview", {
      headers: { Host: "preview.invalid" },
    });
    expect(response.ok()).toBe(true);
    await page.setContent(await response.text());
    await expect(page.locator("html")).toHaveAttribute("lang", "en");
    await expect(page.locator("html")).toHaveAttribute("data-mantine-color-scheme", "loading");
    const canonical = "https://wheretolive.la" + entry.path;
    for (const [selector, attribute, content] of [
      ['link[rel="canonical"]', "href", canonical],
      ['meta[property="og:url"]', "content", canonical],
      ['meta[property="og:title"]', "content", entry.title],
      ['meta[property="og:image"]', "content", "https://wheretolive.la/assets/social-preview.png"],
      ['meta[property="twitter:image"]', "content", "https://wheretolive.la/assets/social-preview.png"],
    ]) {
      await expect(page.locator(selector)).toHaveCount(1);
      await expect(page.locator(selector)).toHaveAttribute(attribute, content);
    }
    await expect(page.locator('meta[property="og:image:alt"]')).toHaveAttribute("content", /WhereToLive.LA/);
  }
  const preview = await request.get("/assets/social-preview.png");
  expect(preview.headers()["content-type"]).toContain("image/png");
  const png = await preview.body();
  expect([png.readUInt32BE(16), png.readUInt32BE(20)]).toEqual([1200, 630]);
  await context.close();
});

for (const width of [390, 1440]) {
  for (const entry of pages) {
    test(`${entry.path} keyboard skip link reaches content at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.goto(entry.path, { waitUntil: "domcontentloaded" });
      const heading = page.getByRole("heading", { level: 1 });
      await expect(heading).toHaveCount(1);
      await expect(heading).toHaveText(entry.key === "lease" ? "Homes for rent in Los Angeles County"
        : entry.key === "buy" ? "Homes for sale in Los Angeles County" : "Search LA housing from your AI assistant.");
      const skip = page.getByRole("link", { name: "Skip to main content" });
      await expect(skip).toHaveCount(1);
      await page.keyboard.press("Tab");
      await expect(skip).toBeFocused();
      const bounds = await skip.boundingBox();
      expect(bounds.y).toBeGreaterThanOrEqual(0);
      expect(bounds.x).toBeGreaterThanOrEqual(0);
      expect(bounds.x + bounds.width).toBeLessThanOrEqual(width);
      await page.keyboard.press("Enter");
      await expect(page.locator(entry.target)).toBeFocused();
      // The language hook must preserve Mantine's initialization at either width.
      await expect(page.locator("html")).toHaveAttribute("data-mantine-color-scheme", /^(light|dark)$/);
      if (entry.key) {
        const panel = page.locator(`#${entry.key}-filter-panel`);
        if (width === 390) {
          await page.locator(`#${entry.key}-filter-open-button`).click();
          await expect(panel).toHaveAttribute("role", "dialog");
          await expect(page.locator(entry.target)).toHaveJSProperty("inert", true);
          await page.keyboard.press("Escape");
          await expect(heading).toHaveCount(1);
          await expect(page.locator(entry.target)).toHaveJSProperty("inert", false);
        }
      }
    });
  }
}

for (const entry of pages.filter((entry) => entry.key)) {
  test(`${entry.key} photo reserves its frame before image delivery`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    let pendingImage;
    await page.route("**/photo-layout-fixture.png", (route) => { pendingImage = route; });
    await page.route(`**/api/${entry.key}/listing-details/*`, async (route) => {
      const response = await route.fetch();
      await route.fulfill({ response, json: { ...await response.json(), mls_photo: "/photo-layout-fixture.png" } });
    });
    await page.goto(entry.path, { waitUntil: "domcontentloaded" });
    const row = page.locator(`[data-results-panel="${entry.key}"] .results-row`).first();
    await expect(row).toBeVisible({ timeout: 30_000 });
    await row.click();
    const photo = page.locator('.leaflet-popup img[alt="Property photo"]');
    await expect(photo).toBeVisible();
    const before = await photo.boundingBox();
    expect(before.height).toBeCloseTo(before.width * 3 / 4, 0);
    expect(await photo.evaluate((image) => image.complete)).toBe(false);
    await expect.poll(() => Boolean(pendingImage)).toBe(true);
    await pendingImage.fulfill({ path: path.resolve(__dirname, "../../assets/social-preview.png") });
    await expect.poll(() => photo.evaluate((image) => image.complete && image.naturalWidth > 0)).toBe(true);
    const after = await photo.boundingBox();
    expect(after.height).toBeCloseTo(before.height, 0);
    expect(after.width).toBeCloseTo(before.width, 0);
  });
}
