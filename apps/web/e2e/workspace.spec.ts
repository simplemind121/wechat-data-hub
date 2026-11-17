import { expect, test } from '@playwright/test';

test('real API liveness, honest readiness and navigation', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('让每一条记录，都有来处。');
  await expect(page.getByRole('status').first()).toHaveText('运行正常');
  await expect(page.getByRole('status').nth(1)).toHaveText('尚未就绪');
  await expect(page.getByText('尚未开放导入')).toBeVisible();
  if (process.env.WDH_CAPTURE_SCREENSHOTS) await page.screenshot({ path: '../../docs/evidence/workspace-desktop.png', fullPage: true });
  await page.getByRole('button', { name: '查看开发进度' }).click();
  await expect(page.getByRole('heading', { name: '当前交付范围' })).toBeVisible();
  await page.getByRole('button', { name: '隐私与边界' }).click();
  await expect(page.getByRole('heading', { name: '默认私有，按证据处理' })).toBeVisible();
});

test('mobile has no horizontal overflow', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await expect(page.getByRole('status').first()).toHaveText('运行正常');
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await expect(page.getByRole('status').nth(1)).toHaveText('尚未就绪');
  if (process.env.WDH_CAPTURE_SCREENSHOTS) await page.screenshot({ path: '../../docs/evidence/workspace-mobile.png', fullPage: true });
});

test('unavailable API shows failure without private input or fake metrics', async ({ page }) => {
  await page.route('**/api/v1/health/*', route => route.fulfill({ status: 503, body: '{}' }));
  await page.goto('/');
  await expect(page.getByRole('status').first()).toHaveText('尚未就绪');
  await expect(page.getByText('等待真实样本验证')).toBeVisible();
});
