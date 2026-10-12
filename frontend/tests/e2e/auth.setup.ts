import { test, expect } from '@playwright/test';

const DEMO_USER = 'admin';
const DEMO_PASS = 'admin1234';
const STATE_PATH = '.auth/state.json';

test('登录并持久化 StorageState', async ({ page }) => {
  await page.goto('/');
  await page.waitForURL(/\/login/);

  const usernameInput = page.getByPlaceholder('用户名');
  const passwordInput = page.getByPlaceholder('密码');
  // antd 两字按钮的 accessible name 为"登 录"（自动插入空格），用正则兼容两种
  const loginButton = page.getByRole('button', { name: /登\s*录/ });

  await expect(usernameInput).toBeVisible();
  await expect(passwordInput).toBeVisible();
  await expect(loginButton).toBeVisible();

  await usernameInput.fill(DEMO_USER);
  await passwordInput.fill(DEMO_PASS);
  await loginButton.click();

  // 登录后进入 /（项目列表）
  await page.waitForURL((url) => url.pathname === '/');
  // token 写入 localStorage 后才落盘 state，避免保存到空态
  await page.waitForFunction(() => !!window.localStorage.getItem('iterd_token'));
  await page.context().storageState({ path: STATE_PATH });
});
