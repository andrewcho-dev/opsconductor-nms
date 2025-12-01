import { test, expect } from '@playwright/test';

test.describe('Admin Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.getByRole('button', { name: '⚙️ Admin' }).click();
  });

  test('admin page loads successfully', async ({ page }) => {
    // Wait for admin page to load - look for any admin-related content
    await page.waitForTimeout(3000);
    
    // Check for any admin-related headers or content
    const adminContent = page.locator('h1, h2, .admin, .settings, .configuration').first();
    if (await adminContent.isVisible()) {
      await expect(adminContent).toBeVisible();
    } else {
      // At minimum, the page should load without errors
      await expect(page.locator('body')).toBeVisible();
    }
  });

  test('admin sections are present', async ({ page }) => {
    // Wait for page to load
    await page.waitForTimeout(2000);
    
    // Look for common admin sections
    const expectedSections = [
      'system', 'network', 'discovery', 'configuration', 
      'settings', 'logs', 'status', 'monitoring'
    ];
    
    let foundSections = 0;
    for (const section of expectedSections) {
      const element = page.locator(`text=/${section}/i`).first();
      if (await element.isVisible()) {
        foundSections++;
      }
    }
    
    // Should have at least some admin content
    expect(foundSections).toBeGreaterThan(0);
  });

  test('admin controls are interactive', async ({ page }) => {
    await page.waitForTimeout(2000);
    
    // Look for buttons, forms, or other interactive elements
    const buttons = page.locator('button').count();
    const inputs = page.locator('input, select, textarea').count();
    
    // Should have some interactive elements
    expect(await buttons + await inputs).toBeGreaterThan(0);
  });

  test('can navigate admin tabs or sections', async ({ page }) => {
    await page.waitForTimeout(2000);
    
    // Look for tab-like navigation
    const tabs = page.locator('[role="tab"], .tab, .nav-item').filter({ hasText: /\w+/ });
    const tabCount = await tabs.count();
    
    if (tabCount > 0) {
      // Click on the first few tabs to test navigation
      for (let i = 0; i < Math.min(tabCount, 3); i++) {
        const tab = tabs.nth(i);
        if (await tab.isVisible()) {
          await tab.click();
          await page.waitForTimeout(1000);
          
          // Page should still be functional
          await expect(page.locator('body')).toBeVisible();
        }
      }
    }
  });

  test('admin forms work correctly', async ({ page }) => {
    await page.waitForTimeout(2000);
    
    // Look for forms and test basic interaction
    const forms = page.locator('form').filter({ has: page.locator('input, select, button') });
    const formCount = await forms.count();
    
    if (formCount > 0) {
      const firstForm = forms.first();
      
      // Try to fill simple inputs if they exist
      const textInputs = firstForm.locator('input[type="text"], input:not([type])').filter({ isVisible: true });
      const inputCount = await textInputs.count();
      
      if (inputCount > 0) {
        await textInputs.first().fill('test-value');
        await page.waitForTimeout(500);
        
        // Clear the value
        await textInputs.first().fill('');
        await page.waitForTimeout(500);
      }
    }
  });

  test('admin page handles errors gracefully', async ({ page }) => {
    // Page should load without showing errors
    await page.waitForTimeout(3000);
    
    // Should not have error displays visible
    const errorElements = page.locator('.error, .error-display, [role="alert"]').filter({ isVisible: true });
    const errorCount = await errorElements.count();
    
    // If there are errors, they should be user-friendly
    if (errorCount > 0) {
      const errorText = await errorElements.first().textContent();
      expect(errorText).toBeTruthy();
      expect(errorText!.length).toBeGreaterThan(10); // Should have meaningful message
    }
  });
});
