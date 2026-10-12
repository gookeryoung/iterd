/** 关键链路：通知触达（seed 产生的站内信在顶栏铃铛可见并可查看）。 */

import { test, expect } from '@playwright/test';

test.describe('通知触达关键路径', () => {
  test('顶栏铃铛有未读角标，通知中心弹层可见且存在通知项', async ({ page }) => {
    await page.goto('/');

    // 1. 铃铛可见且存在未读角标（seed 产生的审批待办/运行完成通知）
    const bell = page.getByLabel('通知中心');
    await expect(bell).toBeVisible();
    // Badge 计数是 Button 的兄弟节点（Badge 包裹层），须在页面级定位
    await expect(page.locator('.ant-badge-count').first()).toBeVisible();

    // 2. 打开通知中心：弹层可见且存在至少一条通知项（"会签待办"标题仅在会签流程触发后产生）
    await bell.click();
    await expect(page.getByText('通知中心').first()).toBeVisible();
    await expect(page.locator('.ant-list-item').first()).toBeVisible();
  });
});
