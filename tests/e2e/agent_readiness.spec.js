const { test, expect } = require('@playwright/test');

for (const path of ['/', '/buy', '/mcp', '/developers', '/about', '/contact', '/privacy']) {
  test(`readable without JavaScript: ${path}`, async ({ browser }) => {
    const context = await browser.newContext({ javaScriptEnabled: false });
    const page = await context.newPage();
    const response = await page.goto(`http://127.0.0.1:8050${path}`);
    expect(response.status()).toBe(200);
    await expect(page.locator('main h1')).toBeVisible();
    expect((await page.locator('main').innerText()).length).toBeGreaterThan(500);
    await expect(page.locator('a[href="/developers"]')).toBeVisible();
    await expect(page.locator('meta[property="og:image"]')).toHaveCount(1);
    await context.close();
  });
}

for (const path of ['/', '/buy']) {
  test(`map replaces fallback and keeps developer access: ${path}`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(path);
    await expect(page.locator('#map')).toBeVisible({ timeout: 30000 });
    await expect(page.locator('#public-content')).toHaveCount(0);
    const link = page.getByRole('link', { name: 'Developers', exact: true });
    await expect(page.locator('.title-card-links a[href="/mcp"]')).toHaveCount(0);
    await expect(link).toBeVisible();
    await link.click();
    await expect(page.locator('h1')).toHaveText('WhereToLive.LA developer guide and public API');
    await page.getByRole('button', { name: 'Search JSON' }).click();
    const result = JSON.parse(await page.locator('body').innerText());
    expect(result.listing_type).toBe('lease');
    expect(result.page_size).toBe(5);
  });
}


test('developer resources link to REST, CLI, and existing MCP setup', async ({ page }) => {
  await page.goto('/developers');
  const resources = page.getByRole('navigation', { name: 'Developer resources' });
  await resources.getByRole('link', { name: 'REST API', exact: true }).click();
  await expect(page).toHaveURL(/\/developers#rest-api$/);
  await expect(page.locator('#rest-api h2')).toHaveText('REST API');
  await resources.getByRole('link', { name: 'CLI', exact: true }).click();
  await expect(page).toHaveURL(/\/developers#cli$/);
  await expect(page.locator('#cli h2')).toHaveText('CLI');
  await resources.getByRole('link', { name: 'MCP', exact: true }).click();
  await expect(page.locator('.mcp-docs')).toBeVisible({ timeout: 30000 });
  await expect(page).toHaveURL(/\/mcp$/);
  await expect(page.locator('.mcp-docs__endpoint-value')).toContainText('https://wheretolive.la/_mcp');
  await page.getByRole('link', { name: 'Developers', exact: true }).click();
  await expect(page).toHaveURL(/\/developers$/);
  await expect(page.getByRole('navigation', { name: 'Developer resources' })).toBeVisible();
});
