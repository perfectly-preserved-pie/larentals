const { test, expect } = require("@playwright/test");

test("location tags preserve commas and accept multiple places", async ({ page }) => {
  await page.goto("/", { waitUntil: "networkidle" });

  const control = page.locator(".location-tags-input").first();
  const input = page.locator(
    ".location-tags-input input#lease-location-input, " +
    ".location-tags-input#lease-location-input input"
  ).first();
  await expect(input).toBeVisible();
  await expect(input).toHaveAttribute("enterkeyhint", "next");
  await expect(input).not.toHaveAttribute("inputprops");
  await expect(input).toHaveAttribute(
    "placeholder",
    "Type a location, then press Enter"
  );

  await input.pressSequentially("Pasadena, CA");
  await expect(control.locator(".mantine-TagsInput-pill")).toHaveCount(0);
  await input.press("Enter");
  await expect(input).toHaveAttribute(
    "placeholder",
    "Type another location, then press Enter"
  );
  await input.pressSequentially("Glendale");
  await input.press("Enter");

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

  const input = page.locator(
    ".location-tags-input input#lease-location-input, " +
    ".location-tags-input#lease-location-input input"
  ).first();
  await expect(input).toHaveAttribute("enterkeyhint", "next");
  await expect(input).toHaveAttribute(
    "placeholder",
    "Type a location, then tap Next"
  );

  await input.fill("Pasadena, CA");
  await input.press("Enter");
  await input.fill("Glendale");
  await input.press("Enter");

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
