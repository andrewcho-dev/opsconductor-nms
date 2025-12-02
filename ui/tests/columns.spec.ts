import { test, expect } from '@playwright/test';

test.describe('Table Columns', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.getByRole('button', { name: '📊 Tables' }).click();
  });

  test('Networks table should not show Run or ID columns', async ({ page }) => {
    // Select Networks table
    await page.getByRole('combobox').first().selectOption('networks');
    
    // Wait for table to load
    await page.waitForSelector('.inventory-grid-wrapper');
    
    // Get all column headers
    const headers = await page.locator('th').allTextContents();
    console.log('Actual columns:', headers);
    
    // Check that Run column is NOT present
    expect(headers).not.toContain('Run');
    
    // Check that ID column is NOT present  
    expect(headers).not.toContain('Network ID');
    
    // Check that router_id column is NOT present
    expect(headers).not.toContain('Router');
    
    // Check that Router IP column IS present
    expect(headers.some(header => header.includes('Router IP'))).toBe(true);
  });

  test('Routers table should not show ID columns', async ({ page }) => {
    // Select Routers table
    await page.getByRole('combobox').first().selectOption('routers');
    
    // Wait for table to load
    await page.waitForSelector('.inventory-grid-wrapper');
    
    // Get all column headers
    const headers = await page.locator('th').allTextContents();
    console.log('Routers table columns:', headers);
    
    // Check that ID column is NOT present
    expect(headers).not.toContain('ID');
  });
});
