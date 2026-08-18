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
  {
    pageType: "lease",
    path: "/",
    maximumInputId: "rental_price_maximum_input",
  },
  {
    pageType: "buy",
    path: "/buy",
    maximumInputId: "list_price_maximum_input",
  },
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

    await page.evaluate(({ maximumInputId, upper }) => {
      window.dash_clientside.set_props(maximumInputId, { value: upper });
    }, {
      maximumInputId: entry.maximumInputId,
      upper: Math.max(1, Math.round(initial.defaults.priceUpperBound * 0.55)),
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
    await page.waitForFunction(
      (key) => JSON.stringify(window.larentals.responsiveFilters.drafts[key].bedroomsRange) ===
        JSON.stringify([2, 3]),
      entry.pageType,
    );
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

test("mobile location drafts do not cover the map with a loading overlay", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const errors = await collectPageErrors(page);
  await page.goto(BASE_URL, { waitUntil: "domcontentloaded" });
  await waitForFilterState(page, "lease");

  const spinner = page.locator("#lease-map-spinner");
  await expect(spinner).toHaveCSS("display", "none");
  await page.locator("#lease-filter-open-button").click();

  const nearbySwitch = page.locator("#lease-nearby-zip-switch");
  await nearbySwitch.click();
  await page.waitForFunction(
    () => window.larentals.responsiveFilters.drafts.lease.nearbyZip === true,
  );
  await expect(spinner).toHaveCSS("display", "none");
  await nearbySwitch.click();

  const input = page.locator("input#lease-location-input");
  await input.fill("Downey");
  await input.press("Enter");
  await page.waitForFunction(() => {
    const draft = window.larentals?.responsiveFilters?.drafts?.lease;
    return JSON.stringify(draft?.locationText) === JSON.stringify(["Downey"]) &&
      Array.isArray(draft?.zipBoundary?.zip_codes) &&
      draft.zipBoundary.zip_codes.includes("90240");
  });

  await expect(spinner).toHaveCSS("display", "none");
  const stagedState = await page.evaluate(() => ({
    draft: window.larentals.responsiveFilters.drafts.lease.locationText,
    applied: window.larentals.responsiveFilters.applied.lease.locationText,
  }));
  expect(stagedState).toEqual({ draft: ["Downey"], applied: [] });

  await page.evaluate(() => document.getElementById("lease-filter-apply-button").click());
  await page.waitForFunction(
    () => JSON.stringify(window.larentals?.responsiveFilters?.applied?.lease?.locationText) ===
      JSON.stringify(["Downey"]),
  );
  await expect(spinner).toHaveCSS("display", "none");
  await expect(page.locator("#lease-quick-location")).toHaveClass(/map-filter-chip--active/);
  expect(errors).toEqual([]);
});

test("hybrid ranges keep exact and unbounded outlier filtering", async ({ page }) => {
  await page.goto(BASE_URL, { waitUntil: "domcontentloaded" });
  await waitForFilterState(page, "lease");
  await page.getByText("Deposits", { exact: true }).click();
  const securityMarks = page.locator("#security_deposit_slider .dash-slider-mark");
  await expect(securityMarks).toHaveCount(3);
  await expect(securityMarks).toHaveText(["$0", "$5k", "$10k"]);
  await expect(page.locator("#security_deposit_slider")).not.toContainText("Unlimited");

  const securityMinimum = page.locator("input#security_deposit_minimum_input");
  const securityMaximum = page.locator("input#security_deposit_maximum_input");
  const securityMinimumClear = page.locator("#security_deposit_minimum_clear");
  const securityUnlimited = page.locator("#security_deposit_maximum_clear");
  await expect(securityMinimum).toHaveValue("$0");
  await expect(securityMinimumClear).toBeHidden();
  await expect(securityMaximum).toHaveValue("");
  await expect(securityMaximum).toHaveAttribute("placeholder", "Unlimited");
  await expect(securityUnlimited).toBeHidden();
  await expect(
    page.locator('#security_deposit_slider .dash-slider-thumb[aria-label="Maximum"]'),
  ).toHaveAttribute("aria-valuemax", "10000");

  await securityMaximum.fill("675000");
  await securityMaximum.press("Tab");
  await page.waitForFunction(
    () => JSON.stringify(window.larentals.responsiveFilters.drafts.lease.securityRange) ===
      JSON.stringify([0, 675000]),
  );
  await expect(securityMaximum).toHaveValue("$675,000");
  await expect(securityUnlimited).toBeVisible();
  await expect(securityUnlimited).toHaveAttribute(
    "aria-label",
    "Set maximum to unlimited",
  );
  await expect(
    page.locator('#security_deposit_slider .dash-slider-thumb[aria-label="Maximum"]'),
  ).toHaveAttribute("aria-valuenow", "10000");

  await securityUnlimited.focus();
  await page.keyboard.press("Enter");
  await page.waitForFunction(
    () => window.larentals.responsiveFilters.drafts.lease.securityRange[1] === null,
  );
  await expect(securityMaximum).toHaveValue("");
  await expect(securityUnlimited).toBeHidden();

  const securityDisplayMaximum = await page.evaluate(
    () => window.larentals.responsiveFilters.defaults.lease.securityUpperBound,
  );
  await page.evaluate((upper) => {
    window.dash_clientside.set_props("security_deposit_slider", {
      value: [1000, upper],
    });
  }, securityDisplayMaximum);
  await page.waitForFunction(
    () => JSON.stringify(window.larentals.responsiveFilters.drafts.lease.securityRange) ===
      JSON.stringify([1000, null]),
  );
  await expect(securityMinimum).toHaveValue("$1,000");
  await expect(securityMaximum).toHaveValue("");
  await expect(securityMinimumClear).toBeVisible();
  await expect(securityMinimumClear).toHaveAttribute(
    "aria-label",
    "Reset minimum to zero",
  );

  await securityMinimumClear.focus();
  await page.keyboard.press("Enter");
  await page.waitForFunction(
    () => window.larentals.responsiveFilters.drafts.lease.securityRange[0] === 0,
  );
  await expect(securityMinimum).toHaveValue("$0");
  await expect(securityMinimumClear).toBeHidden();
  await expect(securityMaximum).toHaveValue("");

  await page.evaluate((upper) => {
    window.dash_clientside.set_props("security_deposit_slider", {
      value: [1000, upper / 2],
    });
  }, securityDisplayMaximum);
  await page.waitForFunction(
    (upper) => JSON.stringify(window.larentals.responsiveFilters.drafts.lease.securityRange) ===
      JSON.stringify([1000, upper / 2]),
    securityDisplayMaximum,
  );
  await expect(securityMaximum).toHaveValue("$5,000");
  await expect(securityUnlimited).toBeVisible();

  const leaseResult = await page.evaluate(() => {
    const defaults = structuredClone(window.larentals.responsiveFilters.defaults.lease);
    Object.assign(defaults, {
      pets: "Both",
      sqftMissing: true,
      ppsqftMissing: true,
      parkingMissing: true,
      yearMissing: true,
      terms: [],
      termsMissing: true,
      furnished: [],
      furnishedMissing: true,
      securityMissing: false,
      petDepositMissing: true,
      keyDepositMissing: true,
      otherDepositMissing: true,
      laundry: [],
      laundryMissing: true,
      subtypes: [],
      dateMissing: true,
      ispMissing: true,
      rentControl: "any",
      zipBoundary: {},
    });
    const feature = {
      type: "Feature",
      geometry: null,
      properties: {
        mls_number: "capped-lease-test",
        list_price: defaults.priceRange[0],
        bedrooms: 15,
        total_bathrooms: 12,
        sqft: null,
        ppsqft: null,
        parking_spaces: null,
        year_built: null,
        terms: null,
        furnished: null,
        security_deposit: 675000,
        pet_deposit: null,
        key_deposit: null,
        other_deposit: null,
        laundry_category: null,
        listed_date: null,
        best_dn: null,
        best_up: null,
      },
    };
    const source = { type: "FeatureCollection", features: [feature] };
    const withoutMaximum = window.larentals.filters.filterLeaseState(defaults, source).features.length;
    defaults.securityRange = [0, defaults.securityUpperBound];
    const atDisplayCap = window.larentals.filters.filterLeaseState(defaults, source).features.length;
    defaults.securityRange = [0, 675000];
    const atExactMaximum = window.larentals.filters.filterLeaseState(defaults, source).features.length;
    return { withoutMaximum, atDisplayCap, atExactMaximum };
  });

  expect(leaseResult).toEqual({ withoutMaximum: 1, atDisplayCap: 0, atExactMaximum: 1 });

  await page.goto(`${BASE_URL}/buy`, { waitUntil: "domcontentloaded" });
  await waitForFilterState(page, "buy");
  const bedroomMarks = page.locator("#bedrooms_slider .dash-slider-mark");
  await expect(bedroomMarks).toHaveCount(7);
  await expect(bedroomMarks.nth(5)).toHaveText("5");
  await expect(bedroomMarks.last()).toHaveText("Unlimited");
  await expect(bedroomMarks.last()).toBeVisible();
  await expect(
    page.locator('#bedrooms_slider .dash-slider-thumb[aria-label="Maximum"] .dash-slider-tooltip'),
  ).toBeHidden();
  const bedroomEndpointGeometry = await page.evaluate(() => {
    const label = document.querySelector(
      "#bedrooms_slider .dash-slider-mark:last-of-type",
    ).getBoundingClientRect();
    const exactCap = document.querySelector(
      "#bedrooms_slider .dash-slider-mark:nth-last-of-type(2)",
    ).getBoundingClientRect();
    const maximumThumb = document.querySelector(
      '#bedrooms_slider .dash-slider-thumb[aria-label="Maximum"]',
    ).getBoundingClientRect();
    const filter = document.getElementById("bedrooms_div_buy").getBoundingClientRect();
    return {
      labelLeft: label.left,
      labelRight: label.right,
      labelCenter: label.left + label.width / 2,
      exactCapRight: exactCap.right,
      thumbCenter: maximumThumb.left + maximumThumb.width / 2,
      filterRight: filter.right,
    };
  });
  expect(Math.abs(
    bedroomEndpointGeometry.labelCenter - bedroomEndpointGeometry.thumbCenter,
  )).toBeLessThanOrEqual(1);
  expect(bedroomEndpointGeometry.exactCapRight + 4).toBeLessThanOrEqual(
    bedroomEndpointGeometry.labelLeft,
  );
  expect(bedroomEndpointGeometry.labelRight).toBeLessThanOrEqual(
    bedroomEndpointGeometry.filterRight + 1,
  );
  await expect(page.locator("#sqft_slider")).toContainText("2.5k");
  await expect(page.locator("#sqft_slider")).not.toContainText("Unlimited");
  await expect(page.locator("#lot_size_slider")).toContainText("12.5k");
  await expect(page.locator("#lot_size_slider")).not.toContainText("Unlimited");
  await expect(page.locator("input#sqft_maximum_input")).toHaveAttribute(
    "placeholder",
    "Unlimited",
  );

  const buyResult = await page.evaluate(() => {
    const defaults = structuredClone(window.larentals.responsiveFilters.defaults.buy);
    Object.assign(defaults, {
      sqftMissing: true,
      ppsqftMissing: true,
      lotSizeMissing: true,
      yearMissing: true,
      subtypes: [],
      dateMissing: true,
      hoaMissing: true,
      hoaFrequency: [],
      ispMissing: true,
      zipBoundary: {},
    });
    const outlierPrice = defaults.priceUpperBound * 10;
    const feature = {
      type: "Feature",
      geometry: null,
      properties: {
        mls_number: "capped-buy-test",
        list_price: outlierPrice,
        bedrooms: 15,
        total_bathrooms: 12,
        sqft: null,
        ppsqft: null,
        lot_size: null,
        year_built: null,
        hoa_fee: null,
        listed_date: null,
        best_dn: null,
        best_up: null,
      },
    };
    const source = { type: "FeatureCollection", features: [feature] };
    const withoutMaximum = window.larentals.filters.filterBuyState(defaults, source).features.length;
    defaults.priceRange = [0, defaults.priceUpperBound];
    const atDisplayCap = window.larentals.filters.filterBuyState(defaults, source).features.length;
    defaults.priceRange = [0, outlierPrice];
    const atExactMaximum = window.larentals.filters.filterBuyState(defaults, source).features.length;
    defaults.bedroomsRange = [0, defaults.bedroomsUpperBound - 1];
    const belowDiscreteSentinel = window.larentals.filters.filterBuyState(defaults, source).features.length;
    return { withoutMaximum, atDisplayCap, atExactMaximum, belowDiscreteSentinel };
  });

  expect(buyResult).toEqual({
    withoutMaximum: 1,
    atDisplayCap: 0,
    atExactMaximum: 1,
    belowDiscreteSentinel: 0,
  });
});

test("hybrid range fields and marks stay clear of missing-value switches", async ({ page }) => {
  await page.setViewportSize({ width: 440, height: 900 });
  await page.goto(`${BASE_URL}/buy`, { waitUntil: "domcontentloaded" });
  await waitForFilterState(page, "buy");
  await page.locator("#buy-filter-open-button").click();
  await page.getByRole("button", { name: "Lot Size", exact: true }).click();

  const exactInputs = page.locator("#lot_size_div_buy .range-filter__exact-inputs");
  const slider = page.locator("#lot_size_div_buy .range-filter__hybrid-slider-wrap");
  const missingSwitch = page.locator("#lot_size_missing_switch");
  await expect(exactInputs).toBeVisible();
  await expect(slider).toBeVisible();
  await expect(missingSwitch).toBeVisible();

  const geometry = await page.evaluate(() => {
    const marksBottom = Math.max(
      ...Array.from(
        document.querySelectorAll(
          "#lot_size_div_buy .range-filter__hybrid-slider-wrap .dash-slider-mark",
        ),
        (mark) => mark.getBoundingClientRect().bottom,
      ),
    );
    const switchTop = document
      .getElementById("lot_size_missing_switch")
      .closest(".mantine-Switch-root")
      .getBoundingClientRect().top;
    return { marksBottom, switchTop };
  });

  expect(geometry.switchTop).toBeGreaterThanOrEqual(geometry.marksBottom + 8);
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
