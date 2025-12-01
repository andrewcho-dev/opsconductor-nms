# Playwright E2E Testing Setup

This project includes comprehensive Playwright end-to-end tests covering all main application flows.

## 🎭 Available Scripts

- `npm run test:e2e` - Run all tests in headless mode
- `npm run test:e2e:ui` - Run tests with interactive Playwright UI viewer
- `npm run test:e2e:headed` - Run tests with visible browser window

## 📋 Test Coverage

### Navigation Tests (`navigation.spec.ts`)
- All navigation buttons are present and clickable
- Navigation highlights current page correctly
- URL updates when navigating between pages

### Inventory Page Tests (`inventory.spec.ts`)
- Inventory page loads and displays device table
- Table columns are sortable
- Inventory items can be filtered
- Different device types are displayed
- Refresh functionality works

### Routing Page Tests (`routing.spec.ts`)
- Routing page loads when router is selected
- Routing table displays correctly
- Routing entries can be filtered
- Routing controls work (refresh, clear)
- Router selection persists across navigation
- Handles no routing data gracefully

### Tables Explorer Tests (`tables.spec.ts`)
- Tables page loads with toolbar
- Can select different tables from dropdown
- Table data displays correctly
- Table controls work (refresh, export)
- Handles empty table selection gracefully

### Admin Page Tests (`admin.spec.ts`)
- Admin page loads successfully
- Admin sections are present
- Admin controls are interactive
- Can navigate admin tabs/sections
- Admin forms work correctly
- Handles errors gracefully

### Error Handling Tests (`error-handling.spec.ts`)
- Error display works correctly
- Error messages contain proper information
- Error IDs and troubleshooting info are shown

## 🚀 Quick Start

1. **Install dependencies** (if not already done):
   ```bash
   npm install
   ```

2. **Install Playwright browsers** (if not already done):
   ```bash
   npx playwright install chromium
   ```

3. **Start development server** (required for tests):
   ```bash
   npm run dev
   ```
   The server will start on `http://localhost:3005` (or next available port).

4. **Run tests**:
   ```bash
   # Run all tests in headless mode
   npm run test:e2e
   
   # Run with interactive UI (recommended for development)
   npm run test:e2e:ui
   
   # Run with visible browser
   npm run test:e2e:headed
   ```

## 🎨 Windsurf Integration

For Windsurf users, the following tasks are available in `windsurf-tasks.json`:

- **test:e2e:ui** - Interactive UI mode for debugging
- **test:e2e:headed** - Visible browser mode
- **test:e2e** - Fast headless mode for CI/CD
- **dev-server** - Start development server

## 🛠️ Configuration

Playwright is configured in `playwright.config.ts`:
- Base URL: `http://localhost:3005` (auto-updates based on dev server)
- Timeout: 30 seconds per test
- Screenshot/video capture on failure
- Single Chromium project

## 📊 Test Results

- **Total Tests**: 28 tests covering all major flows
- **Execution Time**: ~1.5 minutes
- **Coverage**: Navigation, Inventory, Routing, Tables, Admin, Error Handling

## 🔧 Debugging

1. **Use UI mode** for step-by-step debugging:
   ```bash
   npm run test:e2e:ui
   ```

2. **Use headed mode** to see the browser:
   ```bash
   npm run test:e2e:headed
   ```

3. **Check test results** in `test-results/` directory:
   - Screenshots on failure
   - Videos of test execution
   - Trace files for debugging

4. **Run specific tests**:
   ```bash
   npx playwright test tests/navigation.spec.ts
   npx playwright test --grep "navigation"
   ```

## 📝 Adding New Tests

1. Create new `.spec.ts` files in the `tests/` directory
2. Use the existing test patterns as templates
3. Follow the page object model pattern where applicable
4. Run `npm run test:e2e` to verify new tests

## 🔄 Continuous Integration

The tests are designed to run in CI/CD environments:
- Headless mode by default
- Automatic browser installation
- Proper error reporting and exit codes

## 🐛 Troubleshooting

- **Connection refused**: Make sure dev server is running (`npm run dev`)
- **Browser not found**: Run `npx playwright install`
- **Tests timeout**: Increase timeout in `playwright.config.ts`
- **Element not found**: Use Playwright's UI mode to inspect selectors

## 🎯 Best Practices

- Tests are independent and can run in any order
- Each test cleans up after itself
- Proper waiting strategies are used
- Tests cover both happy paths and error scenarios
- Selectors are resilient to UI changes
