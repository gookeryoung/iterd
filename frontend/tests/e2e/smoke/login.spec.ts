/** 冒烟：登录链路（匿名重定向 / 错误提示 / 成功进入）。 */

import { test, expect } from '@playwright/test';

test.describe('登录', () => {
  test('匿名访问受保护路由被重定向到 /login', async ({ page }) => {
    await page.goto('/rules');
    await page.waitForURL(/\/login/);
    await expect(page.getByPlaceholder('用户名')).toBeVisible();
    await expect(page.getByPlaceholder('密码')).toBeVisible();
  });

  test('错误口令登录失败并提示后端错误信息', async ({ page }) => {
    await page.goto('/login');
    await page.getByPlaceholder('用户名').fill('admin');
    await page.getByPlaceholder('密码').fill('wrong-password');
    await page.getByRole('button', { name: /登\s*录/ }).click();

    await expect(page.getByText(/用户名或密码/)).toBeVisible({ timeout: 10_000 });
    // 仍停留在登录页
    await expect(page).toHaveURL(/\/login/);
  });

  test('正确口令登录成功进入项目列表', async ({ page }) => {
    await page.goto('/login');
    await page.getByPlaceholder('用户名').fill('admin');
    await page.getByPlaceholder('密码').fill('admin1234');
    await page.getByRole('button', { name: /登\s*录/ }).click();

    await page.waitForURL((url) => url.pathname === '/');
    await expect(page.getByRole('heading', { name: '项目管理' })).toBeVisible();
    // Header 显示当前用户名
    await expect(page.getByText('admin', { exact: true })).toBeVisible();
  });
});
