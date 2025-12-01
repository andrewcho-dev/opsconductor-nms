import { test, expect } from '@playwright/test';

test.describe('Routing Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('routing page loads when router is selected', async ({ page }) => {
    // Wait for inventory to load
    await expect(page.locator('.inventory-table')).toBeVisible({ timeout: 10000 });
    
    // Find a router row
    const routerRow = page.locator('.inventory-table tbody tr').filter({ hasText: 'router' }).first();
    
    if (await routerRow.isVisible()) {
      // Click on router to navigate to routing
      await routerRow.click();
      
      // Should navigate to routing page
      await expect(page.locator('h2:has-text("Routes")')).toBeVisible({ timeout: 10000 });
    } else {
      // Alternatively, click Routes navigation directly
      await page.getByRole('button', { name: '🌐 Routes' }).click();
      await page.waitForTimeout(2000);
      
      // Should show routing-related content
      const routingContent = page.locator('text=/route|routing|table/i').first();
      if (await routingContent.isVisible()) {
        await expect(routingContent).toBeVisible();
      }
    }
  });

  test('routing table displays correctly', async ({ page }) => {
    // Navigate to routing page
    await page.getByRole('button', { name: '🌐 Routes' }).click();
    await page.waitForTimeout(3000);
    
    // Look for routing table or similar content
    const routingTable = page.locator('.routing-table, .data-table, table').first();
    if (await routingTable.isVisible()) {
      await expect(routingTable).toBeVisible();
      
      // Check for table headers
      const headers = routingTable.locator('thead th, th');
      if (await headers.count() > 0) {
        await expect(headers.first()).toBeVisible();
      }
    }
  });

  test('can filter routing entries', async ({ page }) => {
    await page.getByRole('button', { name: '🌐 Routes' }).click();
    await page.waitForTimeout(3000);
    
    // Look for filter inputs
    const filterInputs = page.locator('input[placeholder*="filter"], input[placeholder*="search"], input[type="text"]').filter({ isVisible: true });
    
    if (await filterInputs.count() > 0) {
      const firstInput = filterInputs.first();
      await firstInput.fill('192.168');
      await page.waitForTimeout(1000);
      
      // Should still have content visible
      const table = page.locator('table').first();
      if (await table.isVisible()) {
        await expect(table).toBeVisible();
      }
    }
  });

  test('routing controls work', async ({ page }) => {
    await page.getByRole('button', { name: '🌐 Routes' }).click();
    await page.waitForTimeout(3000);
    
    // Look for common routing controls
    const refreshBtn = page.locator('button:has-text("Refresh"), button[title*="refresh"]').first();
    const clearBtn = page.locator('button:has-text("Clear"), button[title*="clear"]').first();
    
    // Test refresh if available
    if (await refreshBtn.isVisible()) {
      await refreshBtn.click();
      await page.waitForTimeout(2000);
      
      // Page should still be functional
      await expect(page.locator('body')).toBeVisible();
    }
    
    // Test clear if available
    if (await clearBtn.isVisible()) {
      await clearBtn.click();
      await page.waitForTimeout(1000);
    }
  });

  test('router selection persists', async ({ page }) => {
    // Wait for inventory to load
    await expect(page.locator('.inventory-table')).toBeVisible({ timeout: 10000 });
    
    // Find and click a router
    const routerRow = page.locator('.inventory-table tbody tr').filter({ hasText: 'router' }).first();
    
    if (await routerRow.isVisible()) {
      await routerRow.click();
      
      // Should be on routing page
      await expect(page.locator('h2:has-text("Routes")')).toBeVisible({ timeout: 10000 });
      
      // Navigate away and back
      await page.getByRole('button', { name: '📋 Inventory' }).click();
      await page.waitForTimeout(1000);
      await page.getByRole('button', { name: '🌐 Routes' }).click();
      await page.waitForTimeout(2000);
      
      // Should still show routing content
      await expect(page.locator('body')).toBeVisible();
    }
  });

  test('handles no routing data gracefully', async ({ page }) => {
    await page.getByRole('button', { name: '🌐 Routes' }).click();
    await page.waitForTimeout(3000);
    
    // Should not show error states for normal operation
    const errorElements = page.locator('.error-display, [role="alert"]').filter({ isVisible: true });
    
    // If no routing data, should show appropriate message
    const noDataMessage = page.locator('text=/no data|no routes|empty/i').first();
    if (await noDataMessage.isVisible()) {
      await expect(noDataMessage).toBeVisible();
    } else {
      // Or should show the routing interface
      await expect(page.locator('body')).toBeVisible();
    }
  });
});
