/** 关键页面：规则库 / 模板管理 / 审计日志（seed 演示数据驱动）。 */

import { test, expect } from '@playwright/test';

test.describe('规则库', () => {
  test('显示 seed 规则条目与规则集', async ({ page }) => {
    await page.goto('/rules');
    await expect(page.getByRole('heading', { name: '规则库' })).toBeVisible();
    // seed 规则（seed 主流程与演示规则集各建一条同名规则，取首个即可）
    await expect(page.getByText('图纸文件名规范').first()).toBeVisible();
    // 页面下方"规则集"卡片：seed 的"演示规则集"可见
    await expect(page.getByText('演示规则集').first()).toBeVisible();
  });
});

test.describe('模板管理', () => {
  test('显示 seed 审查模板', async ({ page }) => {
    await page.goto('/workflows');
    await expect(page.getByRole('heading', { name: /模板管理/ })).toBeVisible();
    await expect(page.getByText('演示审查流水线').first()).toBeVisible();
  });
});

test.describe('审计日志', () => {
  test('页面渲染且表格可访问', async ({ page }) => {
    await page.goto('/audit');
    await expect(page.getByRole('heading', { name: '审计日志' })).toBeVisible();
    // 表头渲染 + seed 产生的审计记录至少一行
    await expect(page.getByRole('columnheader', { name: '操作人' })).toBeVisible();
    await expect(page.locator('.ant-table-row').first()).toBeVisible();
  });
});
