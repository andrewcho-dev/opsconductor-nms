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

test('tables view renders datatable explorer', async ({ page }) => {
  await waitForInventory(page);
  await page.getByRole('button', { name: /Tables/ }).click();
  await expect(page.locator('.table-explorer')).toBeVisible();
  await expect(page.locator('.data-table')).toBeVisible();
});
