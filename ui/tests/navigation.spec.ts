import { test, expect } from '@playwright/test';

test.describe('Navigation', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('all navigation buttons are present and clickable', async ({ page }) => {
    // Check all navigation buttons exist
    await expect(page.getByRole('button', { name: '📋 Inventory' })).toBeVisible();
    await expect(page.getByRole('button', { name: '🌐 Routes' })).toBeVisible();
    await expect(page.getByRole('button', { name: '📊 Tables' })).toBeVisible();
    await expect(page.getByRole('button', { name: '⚙️ Admin' })).toBeVisible();
  });

  test('navigation highlights current page', async ({ page }) => {
    // Inventory should be highlighted by default
    const inventoryBtn = page.getByRole('button', { name: '📋 Inventory' });
    await expect(inventoryBtn).toHaveCSS('background-color', 'rgb(59, 130, 246)');

    // Click Routes and check it's highlighted
    await page.getByRole('button', { name: '🌐 Routes' }).click();
    await expect(page.getByRole('button', { name: '🌐 Routes' })).toHaveCSS('background-color', 'rgb(59, 130, 246)');
    await expect(inventoryBtn).toHaveCSS('background-color', 'rgba(0, 0, 0, 0)');

    // Click Tables and check it's highlighted
    await page.getByRole('button', { name: '📊 Tables' }).click();
    await expect(page.getByRole('button', { name: '📊 Tables' })).toHaveCSS('background-color', 'rgb(59, 130, 246)');

    // Click Admin and check it's highlighted
    await page.getByRole('button', { name: '⚙️ Admin' }).click();
    await expect(page.getByRole('button', { name: '⚙️ Admin' })).toHaveCSS('background-color', 'rgb(59, 130, 246)');
  });

  test('URL updates when navigating', async ({ page }) => {
    // Default should be /inventory
    await expect(page).toHaveURL(/.*\/inventory/);

    await page.getByRole('button', { name: '🌐 Routes' }).click();
    await expect(page).toHaveURL(/.*\/routing/);

    await page.getByRole('button', { name: '📊 Tables' }).click();
    await expect(page).toHaveURL(/.*\/tables/);

    await page.getByRole('button', { name: '⚙️ Admin' }).click();
    await expect(page).toHaveURL(/.*\/admin/);
  });
});
