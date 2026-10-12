/** 冒烟：退出登录（登录态下经下拉菜单登出，回到 /login 且凭证清除）。 */

import { test, expect } from '@playwright/test';

test('退出登录清除 token 并回到登录页', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: '项目管理' })).toBeVisible();

  // Header 用户名区域（antd Dropdown hover 触发）
  const username = page.getByText('admin', { exact: true });
  await username.hover();
  await page.getByText('退出登录').click();

  await page.waitForURL(/\/login/);
  // token 已清除
  const token = await page.evaluate(() => window.localStorage.getItem('iterd_token'));
  expect(token).toBeNull();
  await expect(page.getByPlaceholder('用户名')).toBeVisible();
});
