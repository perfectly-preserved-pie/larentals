const { test, expect } = require("@playwright/test");

test("location suggestions and Add button accept multiple places", async ({ page }) => {
  await page.goto("/", { waitUntil: "networkidle" });

  const control = page.locator(".location-tags-input").first();
  const input = page.locator(
    ".location-tags-input input#lease-location-input, " +
    ".location-tags-input#lease-location-input input"
  ).first();
  await expect(input).toBeVisible();
  await expect(input).toHaveAttribute("enterkeyhint", "done");
  await expect(input).not.toHaveAttribute("inputprops");
  await expect(input).toHaveAttribute(
    "placeholder",
    "Search neighborhoods, cities, or ZIPs"
  );
  await expect(page.locator("#lease-location-add-button")).toBeHidden();
  await expect(page.locator(".location-entry-help--desktop").first()).toBeVisible();
  await expect(page.locator("#lease-location-status")).toHaveAttribute("role", "status");
  await expect(page.locator("#lease-location-status")).toHaveAttribute("aria-live", "polite");

  await input.fill("Silver Lake");
  const silverLakeOption = page.getByRole("option", {
    name: "Silver Lake, CA",
    exact: true,
  });
  await expect(silverLakeOption).toBeVisible();
  await input.press("Escape");
  await expect(silverLakeOption).toBeHidden();
  await expect(input).toHaveValue("Silver Lake");
  await input.press("ArrowDown");
  await expect(silverLakeOption).toBeVisible();
  await input.press("Enter");
  await expect(control).toContainText("Silver Lake, CA");

  await input.pressSequentially("Pasadena, CA");
  await expect(control.locator(".mantine-TagsInput-pill")).toHaveCount(1);
  await input.press("Enter");
  await expect(control).toContainText("Pasadena, CA");
  await expect(input).toHaveValue("");
  await input.pressSequentially("Glendale");
  await input.press("Enter");
  await expect(control).toContainText("Glendale");
  await expect(input).toHaveValue("");
  await expect(control.locator(".mantine-TagsInput-pill")).toHaveCount(3);
  await expect(
    control.locator(".mantine-TagsInput-pill button").first()
  ).toHaveAttribute("aria-label", "Remove Silver Lake, CA");

  await expect(control).toContainText("Pasadena, CA");
  await expect(control).toContainText("Glendale");
  await expect(page.locator("#lease-location-status")).toContainText(
    "Filtering by ZIP codes",
    { timeout: 15_000 }
  );

  const moreZipCodes = page
    .locator("#lease-location-status .location-zip-more-button")
    .first();
  await expect(moreZipCodes).toHaveText(/\+\d+ more/);
  await expect(moreZipCodes).toHaveAttribute(
    "aria-label",
    /Show \d+ additional ZIP codes/
  );
  await moreZipCodes.click();
  const zipPopover = page.locator(".location-zip-popover").first();
  await expect(zipPopover).toBeVisible();
  await expect(zipPopover.locator("[role='listitem']").first()).toHaveText(
    /^\d{5}$/
  );

  await page.evaluate(() => {
    document.documentElement.setAttribute("data-mantine-color-scheme", "dark");
  });
  const darkInputStyle = await input.evaluate((element) => {
    const style = getComputedStyle(element);
    return {
      background: style.backgroundColor,
      borderWidth: style.borderWidth,
      boxShadow: style.boxShadow,
      minHeight: style.minHeight,
      padding: style.padding,
    };
  });
  expect(darkInputStyle).toEqual({
    background: "rgba(0, 0, 0, 0)",
    borderWidth: "0px",
    boxShadow: "none",
    minHeight: "24px",
    padding: "0px",
  });
});

test("location instructions match the mobile keyboard action", async ({ browser }) => {
  const context = await browser.newContext({
    hasTouch: true,
    isMobile: true,
    viewport: { width: 390, height: 844 },
  });
  const page = await context.newPage();
  await page.goto("/", { waitUntil: "networkidle" });

  await page.locator("#lease-filter-open-button").tap();
  await expect(page.locator("#lease-filter-panel")).toHaveClass(/is-open/);

  const control = page.locator(".location-tags-input").first();
  const input = page.locator(
    ".location-tags-input input#lease-location-input, " +
    ".location-tags-input#lease-location-input input"
  ).first();
  await expect(input).toHaveAttribute("enterkeyhint", "done");
  await expect(input).toHaveAttribute(
    "placeholder",
    "Search neighborhoods, cities, or ZIPs"
  );
  await expect(page.locator("#lease-location-add-button")).toBeVisible();
  await expect(page.locator(".location-entry-help--touch").first()).toBeVisible();

  await input.fill("Silver Lake");
  const suggestion = page.getByRole("option", {
    name: "Silver Lake, CA",
    exact: true,
  });
  await expect(suggestion).toBeVisible();
  await suggestion.tap();
  await expect(control).toContainText("Silver Lake, CA");
  await expect(input).toHaveValue("");

  await input.fill("Pasadena, CA");
  await page.locator("#lease-location-add-button").tap();
  await expect(control).toContainText("Pasadena, CA");
  await expect(input).toHaveValue("");
  await input.fill("Glendale");
  await page.locator("#lease-location-add-button").tap();
  await expect(control).toContainText("Glendale");
  await expect(input).toHaveValue("");
  const firstRemoveButton = control
    .locator(".mantine-TagsInput-pill button")
    .first();
  await expect(firstRemoveButton).toHaveAttribute("aria-label", "Remove Silver Lake, CA");
  const removeTargetSize = await firstRemoveButton.evaluate((element) => {
    const bounds = element.getBoundingClientRect();
    return { width: bounds.width, height: bounds.height };
  });
  expect(removeTargetSize.width).toBeGreaterThanOrEqual(24);
  expect(removeTargetSize.height).toBeGreaterThanOrEqual(24);

  const moreZipCodes = page.locator(
    "#lease-location-status .location-zip-more-button"
  );
  await expect(moreZipCodes).toBeVisible({ timeout: 15_000 });
  await moreZipCodes.tap();

  const zipPopover = page.locator(".location-zip-popover").first();
  await expect(zipPopover).toBeVisible();
  const popoverIsTopmost = await zipPopover.evaluate((element) => {
    const bounds = element.getBoundingClientRect();
    const center = document.elementFromPoint(
      bounds.left + bounds.width / 2,
      bounds.top + Math.min(bounds.height / 2, 40)
    );
    return element === center || element.contains(center);
  });
  expect(popoverIsTopmost).toBe(true);

  await context.close();
});
