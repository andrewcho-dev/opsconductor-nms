import { test, expect } from '@playwright/test';

test('error handling works correctly', async ({ page }) => {
  // Navigate to the tables page
  await page.goto('http://127.0.0.1:3000');

  // Click on Tables navigation
  await page.click('text=📊 Tables');

  // Wait for the page to load
  await page.waitForSelector('.table-explorer__toolbar', { timeout: 10000 });

  // Try to fetch a non-existent table to trigger an error
  // First, we need to mock the API to return an error
  await page.route('**/api/tables?table=nonexistent**', route => {
    route.fulfill({
      status: 400,
      contentType: 'application/json',
      body: JSON.stringify({
        success: false,
        error: {
          error_id: "TEST_ERROR_123",
          error_code: "RESOURCE_NOT_FOUND",
          message: "Table 'nonexistent' not found",
          user_message: "The requested table does not exist.",
          troubleshooting: "Please select a valid table from the dropdown.",
          timestamp: new Date().toISOString(),
          path: "/api/tables"
        }
      })
    });
  });

  // Select a non-existent table (we'll modify the select temporarily)
  await page.evaluate(() => {
    const select = document.querySelector('.table-explorer__toolbar select') as HTMLSelectElement;
    if (select) {
      // Create a temporary option
      const option = document.createElement('option');
      option.value = 'nonexistent';
      option.text = 'Non-existent Table';
      select.appendChild(option);
      select.value = 'nonexistent';
      select.dispatchEvent(new Event('change', { bubbles: true }));
    }
  });

  // Wait for error to appear
  await page.waitForSelector('.error-display', { timeout: 5000 });

  // Check that the error is displayed correctly
  const errorElement = await page.$('.error-display');
  expect(errorElement).toBeTruthy();

  // Check error message content
  const errorText = await errorElement?.textContent();
  expect(errorText).toContain('RESOURCE NOT FOUND');
  expect(errorText).toContain('The requested table does not exist');

  // Check that error ID is displayed
  expect(errorText).toContain('TEST_ERROR_123');

  // Check that troubleshooting info is shown
  expect(errorText).toContain('Please select a valid table from the dropdown');

  console.log('Error handling test passed!');
});
