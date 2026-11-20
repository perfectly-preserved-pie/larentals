const { test, expect } = require("@playwright/test");
const path = require("node:path");

const pages = [
  { path: "/", key: "lease", target: "#lease-map-main", title: "Where to Rent in LA" },
  { path: "/buy", key: "buy", target: "#buy-map-main", title: "Where to Buy in LA" },
  { path: "/mcp", target: "#mcp-page-title", title: "Connect WhereToLive.LA to Your AI Assistant" },
];

test("public pages expose canonical social previews without JavaScript", async ({ baseURL, browser, request }) => {
  const context = await browser.newContext({ javaScriptEnabled: false });
  const page = await context.newPage();
  for (const entry of pages) {
    // Exercise the actual response on an alternate host, including tracking data.
    const response = await request.get(entry.path + "?utm_source=preview", {
      headers: { Host: "preview.invalid" },
    });
    expect(response.ok()).toBe(true);
    expect(response.headers().link).toContain('</llms.txt>; rel="alternate"; type="text/plain"');
    await page.setContent(await response.text());
    await expect(page.locator("html")).toHaveAttribute("lang", "en");
    await expect(page.locator("html")).toHaveAttribute("data-mantine-color-scheme", entry.key ? "loading" : "light");
    await expect(page).toHaveTitle(entry.title + " | WhereToLive.LA");
    await expect(page.locator("main h1")).toHaveCount(1);
    if (!entry.key) {
      await expect(page.locator("main")).toContainText("https://wheretolive.la/_mcp");
    }
    const canonical = "https://wheretolive.la" + entry.path;
    for (const [selector, attribute, content] of [
      ['link[rel="canonical"]', "href", canonical],
      ['link[rel="alternate"][type="text/plain"]', "href", "/llms.txt"],
      ['link[rel="alternate"][type="text/markdown"]', "href", canonical + (entry.path === "/" ? "index.md" : ".md")],
      ['meta[property="og:url"]', "content", canonical],
      ['meta[property="og:title"]', "content", entry.title],
      ['meta[property="og:image"]', "content", "https://wheretolive.la/assets/social-preview.png"],
      ['meta[property="twitter:image"]', "content", "https://wheretolive.la/assets/social-preview.png"],
    ]) {
      await expect(page.locator(selector)).toHaveCount(1);
      await expect(page.locator(selector)).toHaveAttribute(attribute, content);
    }
    await expect(page.locator('meta[property="og:image:alt"]')).toHaveAttribute("content", /WhereToLive.LA/);
    await page.goto(new URL(entry.path, baseURL).href);
    await expect(page.locator(entry.key ? ".initial-page" : ".mcp-docs")).toBeVisible();
    if (!entry.key) {
      await expect(page.locator(".mcp-docs h3")).toHaveText([
        "Claude", "ChatGPT", "Codex", "Hermes Agent", "Other clients",
      ]);
      await expect(page.locator(".mcp-docs")).toContainText("Create as a plugin");
      await expect(page.locator("#mcp-hermes-yaml-value")).toHaveText(/mcp_servers:\s+wheretolive:/);
      await expect(page.locator(".mcp-docs")).toContainText("Long Beach");
      await expect(page.getByRole("button", { name: "Copy URL" })).toBeHidden();
    }
  }
  const preview = await request.get("/assets/social-preview.png");
  expect(preview.headers()["content-type"]).toContain("image/png");
  const png = await preview.body();
  expect([png.readUInt32BE(16), png.readUInt32BE(20)]).toEqual([1200, 630]);
  await context.close();
});

test("the static introduction stays hidden while Dash is unavailable", async ({ page }) => {
  await page.route(/\/_dash-component-suites\/dash\/dash-renderer\//, (route) => route.abort());
  for (const entry of pages.filter((entry) => entry.key)) {
    await page.goto(entry.path);
    const introduction = page.locator("#react-entry-point .initial-page");
    await expect(introduction).toHaveCount(1);
    await expect(introduction).toHaveCSS("display", "none");
  }
});

test("standalone MCP guide shares the saved site theme", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light" });
  await page.goto("/mcp");
  const darkMode = page.getByRole("switch", { name: "Dark mode" });
  await expect(darkMode).not.toBeChecked();
  await darkMode.check();
  await expect(page.locator("html")).toHaveAttribute("data-mantine-color-scheme", "dark");
  await page.reload();
  await expect(darkMode).toBeChecked();
  await page.getByRole("link", { name: "Rentals", exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute("data-mantine-color-scheme", "dark");
});

test("missing discovery files return HTTP 404 outside the page shell", async ({ request }) => {
  for (const pathname of ["/missing-page", "/.well-known/agents.json",
    "/.well-known/mcp.json", "/.well-known/agent-card.json"]) {
    expect((await request.get(pathname)).status()).toBe(404);
  }
  const manifest = await request.get("/llms.txt");
  expect(manifest.ok()).toBe(true);
  expect(manifest.headers()["content-type"]).toContain("text/plain");
  const fullGuide = await request.get("/llms-full.txt");
  expect(fullGuide.ok()).toBe(true);
  expect(fullGuide.headers()["content-type"]).toContain("text/plain");
  expect(await fullGuide.text()).toContain("codex mcp add wheretolive");
  expect(await fullGuide.text()).toContain("Create as a plugin");
  for (const [mirror, canonical] of [["/index.md", "/"], ["/buy.md", "/buy"], ["/mcp.md", "/mcp"]]) {
    const response = await request.get(mirror);
    expect(response.ok()).toBe(true);
    expect(response.headers()["content-type"]).toContain("text/markdown");
    expect(response.headers().link).toBe(`<https://wheretolive.la${canonical}>; rel="canonical"`);
    expect(await response.text()).toMatch(/^---\ntitle: .+/);
    if (mirror === "/mcp.md") {
      const markdown = await response.text();
      expect(markdown).toContain("### Hermes Agent");
      expect(markdown).toContain("mcp_servers:\n  wheretolive:");
      expect(markdown).toContain("Long Beach");
    }
  }
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

test("MCP setup snippets copy with the keyboard and keep focus", async ({ context, page }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.goto("/mcp", { waitUntil: "domcontentloaded" });

  for (const name of ["Copy URL", "Copy command", "Copy Codex command", "Copy YAML"]) {
    const button = page.getByRole("button", { name, exact: true });
    const target = await button.getAttribute("data-mcp-copy");
    const snippet = await page.locator(`#${target}`).textContent();

    await button.focus();
    await page.keyboard.press("Enter");
    await expect(button).toHaveText("Copied!");
    await expect(button).toBeFocused();
    expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(snippet);
  }
});

for (const entry of pages.filter((entry) => entry.key)) {
  test(`${entry.key} photo reserves its frame before image delivery`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    // Measure the reserved frame without the result popup's entrance scale animation.
    await page.emulateMedia({ reducedMotion: "reduce" });
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
