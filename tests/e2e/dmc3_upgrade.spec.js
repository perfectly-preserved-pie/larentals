const { test, expect } = require("@playwright/test");

/**
 * Wait for the real map and responsive filter state before exercising an input.
 * This excludes initial data hydration from assertions about later user actions.
 * @param {import('@playwright/test').Page} page Listing page under test.
 * @param {string} key Lease or buy listing mode.
 * @returns {Promise<void>} Resolves when filtering is ready.
 */
async function ready(page, key) {
  await page.waitForFunction(key => Boolean(
    window.larentals?.responsiveFilters?.defaults?.[key] &&
    Number.isFinite(window.larentals?.responsiveFilters?.appliedCounts?.[key])
  ), key);
  await expect(page.locator("#map")).toBeVisible();
}

for (const key of ["lease", "buy"]) {
  test(`${key} splitter resizes, restores widths and preserves filters across mobile`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.goto(key === "lease" ? "/" : "/buy");
    await ready(page, key);
    const filterPane = page.locator(".listing-filter-pane");
    const width = () => filterPane.evaluate(node => node.getBoundingClientRect().width);
    const handle = page.getByRole("separator", { name: "Resize filters and map", exact: true });
    await expect(handle).toBeVisible();
    const initial = await width();
    const box = await handle.boundingBox();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + 80, box.y + box.height / 2, { steps: 8 });
    await page.mouse.up();
    await expect.poll(width).toBeGreaterThan(initial + 60);
    const dragged = await width();
    await handle.focus();
    await page.keyboard.press("ArrowRight");
    await expect.poll(width).toBeGreaterThan(dragged + 5);
    const saved = await width();
    await page.reload();
    await ready(page, key);
    await expect.poll(async () => Math.abs(await width() - saved)).toBeLessThan(3);
    const maximum = key === "lease" ? "rental_price_maximum_input" : "list_price_maximum_input";
    await page.evaluate(id => window.dash_clientside.set_props(id, { value: 2500 }), maximum);
    await page.waitForFunction(key => window.larentals.responsiveFilters.applied[key]?.priceRange[1] === 2500, key);
    await page.locator(`#${key}-toggle-filters`).click();
    await expect.poll(width).toBeLessThan(1);
    await expect(page.locator(`#${key}-filter-panel`)).toHaveJSProperty("inert", true);
    await page.setViewportSize({ width: 390, height: 844 });
    await expect(handle).toBeHidden();
    await page.locator(`#${key}-filter-open-button`).click();
    await expect(page.locator(`#${key}-filter-panel`)).toHaveClass(/is-open/);
    await expect(page.locator(`#${key}-filter-panel`)).toHaveJSProperty("inert", false);
    await expect(page.locator(`#${maximum}`)).toBeVisible();
    await expect(page.locator(`#${maximum}`)).toHaveValue("$2,500");
    await page.keyboard.press("Escape");
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.locator(`#${key}-toggle-filters`).click();
    await expect.poll(width).toBeGreaterThan(280);
    await expect(page.locator(`#${maximum}`)).toHaveValue("$2,500");
    await expect.poll(() => page.evaluate(() => {
      const map = window.larentals.mapGestureControls.getMap();
      return Math.abs(map.getSize().x - map.getContainer().getBoundingClientRect().width);
    })).toBeLessThan(2);
    expect(errors).toEqual([]);
  });

  test(`${key} compresses loaded GeoJSON when another optional layer is enabled`, async ({ page }) => {
    await page.goto(key === "lease" ? "/" : "/buy");
    await ready(page, key);
    await page.locator(".layers-control-disclosure__button").click();
    const first = page.waitForResponse(response =>
      new URL(response.url()).pathname === "/_dash-update-component" &&
      response.request().headers()["content-encoding"] !== "gzip" &&
      response.request().postDataJSON()?.output?.includes("lazy-layer-geojson") &&
      response.request().postDataJSON()?.output?.includes('["ALL"]') &&
      response.request().postData()?.includes("Farmers Markets")
    );
    await page.getByRole("checkbox", { name: "Farmers Markets", exact: true }).check();
    const loaded = await first;
    expect(loaded.ok()).toBe(true);
    expect(Object.values((await loaded.json()).response).some(props => props.data?.features?.length > 0)).toBe(true);
    // This clientside status consumes the committed GeoJSON. Individual market
    // icons may all be represented by clusters at the initial county-wide zoom.
    await expect(page.locator(`#${key}-map-spinner`)).toHaveCSS("display", "none");
    const compressed = page.waitForResponse(response =>
      new URL(response.url()).pathname === "/_dash-update-component" &&
      response.request().headers()["content-encoding"] === "gzip"
    );
    await page.getByRole("checkbox", { name: "Supermarkets & Grocery Stores", exact: true }).check();
    const response = await compressed;
    expect(response.ok()).toBe(true);
    const body = await response.json();
    expect(Object.values(body.response).some(props => props.data?.features?.length > 0)).toBe(true);
  });
}

for (const mobile of [false, true]) {
  test(`location lookup shows pending, matched and partial-error states on ${mobile ? "phone" : "desktop"}`, async ({ browser }) => {
    const context = await browser.newContext({
      viewport: mobile ? { width: 390, height: 844 } : { width: 1440, height: 900 },
      isMobile: mobile, hasTouch: mobile,
    });
    const page = await context.newPage();
    let release;
    const held = new Promise(resolve => { release = resolve; });
    let first = true;
    let boundary;
    await page.route("**/_dash-update-component*", async route => {
      if (route.request().headers()["content-encoding"] === "gzip") return route.continue();
      const body = route.request().postDataJSON();
      if (!body.output?.includes("lease-zip-boundary-store.data")) return route.continue();
      const tags = body.inputs.find(input => input.id === "lease-location-input").value;
      if (!tags?.length) return route.continue();
      if (first) {
        first = false;
        await held;
        const upstream = await route.fetch();
        const json = await upstream.json();
        boundary = json.response["lease-zip-boundary-store"].data;
        return route.fulfill({ response: upstream, json });
      }
      if (!tags.includes("Atlantis")) return route.continue();
      const warning = "Could not find a California location matching 'Atlantis'.";
      const partial = tags.includes("90012");
      await route.fulfill({ json: { multi: true, response: {
        "lease-zip-boundary-store": { data: partial ? { ...boundary, warnings: [warning] } : {
          zip_codes: [], features: [], error: "place_not_found", warnings: [warning],
        } },
        "lease-location-status": { children: warning, className: "location-filter-status location-filter-status--error" },
        "lease-location-input": { error: warning, success: "" },
      } } });
    });
    try {
      await page.goto("/");
      await ready(page, "lease");
      if (mobile) await page.locator("#lease-filter-open-button").click();
      await page.evaluate(() => window.dash_clientside.set_props("lease-location-input", { value: ["90012"] }));
      await expect(page.locator(".location-tags-input .mantine-Loader-root")).toBeVisible();
      release();
      await expect(page.locator("#lease-location-status")).toHaveClass(/--success/);
      await expect(page.locator(".location-tags-input .mantine-Loader-root")).toBeHidden();
      await expect(page.locator('[data-location-kind="zip"]')).toContainText("90012");
      await page.evaluate(() => window.dash_clientside.set_props("lease-location-input", { value: ["90012", "Atlantis"] }));
      await expect(page.locator("#lease-location-status")).toContainText("Could not find");
      await expect(page.locator('[data-location-kind="place"]')).toContainText("Atlantis");
      await expect(page.locator("input#lease-location-input")).toHaveAttribute("aria-invalid", "true");
      await page.waitForFunction(() => window.larentals.responsiveFilters.drafts.lease.zipBoundary.zip_codes.includes("90012"));
      await page.getByRole("button", { name: "Remove Atlantis", exact: true }).click();
      await expect(page.locator("#lease-location-status")).toHaveClass(/--success/);
      await page.getByRole("button", { name: "Remove 90012", exact: true }).click();
      await expect(page.locator("#lease-location-status")).toBeEmpty();
      await expect(page.locator("input#lease-location-input")).not.toHaveAttribute("aria-invalid", "true");
    } finally {
      release();
      await context.close();
    }
  });
}

test("exact numeric fields select their formatted amount on focus", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await ready(page, "lease");
  const input = page.locator("#rental_price_maximum_input");
  await input.fill("3000");
  await page.locator("#rental_price_minimum_input").focus();
  await input.focus();
  expect(await input.evaluate(node => [node.selectionStart, node.selectionEnd])).toEqual([0, 6]);
  await page.keyboard.type("2500");
  await expect(input).toHaveValue("$2,500");
});

test("location loading remains active through the resolved map update", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await ready(page, "lease");
  await page.evaluate(() => {
    const callbacks = window.dash_clientside.clientside;
    const apply = callbacks.applyLeaseFilterState;
    callbacks.applyLeaseFilterState = async (state, geojson) => {
      if (state?.zipBoundary?.zip_codes?.includes("90012")) {
        window.__locationMapApplyStarted = true;
        await new Promise(resolve => window.setTimeout(resolve, 900));
      }
      return apply(state, geojson);
    };
  });
  await page.evaluate(() => window.dash_clientside.set_props("lease-location-input", { value: ["90012"] }));
  const fieldLoader = page.locator(".location-tags-input .mantine-Loader-root");
  const statusLoader = page.locator("#lease-location-resolving-status");
  await expect(fieldLoader).toBeVisible();
  await expect(statusLoader).toBeVisible();
  await page.waitForFunction(() => window.__locationMapApplyStarted === true);
  await expect(page.locator("#lease-location-status")).toContainText("Filtering by ZIP codes");
  await page.waitForTimeout(250);
  await expect(fieldLoader).toBeVisible();
  await expect(statusLoader).toBeVisible();
  await expect(fieldLoader).toBeHidden({ timeout: 5000 });
  await expect(statusLoader).toBeHidden();
  await page.waitForFunction(() => window.larentals.responsiveFilters.applied.lease.zipBoundary.zip_codes.includes("90012"));
});

test("phone amount entry replaces budget, square footage and deposit bounds", async ({ browser }) => {
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true,
  });
  const page = await context.newPage();
  try {
    await page.goto("/");
    await ready(page, "lease");
    await page.locator("#lease-filter-open-button").tap();
    for (const [section, id, expected] of [
      ["Monthly Rent", "rental_price", "$2,500"],
      ["Square Footage", "sqft", "2,500 sq ft"],
      ["Deposits", "security_deposit", "$2,500"],
    ]) {
      const heading = page.getByRole("button", { name: section, exact: true });
      if (await heading.getAttribute("aria-expanded") !== "true") await heading.tap();
      const input = page.locator(`#${id}_maximum_input`);
      await input.fill("3000");
      await page.locator(`#${id}_minimum_input`).tap();
      await input.tap();
      expect(await input.evaluate(node => node.selectionEnd - node.selectionStart)).toBeGreaterThan(4);
      await page.keyboard.type("2500");
      await expect(input).toHaveValue(expected);
    }
    const footer = await page.locator(".responsive-filter-panel__footer").boundingBox();
    expect(footer.y + footer.height).toBeLessThanOrEqual(845);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  } finally {
    await context.close();
  }
});
