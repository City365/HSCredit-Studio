/** Playwright E2E — 登录流程. */
import { test, expect } from '@playwright/test';

test.describe('Login Flow', () => {
  test('successful login redirects to workflows', async ({ page }) => {
    await page.goto('http://localhost:3000/login');
    await page.fill('input[id="tenant_slug"]', 'demo');
    await page.fill('input[id="email"]', 'admin@demo.com');
    await page.fill('input[id="password"]', 'DemoPass123!');
    await page.click('button[type="submit"]');
    await expect(page).toHaveURL(/\/workflows/);
  });

  test('invalid credentials shows error', async ({ page }) => {
    await page.goto('http://localhost:3000/login');
    await page.fill('input[id="tenant_slug"]', 'demo');
    await page.fill('input[id="email"]', 'wrong@example.com');
    await page.fill('input[id="password"]', 'wrongpassword');
    await page.click('button[type="submit"]');
    await expect(page.locator('.ant-message-error')).toBeVisible();
  });
});