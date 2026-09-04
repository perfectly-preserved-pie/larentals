const { test, expect } = require("@playwright/test");

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || "http://127.0.0.1:8050";

for (const mode of ["lease", "buy"]) {
  for (const viewport of [
    { width: 320, height: 700 },
    { width: 390, height: 844 },
    { width: 844, height: 390 },
    { width: 900, height: 1000 },
    { width: 1100, height: 800 },
    { width: 1440, height: 900 },
  ]) {
    test(`${mode} datepicker fits and selects dates at ${viewport.width}x${viewport.height}`, async ({ page }) => {
      await page.setViewportSize(viewport);
      await page.goto(`${BASE_URL}${mode === "buy" ? "/buy" : "/"}`);
      await page.waitForFunction(
        (key) => Number.isFinite(window.larentals?.responsiveFilters?.appliedCounts?.[key]),
        mode,
      );
      if (viewport.width < 1100) {
        await page.locator(`#${mode}-filter-open-button`).click();
      }
      // Wait for the responsive accordion defaults and sheet transition.
      await page.waitForTimeout(700);
      const heading = page.getByRole("button", { name: "Listed Date", exact: true });
      if (await heading.getAttribute("aria-expanded") !== "true") await heading.click();
      const filter = page.locator(".listed-date-filter");
      await filter.locator(".dash-datepicker-start-date").click();
      const calendar = filter.locator(".dash-datepicker-content");
      await expect(calendar).toBeVisible();
      const body = page.locator(".responsive-filter-panel__body");
      const geometry = await body.evaluate((el) => {
        const calendar = el.querySelector(".dash-datepicker-content");
        return {
          bodyWidth: el.clientWidth,
          bodyScrollWidth: el.scrollWidth,
          calendarWidth: calendar.clientWidth,
          calendarScrollWidth: calendar.scrollWidth,
        };
      });
      expect(geometry.bodyScrollWidth).toBeLessThanOrEqual(geometry.bodyWidth + 1);
      expect(geometry.calendarScrollWidth).toBeLessThanOrEqual(geometry.calendarWidth + 1);

      await calendar.getByRole("button", { name: "Previous month", exact: true }).click();

      // Every calendar button, including the last week and navigation, must be
      // reachable inside the scroll area and unobscured by the map or footer.
      const buttons = calendar.locator("button:visible, .dash-datepicker-calendar-date-inside");
      for (const button of await buttons.all()) {
        await button.scrollIntoViewIfNeeded();
        expect(await button.evaluate((el) => {
          const box = el.getBoundingClientRect();
          const hit = document.elementFromPoint(box.x + box.width / 2, box.y + box.height / 2);
          return el === hit || el.contains(hit);
        })).toBe(true);
      }
      const day = (number) => calendar.locator(".dash-datepicker-calendar-date-inside")
        .filter({ hasText: new RegExp(`^${number}$`) });
      await day(1).click();
      await day(10).click();
      await expect(calendar).toBeHidden();
      await expect(filter.locator(".dash-datepicker-start-date")).toHaveValue(/-01$/);
      await expect(filter.locator(".dash-datepicker-end-date")).toHaveValue(/-10$/);
      await page.waitForFunction((key) => {
        const draft = window.larentals.responsiveFilters.drafts[key];
        return draft.dateStart?.endsWith("-01") && draft.dateEnd?.endsWith("-10");
      }, mode);
    });
  }
}
