import { test, expect } from '@playwright/test'

test.describe('Quest Settings Surface', () => {
  test('should display quest configuration page', async ({ page }) => {
    // 导航到一个 quest 的 settings 页面
    await page.goto('http://localhost:21888/ui')
    await page.waitForTimeout(2000)

    // 等待页面加载
    await page.waitForSelector('text=Quest Configuration, text=Quest 配置', { timeout: 10000 })

    // 截图
    await page.screenshot({ path: '/tmp/quest-settings-initial.png', fullPage: true })
  })

  test('should toggle environment variables section', async ({ page }) => {
    await page.goto('http://localhost:21888/ui')
    await page.waitForTimeout(2000)

    // 查找环境变量折叠按钮
    const envButton = page.locator('button:has-text("Environment Variables"), button:has-text("环境变量")').first()

    if (await envButton.isVisible()) {
      // 点击展开
      await envButton.click()
      await page.waitForTimeout(500)
      await page.screenshot({ path: '/tmp/quest-settings-env-expanded.png', fullPage: true })

      // 点击收起
      await envButton.click()
      await page.waitForTimeout(500)
      await page.screenshot({ path: '/tmp/quest-settings-env-collapsed.png', fullPage: true })
    }
  })

  test('should display workspace mode selector', async ({ page }) => {
    await page.goto('http://localhost:21888/ui')
    await page.waitForTimeout(2000)

    // 查找工作模式选择器
    const modeSelector = page.locator('text=Copilot, text=Autonomous').first()

    if (await modeSelector.isVisible()) {
      await page.screenshot({ path: '/tmp/quest-settings-workspace-mode.png' })
    }
  })

  test('should display connector bindings section', async ({ page }) => {
    await page.goto('http://localhost:21888/ui')
    await page.waitForTimeout(2000)

    // 查找连接器绑定区域
    const bindingsSection = page.locator('text=Connector, text=连接器').first()

    if (await bindingsSection.isVisible()) {
      await page.screenshot({ path: '/tmp/quest-settings-bindings.png' })
    }
  })
})
