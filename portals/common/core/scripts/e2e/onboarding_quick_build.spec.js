/**
 * Onboarding + quick-build browser E2E (P1-02).
 * Run: npx playwright test (requires Jenkins online for full path).
 */
const { test, expect } = require('@playwright/test');

test.describe('onboarding quick-build', () => {
  test.skip(!process.env.JENKINS_E2E_ONLINE, 'Set JENKINS_E2E_ONLINE=1 when Jenkins is up');

  test('wizard page loads', async ({ page }) => {
    const base = process.env.RELEASE_GATE_BASE_URL || 'http://127.0.0.1:5003';
    await page.goto(`${base}/admin/projects/new/wizard`);
    await expect(page.locator('body')).toContainText(/项目|wizard|向导/i);
  });
});
