/** 关键链路：项目列表 → 项目详情 → 迭代详情（seed 演示数据驱动）。 */

import { test, expect } from '@playwright/test';

test.describe('项目核心链路', () => {
  test('项目列表显示演示项目，点击进入详情与迭代', async ({ page }) => {
    // 1. 项目列表：seed 创建的"演示项目"可见
    await page.goto('/');
    const projectRow = page.getByRole('cell', { name: '演示项目' });
    await expect(projectRow).toBeVisible();

    // 2. 点击行进入项目详情：标题与编码展示
    await projectRow.click();
    await page.waitForURL(/\/projects\/\d+/);
    await expect(page.getByRole('heading', { name: /演示项目/ })).toBeVisible();
    await expect(page.getByText('DEMO')).toBeVisible();

    // 3. 切到"迭代" Tab：seed 创建的"第一轮迭代"可见
    await page.getByRole('tab', { name: '迭代' }).click();
    await expect(page.getByRole('cell', { name: '第一轮迭代' })).toBeVisible();

    // 4. 进入迭代详情：标题"迭代 1：第一轮迭代"
    await page
      .getByRole('row', { name: /第一轮迭代/ })
      .getByRole('button', { name: '进入' })
      .click();
    await page.waitForURL(/\/iterations\/\d+/);
    await expect(page.getByRole('heading', { name: /迭代 1：第一轮迭代/ })).toBeVisible();

    // 5. 返回项目
    await page.getByRole('button', { name: '返回项目' }).click();
    await page.waitForURL(/\/projects\/\d+/);
    await expect(page.getByRole('heading', { name: /演示项目/ })).toBeVisible();
  });
});
