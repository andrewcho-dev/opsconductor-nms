import { test, expect, Page } from '@playwright/test';

const waitForInventory = async (page: Page) => {
  await page.goto('/');
  await expect(page.getByRole('button', { name: 'Inventory' })).toBeVisible();
  await expect(page.locator('.inventory-table')).toBeVisible();
};

test('home page renders inventory grid', async ({ page }) => {
  await waitForInventory(page);
  await expect(page.locator('.inventory-table tbody tr').first()).toBeVisible();
});

test('router clicking navigates to routing page', async ({ page }) => {
  await page.goto('http://10.120.0.18:3000');

  // Wait for InventoryGrid to load
  await page.waitForTimeout(10000);

  // Check if we're on inventory page with the table
  await expect(page.locator('.inventory-table')).toBeVisible({ timeout: 10000 });
  
  // Find a router row (look for a row with router type)
  const routerRow = page.locator('.inventory-table tbody tr').filter({ hasText: 'router' }).first();
  await expect(routerRow).toBeVisible();
  
  // Click the router row
  await routerRow.click();
  
  // Should navigate to routing page
  await expect(page.locator('h2:has-text("Routes")')).toBeVisible({ timeout: 10000 });
});
