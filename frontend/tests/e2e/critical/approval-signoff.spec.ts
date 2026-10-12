/** 关键链路：审批会签（seed 数据集预执行后留下的 waiting 会签作业 → 签署 → 续跑）。 */

import { test, expect } from '@playwright/test';

test.describe('审批会签关键路径', () => {
  test('seed 会签待办可见，签署达成后流水线续跑、该待办清空', async ({ page }) => {
    // 1. 审批待办中心：seed（数据集「项目-某型输送机总装会签流程」）预执行后
    //    sign-off 作业挂起，出现 ASM-SIGNOFF 总装会签待办卡片
    await page.goto('/approvals');
    await expect(page.getByRole('heading', { name: '审批待办' })).toBeVisible();
    const card = page.locator('[data-testid="pending-approval-card"][data-workflow="ASM-SIGNOFF"]');
    await expect(card).toBeVisible();

    // 2. 签署意见（登录态为 admin 超管，恒在签署范围内）：默认"通过"，直接提交
    await card.getByRole('button', { name: '签署意见' }).click();
    const dialog = page.getByRole('dialog', { name: '签署审批意见' });
    await expect(dialog).toBeVisible();
    await dialog.getByRole('button', { name: '提交签署' }).click();
    await expect(page.getByText('签署成功').first()).toBeVisible();

    // 3. 会签门槛 min_count=1：签署即达成，作业完成，该待办卡片从列表消失
    await expect(card).toHaveCount(0, { timeout: 15_000 });
  });
});
