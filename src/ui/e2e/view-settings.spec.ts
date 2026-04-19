import { test } from '@playwright/test'

test('capture settings pages', async ({ page }) => {
  await page.goto('http://localhost:21888/ui/settings')

  // 等待页面加载完成
  await page.waitForSelector('text=Settings', { timeout: 10000 })
  await page.waitForTimeout(3000)
  await page.screenshot({ path: '/tmp/settings-main.png', fullPage: true })

  // 点击 Admin 展开
  const adminBtn = page.locator('button:has-text("Admin"), button:has-text("管理")').first()
  if (await adminBtn.isVisible().catch(() => false)) {
    await adminBtn.click()
    await page.waitForTimeout(1000)
  }

  // Summary 页面
  const summaryBtn = page.locator('button:has-text("Summary"), button:has-text("摘要")').first()
  if (await summaryBtn.isVisible().catch(() => false)) {
    await summaryBtn.click()
    await page.waitForTimeout(4000)
    await page.screenshot({ path: '/tmp/settings-summary.png', fullPage: true })
  }

  // Stats 页面
  const statsBtn = page.locator('button:has-text("Stats"), button:has-text("统计")').first()
  if (await statsBtn.isVisible().catch(() => false)) {
    await statsBtn.click()
    await page.waitForTimeout(4000)
    await page.screenshot({ path: '/tmp/settings-stats.png', fullPage: true })
  }

  // Runtime 页面
  const runtimeBtn = page.locator('button:has-text("Runtime"), button:has-text("运行时"), button:has-text("Sessions")').first()
  if (await runtimeBtn.isVisible().catch(() => false)) {
    await runtimeBtn.click()
    await page.waitForTimeout(4000)
    await page.screenshot({ path: '/tmp/settings-runtime.png', fullPage: true })
  }
})
