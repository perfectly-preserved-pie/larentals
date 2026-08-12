const { test, expect } = require("@playwright/test");

const BASE_URL = "http://127.0.0.1:8050";

/**
 * Record unexpected browser errors raised while a test exercises the page.
 * @param {import("@playwright/test").Page} page Playwright page under test.
 * @returns {Promise<string[]>} Mutable error list populated by event handlers.
 */
async function collectPageErrors(page) {
  const errors = [];
  page.on("pageerror", (error) => errors.push(`pageerror: ${error.message}`));
  page.on("console", (message) => {
    const text = message.text();
    if (
      message.type() === "error" &&
      !text.includes("dash-version.plotly.com") &&
      !text.includes("Failed to load resource")
    ) errors.push(`console: ${text}`);
  });
  return errors;
}

/**
 * Wait until defaults and result counts initialize for one listing page.
 * @param {import("@playwright/test").Page} page Playwright page under test.
 * @param {"lease" | "buy"} pageType Listing mode expected to initialize.
 * @returns {Promise<void>}
 */
async function waitForFilterState(page, pageType) {
  await page.waitForFunction(
    (key) => Boolean(
      window.larentals?.responsiveFilters?.defaults?.[key] &&
      Number.isFinite(window.larentals?.responsiveFilters?.appliedCounts?.[key])
    ),
    pageType,
    { timeout: 20_000 },
  );
}

for (const entry of [
  { pageType: "lease", path: "/", sliderId: "rental_price_slider" },
  { pageType: "buy", path: "/buy", sliderId: "list_price_slider" },
]) {
  test(`${entry.pageType} uses a map-first staged filter sheet on phones`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    const errors = await collectPageErrors(page);
    await page.goto(`${BASE_URL}${entry.path}`, { waitUntil: "domcontentloaded" });
    await waitForFilterState(page, entry.pageType);

    const map = page.locator("#map");
    const toolbar = page.locator(`[data-filter-toolbar='${entry.pageType}']`);
    const panel = page.locator(`[data-filter-panel='${entry.pageType}']`);
    await expect(map).toBeVisible();
    await expect(toolbar).toBeVisible();
    await expect(panel).not.toHaveClass(/is-open/);
    const mapBox = await map.boundingBox();
    expect(mapBox.y).toBeLessThanOrEqual(1);
    expect(mapBox.height).toBeGreaterThanOrEqual(800);

    const initial = await page.evaluate((key) => ({
      defaults: window.larentals.responsiveFilters.defaults[key],
      appliedCount: window.larentals.responsiveFilters.appliedCounts[key],
    }), entry.pageType);

    await page.locator(`#${entry.pageType}-filter-open-button`).click();
    await expect(panel).toHaveClass(/is-open/);
    await expect(panel).toHaveAttribute("role", "dialog");
    await expect(panel).toHaveAttribute("aria-modal", "true");

    await page.evaluate(({ sliderId, upper }) => {
      window.dash_clientside.set_props(sliderId, { value: [0, upper] });
    }, {
      sliderId: entry.sliderId,
      upper: Math.max(1, Math.round(initial.defaults.priceRange[1] * 0.55)),
    });

    await page.waitForFunction(
      (key) => window.larentals.responsiveFilters.previewCounts[key] !==
        window.larentals.responsiveFilters.appliedCounts[key],
      entry.pageType,
      { timeout: 10_000 },
    );
    const whileEditing = await page.evaluate((key) => ({
      appliedPrice: window.larentals.responsiveFilters.applied[key].priceRange,
      draftPrice: window.larentals.responsiveFilters.drafts[key].priceRange,
    }), entry.pageType);
    expect(whileEditing.appliedPrice).toEqual(initial.defaults.priceRange);
    expect(whileEditing.draftPrice).not.toEqual(initial.defaults.priceRange);

    const sheetGeometry = await page.evaluate((key) => {
      const panel = document.getElementById(`${key}-filter-panel`).getBoundingClientRect();
      const footer = document.querySelector(`#${key}-filter-panel .responsive-filter-panel__footer`).getBoundingClientRect();
      return { panel: { top: panel.top, bottom: panel.bottom }, footer: { top: footer.top, bottom: footer.bottom } };
    }, entry.pageType);
    expect(sheetGeometry.footer.top).toBeGreaterThanOrEqual(sheetGeometry.panel.top);
    expect(sheetGeometry.footer.bottom).toBeLessThanOrEqual(sheetGeometry.panel.bottom + 1);
    await page.evaluate((key) => document.getElementById(`${key}-filter-apply-button`).click(), entry.pageType);
    await expect(panel).not.toHaveClass(/is-open/);
    await page.waitForFunction(
      (key) => window.larentals.responsiveFilters.applied[key].priceRange[1] !==
        window.larentals.responsiveFilters.defaults[key].priceRange[1],
      entry.pageType,
    );
    await expect(page.locator(`#${entry.pageType}-quick-price`)).toHaveClass(/map-filter-chip--active/);

    await page.locator(`#${entry.pageType}-filter-open-button`).click();
    await page.evaluate(() => {
      window.dash_clientside.set_props("bedrooms_slider", { value: [2, 3] });
    });
    await page.locator(`#${entry.pageType}-filter-close-button`).click({ force: true });
    await page.waitForFunction(
      (key) => JSON.stringify(window.larentals.responsiveFilters.drafts[key].bedroomsRange) ===
        JSON.stringify(window.larentals.responsiveFilters.applied[key].bedroomsRange),
      entry.pageType,
    );

    await page.locator(`#${entry.pageType}-quick-price`).click();
    await page.waitForFunction(
      (key) => JSON.stringify(window.larentals.responsiveFilters.applied[key].priceRange) ===
        JSON.stringify(window.larentals.responsiveFilters.defaults[key].priceRange),
      entry.pageType,
    );
    await expect(page.locator(`#${entry.pageType}-quick-price`)).not.toHaveClass(/map-filter-chip--active/);

    if (entry.pageType === "lease") {
      await page.evaluate(() => {
        window.dash_clientside.set_props("lease-layers-control", { overlays: ["Schools"] });
      });
      await expect(page.locator("#lease-school-layer-map-prompt")).toHaveClass(/school-layer-map-prompt--visible/);
      await page.evaluate(() => document.getElementById("lease-school-layer-show-filters-button").click());
      await expect(panel).toHaveClass(/is-open/);
      await expect(page.locator("#lease-school-layer-controls-card")).toHaveClass(/school-layer-panel-card--active/);
      await page.keyboard.press("Escape");
      await expect(page.locator("#lease-school-layer-show-filters-button")).toBeFocused();
    }

    expect(errors).toEqual([]);
  });
}

test("tablet uses a right drawer and desktop keeps a persistent sidebar", async ({ page }) => {
  const errors = await collectPageErrors(page);
  await page.setViewportSize({ width: 900, height: 1000 });
  await page.goto(BASE_URL, { waitUntil: "domcontentloaded" });
  await waitForFilterState(page, "lease");
  await expect(page.locator("[data-filter-toolbar='lease']")).toBeVisible();
  await page.locator("#lease-filter-open-button").click();
  const tabletPanel = await page.locator("[data-filter-panel='lease']").boundingBox();
  expect(tabletPanel.width).toBeGreaterThanOrEqual(430);
  expect(tabletPanel.x).toBeGreaterThanOrEqual(455);
  await page.keyboard.press("Escape");
  await expect(page.locator("#lease-filter-open-button")).toBeFocused();

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.waitForTimeout(250);
  await expect(page.locator("[data-filter-toolbar='lease']")).toBeHidden();
  const desktopPanel = await page.locator("[data-filter-panel='lease']").boundingBox();
  expect(desktopPanel.width).toBeGreaterThanOrEqual(320);
  expect(desktopPanel.width).toBeLessThanOrEqual(400);
  await expect(page.locator("[data-filter-panel='lease']")).toHaveAttribute("role", "complementary");

  expect(errors).toEqual([]);
});

test("range slider tooltips stay clear of missing-value switches", async ({ page }) => {
  await page.setViewportSize({ width: 440, height: 900 });
  await page.goto(`${BASE_URL}/buy`, { waitUntil: "domcontentloaded" });
  await waitForFilterState(page, "buy");
  await page.locator("#buy-filter-open-button").click();
  await page.getByRole("button", { name: "Lot Size", exact: true }).click();

  const slider = page.locator("#lot_size_div_buy .range-filter__slider-with-switch");
  const missingSwitch = page.locator("#lot_size_missing_switch");
  await expect(slider).toBeVisible();
  await expect(missingSwitch).toBeVisible();

  const geometry = await page.evaluate(() => {
    const tooltipBottom = Math.max(
      ...Array.from(
        document.querySelectorAll(
          "#lot_size_div_buy .range-filter__slider-with-switch .rc-slider-tooltip",
        ),
        (tooltip) => tooltip.getBoundingClientRect().bottom,
      ),
    );
    const switchTop = document
      .getElementById("lot_size_missing_switch")
      .closest(".mantine-Switch-root")
      .getBoundingClientRect().top;
    return { tooltipBottom, switchTop };
  });

  expect(geometry.switchTop).toBeGreaterThanOrEqual(geometry.tooltipBottom + 8);
});

test("ISP slider tooltips stay clear of the next control", async ({ page }) => {
  await page.setViewportSize({ width: 440, height: 900 });
  await page.goto(BASE_URL, { waitUntil: "domcontentloaded" });
  await waitForFilterState(page, "lease");
  await page.locator("#lease-filter-open-button").click();
  await page
    .getByRole("button", { name: "Internet Service Provider (ISP) Speed", exact: true })
    .click();

  const ispFilter = page.locator("#isp_speed_div");
  await expect(ispFilter).toBeVisible();

  const geometry = await page.evaluate(() => {
    const ranges = Array.from(
      document.querySelectorAll("#isp_speed_div .isp-speed-filter__range"),
    );
    const tooltipBottom = (range) => Math.max(
      ...Array.from(
        range.querySelectorAll(".rc-slider-tooltip"),
        (tooltip) => tooltip.getBoundingClientRect().bottom,
      ),
    );
    const uploadHeadingTop = ranges[1]
      .querySelector("h6")
      .getBoundingClientRect().top;
    const switchTop = document
      .getElementById("isp_speed_missing_switch")
      .closest(".mantine-Switch-root")
      .getBoundingClientRect().top;
    return {
      downloadTooltipBottom: tooltipBottom(ranges[0]),
      uploadHeadingTop,
      uploadTooltipBottom: tooltipBottom(ranges[1]),
      switchTop,
    };
  });

  expect(geometry.uploadHeadingTop).toBeGreaterThanOrEqual(
    geometry.downloadTooltipBottom + 8,
  );
  expect(geometry.switchTop).toBeGreaterThanOrEqual(
    geometry.uploadTooltipBottom + 8,
  );
});
