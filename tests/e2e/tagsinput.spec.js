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

  const input = page.locator(
    ".location-tags-input input#lease-location-input, " +
    ".location-tags-input#lease-location-input input"
  ).first();
  await expect(input).toHaveAttribute("enterkeyhint", "next");
  await expect(input).toHaveAttribute(
    "placeholder",
    "Type a location, then tap Next"
  );

  await context.close();
});
