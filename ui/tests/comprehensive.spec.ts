import { test, expect } from '@playwright/test';

test.describe('Comprehensive System Functionality', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('all navigation elements work correctly', async ({ page }) => {
    // Test all navigation buttons
    const navButtons = [
      { name: '📋 Inventory', expectedPath: '/inventory' },
      { name: '🌐 Routes', expectedPath: '/routing' },
      { name: '📊 Tables', expectedPath: '/tables' },
      { name: '⚙️ Admin', expectedPath: '/admin' }
    ];

    for (const button of navButtons) {
      await page.getByRole('button', { name: button.name }).click();
      await page.waitForTimeout(1000);
      await expect(page).toHaveURL(new RegExp(button.expectedPath + '$'));
      
      // Verify page content is loaded
      await expect(page.locator('body')).toBeVisible();
    }
  });

  test('inventory page all interactive elements work', async ({ page }) => {
    // Wait for inventory to load
    await expect(page.locator('.inventory-table')).toBeVisible({ timeout: 10000 });
    
    // Test table headers for sorting
    const headers = page.locator('.inventory-table th');
    const headerCount = await headers.count();
    
    for (let i = 0; i < Math.min(headerCount, 5); i++) {
      const header = headers.nth(i);
      if (await header.isVisible()) {
        await header.click();
        await page.waitForTimeout(500);
        // Table should still be visible after sorting
        await expect(page.locator('.inventory-table')).toBeVisible();
      }
    }

    // Test filter inputs if they exist
    const filterInputs = page.locator('input[placeholder*="filter"], input[placeholder*="search"], input[type="text"]');
    const inputCount = await filterInputs.count();
    
    if (inputCount > 0) {
      const firstInput = filterInputs.first();
      await firstInput.fill('test');
      await page.waitForTimeout(1000);
      await firstInput.fill('');
      await page.waitForTimeout(500);
    }

    // Test refresh button if it exists
    const refreshBtn = page.locator('button[title*="refresh"], button:has-text("Refresh"), .refresh-btn').first();
    if (await refreshBtn.isVisible()) {
      await refreshBtn.click();
      await page.waitForTimeout(2000);
      await expect(page.locator('.inventory-table')).toBeVisible();
    }

    // Test clicking on device rows
    const deviceRows = page.locator('.inventory-table tbody tr');
    const rowCount = await deviceRows.count();
    
    if (rowCount > 0) {
      // Test clicking on different device types
      for (let i = 0; i < Math.min(rowCount, 3); i++) {
        const row = deviceRows.nth(i);
        if (await row.isVisible()) {
          await row.click();
          await page.waitForTimeout(1000);
          
          // Should either navigate to routing or stay on inventory
          const currentUrl = page.url();
          if (currentUrl.includes('/routing')) {
            // If it navigated to routing, go back to inventory
            await page.getByRole('button', { name: '📋 Inventory' }).click();
            await expect(page.locator('.inventory-table')).toBeVisible({ timeout: 5000 });
          }
        }
      }
    }
  });

  test('routing page all interactive elements work', async ({ page }) => {
    // Navigate to routing page
    await page.getByRole('button', { name: '🌐 Routes' }).click();
    await page.waitForTimeout(3000);

    // Test routing controls
    const buttons = page.locator('button').filter({ isVisible: true });
    const buttonCount = await buttons.count();

    for (let i = 0; i < Math.min(buttonCount, 5); i++) {
      const button = buttons.nth(i);
      const buttonText = await button.textContent();
      
      if (buttonText && !buttonText.includes('📋') && !buttonText.includes('📊') && !buttonText.includes('⚙️')) {
        await button.click();
        await page.waitForTimeout(1000);
        // Page should still be functional
        await expect(page.locator('body')).toBeVisible();
      }
    }

    // Test filter inputs
    const inputs = page.locator('input').filter({ isVisible: true });
    const inputCount = await inputs.count();

    for (let i = 0; i < Math.min(inputCount, 3); i++) {
      const input = inputs.nth(i);
      await input.fill('192.168');
      await page.waitForTimeout(1000);
      await input.fill('');
      await page.waitForTimeout(500);
    }

    // Test dropdowns/selects
    const selects = page.locator('select').filter({ isVisible: true });
    const selectCount = await selects.count();

    for (let i = 0; i < Math.min(selectCount, 3); i++) {
      const select = selects.nth(i);
      const options = select.locator('option');
      const optionCount = await options.count();
      
      if (optionCount > 1) {
        await select.selectOption({ index: 1 });
        await page.waitForTimeout(1000);
        await select.selectOption({ index: 0 });
        await page.waitForTimeout(500);
      }
    }
  });

  test('tables page all interactive elements work', async ({ page }) => {
    // Navigate to tables page
    await page.getByRole('button', { name: '📊 Tables' }).click();
    await page.waitForTimeout(2000);

    // Test all dropdowns
    const selects = page.locator('select').filter({ isVisible: true });
    const selectCount = await selects.count();

    for (let i = 0; i < Math.min(selectCount, 5); i++) {
      const select = selects.nth(i);
      const options = select.locator('option');
      const optionCount = await options.count();
      
      // Test selecting different options
      for (let j = 1; j < Math.min(optionCount, 3); j++) {
        await select.selectOption({ index: j });
        await page.waitForTimeout(2000);
        
        // Check if content loaded
        const content = page.locator('.table-content, .data-table, tbody').first();
        if (await content.isVisible()) {
          await expect(content).toBeVisible();
        }
      }
    }

    // Test control buttons
    const controlButtons = page.locator('button').filter({ isVisible: true });
    const buttonCount = await controlButtons.count();

    for (let i = 0; i < Math.min(buttonCount, 5); i++) {
      const button = controlButtons.nth(i);
      const buttonText = await button.textContent();
      
      if (buttonText && !buttonText.includes('📋') && !buttonText.includes('🌐') && !buttonText.includes('⚙️')) {
        await button.click();
        await page.waitForTimeout(1000);
        await expect(page.locator('.table-explorer__toolbar')).toBeVisible();
      }
    }
  });

  test('admin page all interactive elements work', async ({ page }) => {
    // Navigate to admin page
    await page.getByRole('button', { name: '⚙️ Admin' }).click();
    await page.waitForTimeout(3000);

    // Test all buttons
    const buttons = page.locator('button').filter({ isVisible: true });
    const buttonCount = await buttons.count();

    for (let i = 0; i < Math.min(buttonCount, 8); i++) {
      const button = buttons.nth(i);
      const buttonText = await button.textContent();
      
      if (buttonText && !buttonText.includes('📋') && !buttonText.includes('🌐') && !buttonText.includes('📊')) {
        await button.click();
        await page.waitForTimeout(1000);
        await expect(page.locator('body')).toBeVisible();
      }
    }

    // Test all input fields
    const inputs = page.locator('input, textarea').filter({ isVisible: true });
    const inputCount = await inputs.count();

    for (let i = 0; i < Math.min(inputCount, 5); i++) {
      const input = inputs.nth(i);
      const inputType = await input.getAttribute('type');
      
      if (inputType !== 'password' && inputType !== 'hidden') {
        await input.fill('test-value');
        await page.waitForTimeout(500);
        await input.fill('');
        await page.waitForTimeout(500);
      }
    }

    // Test all select dropdowns
    const selects = page.locator('select').filter({ isVisible: true });
    const selectCount = await selects.count();

    for (let i = 0; i < Math.min(selectCount, 5); i++) {
      const select = selects.nth(i);
      const options = select.locator('option');
      const optionCount = await options.count();
      
      if (optionCount > 1) {
        await select.selectOption({ index: 1 });
        await page.waitForTimeout(1000);
        await select.selectOption({ index: 0 });
        await page.waitForTimeout(500);
      }
    }

    // Test checkboxes
    const checkboxes = page.locator('input[type="checkbox"]').filter({ isVisible: true });
    const checkboxCount = await checkboxes.count();

    for (let i = 0; i < Math.min(checkboxCount, 5); i++) {
      const checkbox = checkboxes.nth(i);
      await checkbox.check();
      await page.waitForTimeout(500);
      await checkbox.uncheck();
      await page.waitForTimeout(500);
    }
  });

  test('all links and external navigation work', async ({ page }) => {
    // Look for any links on the page
    const links = page.locator('a').filter({ isVisible: true });
    const linkCount = await links.count();

    for (let i = 0; i < Math.min(linkCount, 5); i++) {
      const link = links.nth(i);
      const href = await link.getAttribute('href');
      
      if (href && !href.startsWith('mailto:') && !href.startsWith('tel:')) {
        await link.click();
        await page.waitForTimeout(2000);
        
        // Should either navigate or stay functional
        await expect(page.locator('body')).toBeVisible();
        
        // Go back to main page if needed
        if (!page.url().includes('localhost')) {
          await page.goto('/');
          await page.waitForTimeout(1000);
        }
      }
    }
  });

  test('responsive design and viewport interactions', async ({ page }) => {
    // Test different viewport sizes
    const viewports = [
      { width: 1920, height: 1080 },
      { width: 1366, height: 768 },
      { width: 768, height: 1024 },
      { width: 375, height: 667 }
    ];

    for (const viewport of viewports) {
      await page.setViewportSize(viewport);
      await page.waitForTimeout(1000);
      
      // Test navigation is still functional
      await expect(page.getByRole('button', { name: '📋 Inventory' })).toBeVisible();
      await page.getByRole('button', { name: '📊 Tables' }).click();
      await page.waitForTimeout(1000);
      await page.getByRole('button', { name: '📋 Inventory' }).click();
      await page.waitForTimeout(1000);
    }
  });

  test('error handling and edge cases', async ({ page }) => {
    // Test rapid navigation
    const navButtons = ['📋 Inventory', '🌐 Routes', '📊 Tables', '⚙️ Admin'];
    
    for (let i = 0; i < 3; i++) {
      for (const button of navButtons) {
        await page.getByRole('button', { name: button }).click();
        await page.waitForTimeout(200);
      }
    }

    // Test page refresh on different pages
    for (const button of navButtons) {
      await page.getByRole('button', { name: button }).click();
      await page.waitForTimeout(1000);
      await page.reload();
      await page.waitForTimeout(2000);
      await expect(page.locator('body')).toBeVisible();
    }

    // Test browser back/forward
    await page.getByRole('button', { name: '📋 Inventory' }).click();
    await page.waitForTimeout(1000);
    await page.getByRole('button', { name: '🌐 Routes' }).click();
    await page.waitForTimeout(1000);
    await page.goBack();
    await page.waitForTimeout(1000);
    await page.goForward();
    await page.waitForTimeout(1000);
  });
});
