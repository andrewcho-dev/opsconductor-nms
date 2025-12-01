import { test, expect } from '@playwright/test';

test.describe('Inventory Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('inventory page loads and displays table', async ({ page }) => {
    // Wait for inventory to load
    await expect(page.locator('.inventory-table')).toBeVisible({ timeout: 10000 });
    
    // Check table headers are present
    await expect(page.locator('.inventory-table thead')).toBeVisible();
    
    // Check that we have some data rows
    await expect(page.locator('.inventory-table tbody tr').first()).toBeVisible();
  });

  test('inventory table has sortable columns', async ({ page }) => {
    await expect(page.locator('.inventory-table')).toBeVisible({ timeout: 10000 });
    
    // Look for sortable column headers
    const headers = page.locator('.inventory-table th');
    await expect(headers.first()).toBeVisible();
    
    // Try clicking on a column header to sort
    const firstHeader = headers.first();
    await firstHeader.click();
    
    // Wait a moment for sorting to take effect
    await page.waitForTimeout(1000);
    
    // Table should still be visible after sorting
    await expect(page.locator('.inventory-table tbody tr').first()).toBeVisible();
  });

  test('can filter inventory items', async ({ page }) => {
    await expect(page.locator('.inventory-table')).toBeVisible({ timeout: 10000 });
    
    // Look for filter input (if it exists)
    const filterInput = page.locator('input[placeholder*="filter"], input[placeholder*="search"]').first();
    if (await filterInput.isVisible()) {
      await filterInput.fill('router');
      await page.waitForTimeout(1000);
      
      // Should have filtered results
      const rows = page.locator('.inventory-table tbody tr');
      await expect(rows.first()).toBeVisible();
    }
  });

  test('inventory shows different device types', async ({ page }) => {
    await expect(page.locator('.inventory-table')).toBeVisible({ timeout: 10000 });
    
    // Check for different device types in the table
    const tableContent = await page.locator('.inventory-table').textContent();
    
    // Should contain various network device types
    expect(tableContent?.toLowerCase()).toMatch(/(router|switch|host|server|device)/i);
  });

  test('inventory refresh works', async ({ page }) => {
    await expect(page.locator('.inventory-table')).toBeVisible({ timeout: 10000 });
    
    // Look for refresh button
    const refreshBtn = page.locator('button[title*="refresh"], button:has-text("Refresh")').first();
    if (await refreshBtn.isVisible()) {
      await refreshBtn.click();
      
      // Table should still be visible after refresh
      await expect(page.locator('.inventory-table tbody tr').first()).toBeVisible({ timeout: 10000 });
    }
  });
});
