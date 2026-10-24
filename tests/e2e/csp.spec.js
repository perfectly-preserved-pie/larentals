const { test, expect } = require("@playwright/test");
const { createHash } = require("node:crypto");

const BASE_URL = process.env.CSP_TEST_BASE_URL || "http://127.0.0.1:8050";
test.use({ launchOptions: { args: ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"] } });

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    window.cspViolations = [];
    document.addEventListener("securitypolicyviolation", (event) => {
      window.cspViolations.push({ directive: event.effectiveDirective, blocked: event.blockedURI });
    });
  });
});

for (const path of ["/", "/buy", "/mcp"]) {
  test(`CSP allows required resources on ${path}`, async ({ page }) => {
    const response = await page.goto(BASE_URL + path, { waitUntil: "networkidle" });
    const policy = response.headers()["content-security-policy"];
    expect(policy).toContain("'sha256-");
    expect(policy).not.toContain("'unsafe-eval'");
    expect(policy.split("; ").find((part) => part.startsWith("script-src "))).not.toContain("'unsafe-inline'");
    if (path !== "/mcp") {
      await expect(page.locator(".results-row").first()).toBeVisible();
      await page.locator(".results-row").first().click();
      const report = page.locator("[data-report-listing]");
      await expect(report).toBeVisible({ timeout: 30_000 });
      await report.click();
      await expect(page.locator(".swal2-popup")).toBeVisible();
      await page.keyboard.press("Escape");
    }
    expect(await page.evaluate(() => window.cspViolations)).toEqual([]);
  });
}

test("CSP blocks injected inline scripts and event handlers", async ({ page }) => {
  await page.goto(BASE_URL, { waitUntil: "networkidle" });
  await page.evaluate(() => {
    const script = document.createElement("script");
    script.textContent = "window.injectedScriptRan = true";
    document.body.appendChild(script);
    const button = document.createElement("button");
    button.setAttribute("onclick", "window.injectedHandlerRan = true");
    document.body.appendChild(button);
    button.click();
  });
  await expect.poll(() => page.evaluate(() => window.cspViolations.length)).toBeGreaterThanOrEqual(2);
  expect(await page.evaluate(() => Boolean(window.injectedScriptRan || window.injectedHandlerRan))).toBe(false);
  expect(await page.evaluate(() => window.cspViolations.map((entry) => entry.directive)))
    .toEqual(expect.arrayContaining(["script-src-elem", "script-src-attr"]));
});

test("CSP blocks JavaScript eval inside an approved script", async ({ page }) => {
  const probe = "try { eval('window.evalRan = true'); } catch (error) { window.evalBlocked = error.name; }";
  const hash = createHash("sha256").update(probe).digest("base64");
  await page.route(BASE_URL + "/", async (route) => {
    const response = await route.fetch();
    const headers = response.headers();
    headers["content-security-policy"] = headers["content-security-policy"]
      .replace("script-src 'self'", `script-src 'self' 'sha256-${hash}'`);
    await route.fulfill({ response, headers, body: (await response.text()).replace("</body>", `<script>${probe}</script></body>`) });
  });
  await page.goto(BASE_URL, { waitUntil: "networkidle" });
  expect(await page.evaluate(() => window.evalBlocked)).toBe("EvalError");
  expect(await page.evaluate(() => Boolean(window.evalRan))).toBe(false);
});

test("CSP allows every optional map layer", async ({ page }) => {
  test.setTimeout(120_000);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto(BASE_URL, { waitUntil: "networkidle" });
  await page.locator(".layers-control-disclosure__button").click();
  const controls = page.locator(".leaflet-control-layers-list input");
  for (const input of await controls.all()) {
    await input.check();
    // Overlay data and the heatmap plugin load after the checkbox changes.
    await page.waitForTimeout(1000);
    if (await input.getAttribute("type") === "checkbox") await input.uncheck();
  }
  expect(await page.evaluate(() => window.cspViolations)).toEqual([]);
});

test.describe("gesture model resources", () => {
  test("CSP allows camera and WebAssembly startup", async ({ page }) => {
    test.setTimeout(90_000);
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto(BASE_URL, { waitUntil: "networkidle" });
    await page.locator('[data-map-gesture-panel="toggle"]').click();
    const toggle = page.locator('[data-map-gesture-control="toggle"]');
    await toggle.click();
    await expect(toggle).toHaveAttribute("aria-pressed", "true", { timeout: 60_000 });
    expect(await page.evaluate(() => window.cspViolations)).toEqual([]);
    await toggle.click();
    await expect(toggle).toHaveAttribute("aria-pressed", "false");
  });
});
