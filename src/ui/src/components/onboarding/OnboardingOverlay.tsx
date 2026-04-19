'use client'

import * as React from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { BookOpen, ChevronLeft, ChevronRight, Compass, Languages, Sparkles, X } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

import { Button } from '@/components/ui/button'
import { onboardingStepBodies } from '@/demo/onboarding/steps'
import {
  ONBOARDING_MOBILE_VIEWPORT_MAX_WIDTH,
  useMobileViewport,
} from '@/lib/hooks/useMobileViewport'
import { useAdminOpsStore } from '@/lib/stores/admin-ops'
import { cn } from '@/lib/utils'
import { useOnboardingStore, type OnboardingLanguage } from '@/lib/stores/onboarding'

type OnboardingStep = {
  id: string
  route: 'landing' | 'project' | 'settings'
  title: Record<OnboardingLanguage, string>
  body: Record<OnboardingLanguage, string>
  hint?: Record<OnboardingLanguage, string>
  targetId?: string
  actionTargetId?: string
  navigateTo?: string
  placement?: 'auto' | 'top' | 'bottom' | 'left' | 'right' | 'center'
  advanceMode?: 'manual' | 'wait_for_element' | 'wait_for_element_missing' | 'wait_for_route'
  waitForElementId?: string
  waitForRoute?: RegExp
  routePattern?: RegExp
  autoSkipIfTargetMissing?: boolean
}

type OverlayCopy = {
  chooserTitle: string
  chooserBody: string
  chooserZh: string
  chooserEn: string
  chooserSkip: string
  chooserNever: string
  progress: (current: number, total: number) => string
  back: string
  next: string
  finish: string
  skip: string
  waitForAction: string
  waitingTarget: string
  readingHint: string
}

const COPY: Record<OnboardingLanguage, OverlayCopy> = {
  en: {
    chooserTitle: 'Choose your first tutorial',
    chooserBody:
      'DeepScientist can walk you through the first run step by step. Choose the guide language, skip for now, or turn the reminder off.',
    chooserZh: 'Chinese guide',
    chooserEn: 'English guide',
    chooserSkip: 'Skip for now',
    chooserNever: 'Do not remind again',
    progress: (current, total) => `Step ${current} / ${total}`,
    back: 'Back',
    next: 'Next',
    finish: 'Finish',
    skip: 'Skip tutorial',
    waitForAction: 'You can click the highlighted area yourself, or press Next and I will continue for you.',
    waitingTarget: 'Waiting for the next area to appear. If the page is still moving, give it a second.',
    readingHint: 'Take your time. This step will not move on until you press Next.',
  },
  zh: {
    chooserTitle: '选择首次教程语言',
    chooserBody:
      'DeepScientist 可以像游戏教程一样，带你一步步完成第一次使用。你可以选择中文或英文讲解，也可以先跳过或不再提醒。',
    chooserZh: '中文讲解',
    chooserEn: 'English guide',
    chooserSkip: '暂时跳过',
    chooserNever: '不再提醒',
    progress: (current, total) => `第 ${current} / ${total} 步`,
    back: '上一步',
    next: '下一步',
    finish: '完成',
    skip: '跳过教程',
    waitForAction: '你可以自己点击高亮区域，也可以直接按“下一步”，我会替你继续。',
    waitingTarget: '正在等待下一块区域出现。如果页面还在变化，稍等一秒即可。',
    readingHint: '这一页不会自动跳走，你可以先把当前区域看清楚，再按“下一步”。',
  },
}

const ONBOARDING_ANIMATION_STYLES = `
@keyframes ds-onboarding-halo {
  0%, 100% {
    transform: scale(0.985);
    opacity: 0.78;
  }
  50% {
    transform: scale(1.02);
    opacity: 1;
  }
}

@keyframes ds-onboarding-float {
  0%, 100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-3px);
  }
}
`

const ONBOARDING_LAYER_CLASS = 'z-[10020]'

const ONBOARDING_STEPS: OnboardingStep[] = [
  {
    id: 'landing-intro',
    route: 'landing',
    targetId: 'landing-hero',
    title: {
      en: 'This is the launch surface',
      zh: '这里是研究启动页',
    },
    body: onboardingStepBodies['landing-intro'],
  },
  {
    id: 'landing-surfaces',
    route: 'landing',
    targetId: 'landing-entry-actions',
    title: {
      en: 'These are the three main entry paths',
      zh: '这里是三个主要入口',
    },
    body: onboardingStepBodies['landing-surfaces'],
  },
  {
    id: 'landing-open-benchstore',
    route: 'landing',
    targetId: 'landing-benchstore',
    title: {
      en: 'Open BenchStore first',
      zh: '先打开 BenchStore',
    },
    body: onboardingStepBodies['landing-open-benchstore'],
    actionTargetId: 'landing-benchstore',
    advanceMode: 'wait_for_element',
    waitForElementId: 'benchstore-dialog',
  },
  {
    id: 'benchstore-overview',
    route: 'landing',
    targetId: 'benchstore-overview-surface',
    title: {
      en: 'BenchStore starts as a storefront view',
      zh: 'BenchStore 先以 storefront 方式出现',
    },
    body: onboardingStepBodies['benchstore-overview'],
    placement: 'top',
    autoSkipIfTargetMissing: true,
  },
  {
    id: 'benchstore-copilot',
    route: 'landing',
    targetId: 'benchstore-assistant-surface',
    title: {
      en: 'BenchStore Copilot can recommend and prepare launch details',
      zh: 'BenchStore Copilot 会帮你推荐并补齐启动信息',
    },
    body: onboardingStepBodies['benchstore-copilot'],
    placement: 'left',
  },
  {
    id: 'benchstore-open-detail',
    route: 'landing',
    targetId: 'benchstore-featured-card',
    title: {
      en: 'Open one benchmark detail page',
      zh: '打开一个 benchmark 详情页',
    },
    body: onboardingStepBodies['benchstore-open-detail'],
    actionTargetId: 'benchstore-featured-card',
    advanceMode: 'wait_for_element',
    waitForElementId: 'benchstore-detail-surface',
    autoSkipIfTargetMissing: true,
  },
  {
    id: 'benchstore-detail',
    route: 'landing',
    targetId: 'benchstore-detail-surface',
    title: {
      en: 'This detail page is where the choice becomes real',
      zh: '真正做选择时看的是这个详情页',
    },
    body: onboardingStepBodies['benchstore-detail'],
    placement: 'top',
    autoSkipIfTargetMissing: true,
  },
  {
    id: 'benchstore-start',
    route: 'landing',
    targetId: 'benchstore-detail-action-strip',
    title: {
      en: 'This strip is the handoff into launch',
      zh: '这个动作区就是进入启动流程的交接点',
    },
    body: onboardingStepBodies['benchstore-start'],
    hint: {
      en: 'Read this handoff point first. Then press Next and I will close BenchStore before continuing.',
      zh: '先看清这个交接点，再按“下一步”，我会先替你退出 BenchStore，然后继续。',
    },
    actionTargetId: 'benchstore-close',
    advanceMode: 'wait_for_element_missing',
    waitForElementId: 'benchstore-dialog',
    placement: 'top',
  },
  {
    id: 'landing-open-dialog',
    route: 'landing',
    targetId: 'landing-start-research',
    title: {
      en: 'Open the launch dialog',
      zh: '先打开启动模式弹框',
    },
    body: onboardingStepBodies['landing-open-dialog'],
    actionTargetId: 'landing-start-research',
    advanceMode: 'wait_for_element',
    waitForElementId: 'experiment-launch-dialog',
  },
  {
    id: 'launch-mode-overview',
    route: 'landing',
    targetId: 'experiment-launch-dialog',
    title: {
      en: 'First choose between Copilot and Autonomous',
      zh: '先在 Copilot 和全自动之间做选择',
    },
    body: onboardingStepBodies['launch-mode-overview'],
    placement: 'top',
  },
  {
    id: 'launch-mode-copilot',
    route: 'landing',
    targetId: 'launch-mode-copilot-card',
    title: {
      en: 'Copilot is for human-in-the-loop work',
      zh: 'Copilot 适合人机共研',
    },
    body: onboardingStepBodies['launch-mode-copilot'],
    placement: 'right',
  },
  {
    id: 'launch-mode-autonomous',
    route: 'landing',
    targetId: 'launch-mode-autonomous-card',
    title: {
      en: 'The walkthrough now follows the autonomous path',
      zh: '这个教程接下来走全自动主线',
    },
    body: onboardingStepBodies['launch-mode-autonomous'],
    actionTargetId: 'launch-mode-autonomous-card',
    advanceMode: 'wait_for_element',
    waitForElementId: 'start-research-dialog',
  },
  {
    id: 'dialog-overview',
    route: 'landing',
    targetId: 'start-research-dialog',
    title: {
      en: 'Start with the essentials first',
      zh: '先从必要信息开始',
    },
    body: onboardingStepBodies['dialog-overview'],
    placement: 'top',
  },
  {
    id: 'dialog-title',
    route: 'landing',
    targetId: 'start-research-title',
    title: {
      en: 'Title and Project ID',
      zh: '标题和项目 ID',
    },
    body: onboardingStepBodies['dialog-title'],
  },
  {
    id: 'dialog-goal',
    route: 'landing',
    targetId: 'start-research-goal',
    title: {
      en: 'Write the real research request here',
      zh: '这里写真正的研究请求',
    },
    body: onboardingStepBodies['dialog-goal'],
  },
  {
    id: 'dialog-references',
    route: 'landing',
    targetId: 'start-research-references',
    title: {
      en: 'Attach baselines and references when you have them',
      zh: '有 baseline 和参考资料就放在这里',
    },
    body: onboardingStepBodies['dialog-references'],
  },
  {
    id: 'dialog-connectors',
    route: 'landing',
    targetId: 'start-research-connector',
    title: {
      en: 'Choose where delivery and updates should go',
      zh: '选择启动后消息要投递到哪里',
    },
    body: onboardingStepBodies['dialog-connectors'],
  },
  {
    id: 'dialog-deepxiv',
    route: 'landing',
    targetId: 'start-research-deepxiv',
    title: {
      en: 'DeepXiv changes the literature route',
      zh: 'DeepXiv 会改变文献路线',
    },
    body: onboardingStepBodies['dialog-deepxiv'],
  },
  {
    id: 'dialog-contract',
    route: 'landing',
    targetId: 'start-research-contract',
    title: {
      en: 'The launch contract changes how the run begins',
      zh: '这组启动合同会改变项目最初的推进方式',
    },
    body: onboardingStepBodies['dialog-contract'],
    placement: 'left',
  },
  {
    id: 'dialog-setup-agent',
    route: 'landing',
    targetId: 'start-research-assistant-surface',
    title: {
      en: 'SetupAgent can help complete the launch form',
      zh: 'SetupAgent 可以协助补齐启动表单',
    },
    body: onboardingStepBodies['dialog-setup-agent'],
    actionTargetId: 'start-research-toggle-preview',
    advanceMode: 'wait_for_element',
    waitForElementId: 'start-research-preview-surface',
    placement: 'left',
    autoSkipIfTargetMissing: true,
  },
  {
    id: 'dialog-preview',
    route: 'landing',
    targetId: 'start-research-preview-surface',
    title: {
      en: 'Review the kickoff prompt before you create',
      zh: '创建前看一眼 kickoff Prompt',
    },
    body: onboardingStepBodies['dialog-preview'],
    placement: 'left',
  },
  {
    id: 'dialog-create',
    route: 'landing',
    targetId: 'start-research-create',
    title: {
      en: 'Create the project to continue',
      zh: '创建项目后继续',
    },
    body: onboardingStepBodies['dialog-create'],
    actionTargetId: 'start-research-create',
    advanceMode: 'wait_for_route',
    waitForRoute: /^\/(projects\/[^/]+|tutorial\/demo\/[^/]+)$/,
  },
  {
    id: 'workspace-navbar',
    route: 'project',
    targetId: 'workspace-navbar',
    title: {
      en: 'This top bar is your global control strip',
      zh: '这条顶部栏是全局控制区',
    },
    body: onboardingStepBodies['workspace-navbar'],
  },
  {
    id: 'workspace-explorer',
    route: 'project',
    targetId: 'workspace-explorer',
    title: {
      en: 'Explorer is the local file view',
      zh: 'Explorer 是本地文件视角',
    },
    body: onboardingStepBodies['workspace-explorer'],
    autoSkipIfTargetMissing: true,
  },
  {
    id: 'workspace-arxiv',
    route: 'project',
    targetId: 'quest-explorer-arxiv-tab',
    title: {
      en: 'ArXiv keeps the project literature visible',
      zh: 'ArXiv 区域会保留项目文献',
    },
    body: onboardingStepBodies['workspace-arxiv'],
    actionTargetId: 'quest-explorer-arxiv-tab',
    advanceMode: 'wait_for_element',
    waitForElementId: 'workspace-arxiv',
    autoSkipIfTargetMissing: true,
  },
  {
    id: 'workspace-files-tab',
    route: 'project',
    targetId: 'quest-explorer-files-tab',
    title: {
      en: 'Return to Files to keep exploring the workspace',
      zh: '切回 Files，继续浏览工作区',
    },
    body: onboardingStepBodies['workspace-files-tab'],
    actionTargetId: 'quest-explorer-files-tab',
    advanceMode: 'wait_for_element',
    waitForElementId: 'quest-explorer-open-file',
    autoSkipIfTargetMissing: true,
  },
  {
    id: 'workspace-open-file',
    route: 'project',
    targetId: 'quest-explorer-open-file',
    title: {
      en: 'Open a real file from Explorer',
      zh: '从 Explorer 打开一个真实文件',
    },
    body: onboardingStepBodies['workspace-open-file'],
    actionTargetId: 'quest-explorer-open-file',
    advanceMode: 'wait_for_element',
    waitForElementId: 'quest-file-surface',
    autoSkipIfTargetMissing: true,
  },
  {
    id: 'workspace-file-surface',
    route: 'project',
    targetId: 'quest-file-surface',
    title: {
      en: 'This is the file view itself',
      zh: '这里就是文件本身的查看界面',
    },
    body: onboardingStepBodies['workspace-file-surface'],
    autoSkipIfTargetMissing: true,
  },
  {
    id: 'workspace-file-back',
    route: 'project',
    targetId: 'quest-workspace-tab-canvas',
    title: {
      en: 'Return to the workspace to continue',
      zh: '返回工作区，继续后面的操作',
    },
    body: onboardingStepBodies['workspace-file-back'],
    actionTargetId: 'quest-workspace-tab-canvas',
    advanceMode: 'wait_for_element',
    waitForElementId: 'quest-canvas-surface',
    autoSkipIfTargetMissing: true,
  },
  {
    id: 'workspace-canvas',
    route: 'project',
    targetId: 'quest-canvas-surface',
    title: {
      en: 'Canvas shows the research map',
      zh: 'Canvas 展示研究地图',
    },
    body: onboardingStepBodies['workspace-canvas'],
    autoSkipIfTargetMissing: true,
  },
  {
    id: 'workspace-canvas-node',
    route: 'project',
    targetId: 'quest-canvas-focus-node',
    title: {
      en: 'Click a node to inspect the branch itself',
      zh: '点击节点，查看这条分支本身的内容',
    },
    body: onboardingStepBodies['workspace-canvas-node'],
    actionTargetId: 'quest-canvas-focus-node',
    advanceMode: 'wait_for_element',
    waitForElementId: 'quest-stage-surface',
    autoSkipIfTargetMissing: true,
  },
  {
    id: 'workspace-scope-files',
    route: 'project',
    targetId: 'quest-scope-diff-file',
    title: {
      en: 'Node clicks also scope the Explorer to the relevant files',
      zh: '点节点后，Explorer 也会切到这条分支对应的文件',
    },
    body: onboardingStepBodies['workspace-scope-files'],
    autoSkipIfTargetMissing: true,
  },
  {
    id: 'workspace-open-diff',
    route: 'project',
    targetId: 'quest-scope-diff-file',
    title: {
      en: 'Open the diff to inspect what changed',
      zh: '打开 diff，查看到底改了什么',
    },
    body: onboardingStepBodies['workspace-open-diff'],
    actionTargetId: 'quest-scope-diff-file',
    advanceMode: 'wait_for_element',
    waitForElementId: 'quest-diff-surface',
    autoSkipIfTargetMissing: true,
  },
  {
    id: 'workspace-details-tab',
    route: 'project',
    targetId: 'quest-workspace-tab-details',
    title: {
      en: 'Open Details for the high-signal summary',
      zh: '打开 Details 看高信号摘要',
    },
    body: onboardingStepBodies['workspace-details-tab'],
    actionTargetId: 'quest-workspace-tab-details',
    advanceMode: 'wait_for_element',
    waitForElementId: 'quest-details-surface',
    autoSkipIfTargetMissing: true,
  },
  {
    id: 'workspace-details',
    route: 'project',
    targetId: 'quest-details-surface',
    title: {
      en: 'Details is the quick project briefing',
      zh: 'Details 是项目的快速简报页',
    },
    body: onboardingStepBodies['workspace-details'],
    autoSkipIfTargetMissing: true,
  },
  {
    id: 'workspace-memory-tab',
    route: 'project',
    targetId: 'quest-workspace-tab-memory',
    title: {
      en: 'Open Memory for durable notes',
      zh: '打开 Memory 看持久记忆',
    },
    body: onboardingStepBodies['workspace-memory-tab'],
    actionTargetId: 'quest-workspace-tab-memory',
    advanceMode: 'wait_for_element',
    waitForElementId: 'quest-memory-surface',
    autoSkipIfTargetMissing: true,
  },
  {
    id: 'workspace-memory',
    route: 'project',
    targetId: 'quest-memory-surface',
    title: {
      en: 'Memory keeps the project growing across rounds',
      zh: 'Memory 让项目能跨轮次持续生长',
    },
    body: onboardingStepBodies['workspace-memory'],
    autoSkipIfTargetMissing: true,
  },
  {
    id: 'workspace-copilot',
    route: 'project',
    targetId: 'workspace-copilot-panel',
    title: {
      en: 'Copilot stays attached while the project runs',
      zh: 'Copilot 会在项目运行期间一直保持连接',
    },
    body: onboardingStepBodies['workspace-copilot'],
  },
  {
    id: 'workspace-copilot-modes',
    route: 'project',
    targetId: 'quest-copilot-mode-tabs',
    title: {
      en: 'Studio and Chat are two different surfaces',
      zh: 'Studio 和 Chat 是两种不同的工作面',
    },
    body: onboardingStepBodies['workspace-copilot-modes'],
    placement: 'left',
  },
  {
    id: 'workspace-next-action',
    route: 'project',
    targetId: 'workspace-copilot-panel',
    title: {
      en: 'This is where human collaboration takes over',
      zh: '这里就是人类协作真正接手的地方',
    },
    body: onboardingStepBodies['workspace-next-action'],
  },
  {
    id: 'workspace-open-admin',
    route: 'project',
    targetId: 'workspace-navbar',
    title: {
      en: 'The tutorial ends with the operator surface',
      zh: '教程最后会收尾到运维控制面',
    },
    body: onboardingStepBodies['workspace-open-admin'],
    navigateTo: '/settings/summary',
    advanceMode: 'wait_for_route',
    waitForRoute: /^\/settings\/summary$/,
  },
  {
    id: 'admin-summary',
    route: 'settings',
    routePattern: /^\/settings\/summary$/,
    targetId: 'settings-admin-summary-surface',
    title: {
      en: 'Admin Summary is the system overview',
      zh: 'Admin Summary 是系统总览页',
    },
    body: onboardingStepBodies['admin-summary'],
    navigateTo: '/settings/quests',
    advanceMode: 'wait_for_route',
    waitForRoute: /^\/settings\/quests(?:\/[^/]+)?$/,
    placement: 'top',
    autoSkipIfTargetMissing: true,
  },
  {
    id: 'admin-quests',
    route: 'settings',
    routePattern: /^\/settings\/quests(?:\/[^/]+)?$/,
    targetId: 'settings-admin-quests-surface',
    title: {
      en: 'Quest Supervision is the operator table',
      zh: 'Quest Supervision 是运维总表',
    },
    body: onboardingStepBodies['admin-quests'],
    placement: 'top',
    autoSkipIfTargetMissing: true,
  },
  {
    id: 'admin-copilot',
    route: 'settings',
    routePattern: /^\/settings\/quests(?:\/[^/]+)?$/,
    targetId: 'settings-admin-copilot-recipes',
    title: {
      en: 'Admin Copilot can inspect and prepare ISSUE / PR handoffs',
      zh: 'Admin Copilot 可以自检并走 ISSUE / PR 路线',
    },
    body: onboardingStepBodies['admin-copilot'],
    placement: 'left',
  },
]

function queryTarget(id?: string | null) {
  if (!id || typeof document === 'undefined') return null
  return document.querySelector<HTMLElement>(`[data-onboarding-id="${id}"]`)
}

function stepNeedsCopilotPanel(step: OnboardingStep | null) {
  if (!step) return false
  const ids = [step.targetId, step.actionTargetId, step.waitForElementId].filter(Boolean)
  return ids.some((id) => id === 'workspace-copilot-panel' || id === 'quest-copilot-mode-tabs')
}

function stepNeedsAdminCopilot(step: OnboardingStep | null) {
  if (!step) return false
  const ids = [step.targetId, step.actionTargetId, step.waitForElementId].filter(Boolean)
  return ids.some((id) => id === 'settings-admin-copilot-rail' || id === 'settings-admin-copilot-recipes')
}

function isVerticalScrollable(element: HTMLElement) {
  const style = window.getComputedStyle(element)
  const overflowY = style.overflowY
  return /(auto|scroll|overlay)/.test(overflowY) && element.scrollHeight > element.clientHeight + 1
}

function scrollTargetIntoViewVerticalOnly(target: HTMLElement) {
  if (typeof window === 'undefined') return

  const padding = 28
  const ancestors: HTMLElement[] = []
  let node = target.parentElement

  while (node) {
    if (isVerticalScrollable(node)) {
      ancestors.push(node)
    }
    node = node.parentElement
  }

  for (const container of ancestors) {
    const targetRect = target.getBoundingClientRect()
    const containerRect = container.getBoundingClientRect()
    const minTop = containerRect.top + padding
    const maxBottom = containerRect.bottom - padding

    if (targetRect.top < minTop) {
      container.scrollTo({
        top: container.scrollTop + (targetRect.top - minTop),
        behavior: 'smooth',
      })
      continue
    }

    if (targetRect.bottom > maxBottom) {
      container.scrollTo({
        top: container.scrollTop + (targetRect.bottom - maxBottom),
        behavior: 'smooth',
      })
    }
  }

  const rect = target.getBoundingClientRect()
  const viewportTop = padding
  const viewportBottom = window.innerHeight - padding

  if (rect.top < viewportTop || rect.bottom > viewportBottom) {
    const targetTop = Math.max(
      0,
      window.scrollY + rect.top - Math.max(72, (window.innerHeight - rect.height) / 2)
    )
    window.scrollTo({
      top: targetTop,
      behavior: 'smooth',
    })
  }
}

function triggerTargetAction(id?: string | null) {
  const target = queryTarget(id)
  if (!target) return false
  const isFileTreeNode = Boolean(target.closest('[data-node-id]'))
  if (isFileTreeNode) {
    target.dispatchEvent(
      new MouseEvent('click', {
        bubbles: true,
        cancelable: true,
        view: window,
        detail: 1,
      })
    )
    target.dispatchEvent(
      new MouseEvent('click', {
        bubbles: true,
        cancelable: true,
        view: window,
        detail: 2,
      })
    )
    target.dispatchEvent(
      new MouseEvent('dblclick', {
        bubbles: true,
        cancelable: true,
        view: window,
        detail: 2,
      })
    )
    return true
  }
  if (typeof target.click === 'function') {
    target.click()
    return true
  }
  target.dispatchEvent(
    new MouseEvent('click', {
      bubbles: true,
      cancelable: true,
      view: window,
    })
  )
  return true
}

function routeMatches(step: OnboardingStep, pathname: string) {
  const baseMatch =
    step.route === 'landing'
      ? pathname === '/'
      : step.route === 'project'
        ? /^\/(projects\/[^/]+|tutorial\/demo\/[^/]+)$/.test(pathname)
        : /^\/settings(?:\/.*)?$/.test(pathname)
  if (!baseMatch) return false
  if (step.routePattern) {
    return step.routePattern.test(pathname)
  }
  return true
}

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max)
}

function resolveCardPosition(args: {
  targetRect: DOMRect | null
  cardWidth: number
  cardHeight: number
  placement: OnboardingStep['placement']
}) {
  const margin = 16
  const gap = 18
  const viewportWidth = typeof window !== 'undefined' ? window.innerWidth : 1280
  const viewportHeight = typeof window !== 'undefined' ? window.innerHeight : 720

  if (!args.targetRect || args.placement === 'center') {
    return {
      top: clamp((viewportHeight - args.cardHeight) / 2, margin, Math.max(margin, viewportHeight - margin - args.cardHeight)),
      left: clamp((viewportWidth - args.cardWidth) / 2, margin, Math.max(margin, viewportWidth - margin - args.cardWidth)),
    }
  }

  const rect = args.targetRect
  const canPlaceBottom = rect.bottom + gap + args.cardHeight <= viewportHeight - margin
  const canPlaceTop = rect.top - gap - args.cardHeight >= margin
  const canPlaceRight = rect.right + gap + args.cardWidth <= viewportWidth - margin
  const canPlaceLeft = rect.left - gap - args.cardWidth >= margin

  let placement = args.placement || 'auto'
  if (placement === 'auto') {
    if (canPlaceBottom) placement = 'bottom'
    else if (canPlaceTop) placement = 'top'
    else if (canPlaceRight) placement = 'right'
    else if (canPlaceLeft) placement = 'left'
    else placement = 'bottom'
  }

  let top = rect.bottom + gap
  let left = rect.left + rect.width / 2 - args.cardWidth / 2

  if (placement === 'top') {
    top = rect.top - args.cardHeight - gap
  } else if (placement === 'right') {
    top = rect.top + rect.height / 2 - args.cardHeight / 2
    left = rect.right + gap
  } else if (placement === 'left') {
    top = rect.top + rect.height / 2 - args.cardHeight / 2
    left = rect.left - args.cardWidth - gap
  }

  return {
    top: clamp(top, margin, Math.max(margin, viewportHeight - margin - args.cardHeight)),
    left: clamp(left, margin, Math.max(margin, viewportWidth - margin - args.cardWidth)),
  }
}

function OnboardingChooser({
  onStart,
  onSkip,
  onNever,
}: {
  onStart: (language: OnboardingLanguage) => void
  onSkip: () => void
  onNever: () => void
}) {
  return (
    <div className={cn('fixed inset-0 flex items-center justify-center p-4', ONBOARDING_LAYER_CLASS)}>
      <div className="absolute inset-0 bg-[rgba(17,19,24,0.52)] backdrop-blur-[2px]" />
      <div className="relative w-full max-w-[520px] rounded-[28px] border border-white/15 bg-[rgba(255,250,245,0.96)] p-6 shadow-[0_32px_100px_-48px_rgba(15,23,42,0.55)] backdrop-blur-xl">
        <div className="flex items-center gap-3 text-[rgba(92,78,58,0.95)]">
          <div className="flex h-11 w-11 items-center justify-center rounded-full bg-[rgba(199,173,150,0.24)]">
            <Languages className="h-5 w-5" />
          </div>
          <div>
            <div className="text-sm font-semibold uppercase tracking-[0.18em] text-[rgba(126,108,82,0.76)]">
              First Run
            </div>
            <h2 className="mt-1 text-xl font-semibold tracking-tight">
              选择首次教程语言 / Choose Your First Tutorial
            </h2>
          </div>
        </div>

        <p className="mt-4 text-sm leading-7 text-[rgba(70,61,49,0.84)]">
          DeepScientist 可以像游戏教程一样，带你一步步完成第一次使用。
          Choose Chinese or English, skip for now, or turn the reminder off.
        </p>

        <div className="mt-6 grid gap-3 sm:grid-cols-2">
          <button
            type="button"
            onClick={() => onStart('zh')}
            className="rounded-[20px] border border-[rgba(126,77,42,0.16)] bg-[rgba(244,239,233,0.76)] px-4 py-4 text-left transition hover:border-[rgba(126,77,42,0.28)] hover:bg-white"
          >
            <div className="text-sm font-semibold text-[rgba(38,36,33,0.95)]">中文讲解</div>
            <div className="mt-1 text-[12px] leading-6 text-[rgba(86,82,77,0.82)]">
              一步步说明页面结构、创建项目和工作区的基本用法。
            </div>
          </button>
          <button
            type="button"
            onClick={() => onStart('en')}
            className="rounded-[20px] border border-[rgba(126,77,42,0.16)] bg-[rgba(244,239,233,0.76)] px-4 py-4 text-left transition hover:border-[rgba(126,77,42,0.28)] hover:bg-white"
          >
            <div className="text-sm font-semibold text-[rgba(38,36,33,0.95)]">English guide</div>
            <div className="mt-1 text-[12px] leading-6 text-[rgba(86,82,77,0.82)]">
              Walk through the first run, project creation flow, and workspace basics.
            </div>
          </button>
        </div>

        <div className="mt-5 flex flex-col gap-2 sm:flex-row sm:justify-end">
          <Button variant="ghost" onClick={onSkip}>
            暂时跳过 / Skip for now
          </Button>
          <Button variant="secondary" onClick={onNever}>
            不再提醒 / Do not remind again
          </Button>
        </div>
      </div>
    </div>
  )
}

export function OnboardingOverlay() {
  const location = useLocation()
  const navigate = useNavigate()
  const {
    hydrated,
    status,
    stepIndex,
    language,
    startedFrom,
    hydrate,
    startTutorial,
    nextStep,
    previousStep,
    skipFirstRun,
    neverShowAgain,
    close,
    completeTutorial,
  } = useOnboardingStore((state) => ({
    hydrated: state.hydrated,
    status: state.status,
    stepIndex: state.stepIndex,
    language: state.language,
    startedFrom: state.startedFrom,
    hydrate: state.hydrate,
    startTutorial: state.startTutorial,
    nextStep: state.nextStep,
    previousStep: state.previousStep,
    skipFirstRun: state.skipFirstRun,
    neverShowAgain: state.neverShowAgain,
    close: state.close,
    completeTutorial: state.completeTutorial,
  }))

  const [targetRect, setTargetRect] = React.useState<DOMRect | null>(null)
  const [targetFound, setTargetFound] = React.useState(false)
  const [cardSize, setCardSize] = React.useState({ width: 466, height: 260 })
  const isMobileViewport = useMobileViewport({
    maxWidth: ONBOARDING_MOBILE_VIEWPORT_MAX_WIDTH,
  })
  const startAdminOpsSession = useAdminOpsStore((state) => state.startFreshSession)
  const cardRef = React.useRef<HTMLDivElement | null>(null)
  const step = status === 'running' ? ONBOARDING_STEPS[stepIndex] ?? null : null
  const activeLanguage = language === 'zh' || language === 'en' ? language : 'en'
  const copy = COPY[activeLanguage]
  const isGuidedProjectRoute = /^\/projects\/demo-/.test(location.pathname)

  const exitTutorial = React.useCallback(
    (mode: 'close' | 'complete') => {
      if (mode === 'complete') {
        completeTutorial()
      } else {
        close()
      }
      if (isGuidedProjectRoute) {
        window.setTimeout(() => {
          navigate('/', { replace: false })
        }, 0)
      }
    },
    [close, completeTutorial, isGuidedProjectRoute, navigate]
  )

  const advance = React.useCallback(() => {
    if (stepIndex >= ONBOARDING_STEPS.length - 1) {
      exitTutorial('complete')
      return
    }
    nextStep()
  }, [exitTutorial, nextStep, stepIndex])

  const advanceWithAction = React.useCallback(() => {
    if (status !== 'running' || !step) return
    if (step.navigateTo) {
      navigate(step.navigateTo)
      return
    }
    if (step.actionTargetId || (step.advanceMode === 'wait_for_element' && step.targetId)) {
      const acted = triggerTargetAction(step.actionTargetId || step.targetId)
      if (!acted) {
        advance()
      }
      return
    }
    advance()
  }, [advance, navigate, status, step])

  React.useEffect(() => {
    hydrate()
  }, [hydrate])

  React.useEffect(() => {
    if (isMobileViewport && status !== 'idle') {
      close()
    }
  }, [close, isMobileViewport, status])

  React.useEffect(() => {
    if (status !== 'running' || !step) {
      setTargetRect(null)
      setTargetFound(false)
      return
    }

    let active = true

    const updateTarget = () => {
      const target = queryTarget(step.targetId)
      if (!active) return
      setTargetFound(Boolean(target))
      setTargetRect(target ? target.getBoundingClientRect() : null)
    }

    updateTarget()
    const intervalId = window.setInterval(updateTarget, 220)
    window.addEventListener('resize', updateTarget)
    window.addEventListener('scroll', updateTarget, true)

    return () => {
      active = false
      window.clearInterval(intervalId)
      window.removeEventListener('resize', updateTarget)
      window.removeEventListener('scroll', updateTarget, true)
    }
  }, [status, step])

  React.useEffect(() => {
    if (!step?.targetId) return
    const target = queryTarget(step.targetId)
    if (!target) return
    scrollTargetIntoViewVerticalOnly(target)
  }, [step?.id, step?.targetId])

  React.useEffect(() => {
    if (typeof document === 'undefined') return
    if (status === 'idle') return

    const htmlOverflowX = document.documentElement.style.overflowX
    const bodyOverflowX = document.body.style.overflowX

    document.documentElement.style.overflowX = 'hidden'
    document.body.style.overflowX = 'hidden'

    return () => {
      document.documentElement.style.overflowX = htmlOverflowX
      document.body.style.overflowX = bodyOverflowX
    }
  }, [status])

  React.useEffect(() => {
    if (!cardRef.current) return
    const update = () => {
      if (!cardRef.current) return
      const rect = cardRef.current.getBoundingClientRect()
      setCardSize((current) => {
        const next = { width: rect.width, height: rect.height }
        if (Math.abs(current.width - next.width) < 1 && Math.abs(current.height - next.height) < 1) {
          return current
        }
        return next
      })
    }
    update()
    const observer = new ResizeObserver(update)
    observer.observe(cardRef.current)
    return () => observer.disconnect()
  }, [step?.id, status])

  React.useEffect(() => {
    if (status !== 'running' || !step) return
    if (step.advanceMode !== 'wait_for_route' || !step.waitForRoute) return
    if (!step.waitForRoute.test(location.pathname)) return
    const timer = window.setTimeout(() => advance(), 120)
    return () => window.clearTimeout(timer)
  }, [advance, location.pathname, status, step])

  React.useEffect(() => {
    if (status !== 'running' || !step) return
    if (step.advanceMode !== 'wait_for_element' || !step.waitForElementId) return
    if (!queryTarget(step.waitForElementId)) return
    const timer = window.setTimeout(() => advance(), 120)
    return () => window.clearTimeout(timer)
  }, [advance, status, step, targetRect])

  React.useEffect(() => {
    if (status !== 'running' || !step) return
    if (step.advanceMode !== 'wait_for_element_missing' || !step.waitForElementId) return
    if (queryTarget(step.waitForElementId)) return
    const timer = window.setTimeout(() => advance(), 120)
    return () => window.clearTimeout(timer)
  }, [advance, status, step, targetRect])

  React.useEffect(() => {
    if (status !== 'running' || !step) return
    if (!step.autoSkipIfTargetMissing) return
    if (!routeMatches(step, location.pathname)) return
    if (targetFound) return
    const timer = window.setTimeout(() => advance(), 900)
    return () => window.clearTimeout(timer)
  }, [advance, location.pathname, status, step, targetFound])

  React.useEffect(() => {
    if (status !== 'running' || !step) return
    if (!routeMatches(step, location.pathname)) return
    if (!stepNeedsCopilotPanel(step)) return

    let cancelled = false

    const ensureCopilot = () => {
      if (cancelled) return
      const relevantTargetId =
        step.targetId === 'quest-copilot-mode-tabs'
          ? 'quest-copilot-mode-tabs'
          : 'workspace-copilot-panel'
      if (queryTarget(relevantTargetId)) return
      window.dispatchEvent(
        new CustomEvent('ds:copilot:open', {
          detail: {
            focus: false,
            source: 'onboarding',
          },
        })
      )
    }

    ensureCopilot()
    const intervalId = window.setInterval(ensureCopilot, 700)
    return () => {
      cancelled = true
      window.clearInterval(intervalId)
    }
  }, [location.pathname, status, step, targetFound])

  React.useEffect(() => {
    if (status !== 'running' || !step) return
    if (!routeMatches(step, location.pathname)) return
    if (!stepNeedsAdminCopilot(step)) return

    let cancelled = false

    const ensureAdminCopilot = () => {
      if (cancelled) return
      const relevantTargetId =
        step.targetId === 'settings-admin-copilot-recipes'
          ? 'settings-admin-copilot-recipes'
          : 'settings-admin-copilot-rail'
      if (queryTarget(relevantTargetId)) return
      startAdminOpsSession(location.pathname || '/settings')
    }

    ensureAdminCopilot()
    const intervalId = window.setInterval(ensureAdminCopilot, 700)
    return () => {
      cancelled = true
      window.clearInterval(intervalId)
    }
  }, [location.pathname, startAdminOpsSession, status, step, targetFound])

  if (!hydrated) {
    return null
  }

  if (isMobileViewport) {
    return null
  }

  if (status === 'choosing_language') {
    return (
      <OnboardingChooser
        onStart={(nextLanguage) => startTutorial(nextLanguage, location.pathname, startedFrom || 'auto')}
        onSkip={skipFirstRun}
        onNever={neverShowAgain}
      />
    )
  }

  if (status !== 'running' || !step) {
    return null
  }

  const shouldRenderForRoute = routeMatches(step, location.pathname)
  if (!shouldRenderForRoute && step.advanceMode !== 'wait_for_route') {
    return null
  }

  const isActionStep =
    step.advanceMode === 'wait_for_element' ||
    step.advanceMode === 'wait_for_element_missing' ||
    step.advanceMode === 'wait_for_route'
  const highlightPadding = 8
  const viewportWidth = typeof window !== 'undefined' ? window.innerWidth : 1280
  const viewportHeight = typeof window !== 'undefined' ? window.innerHeight : 720
  const overlayRect = targetRect
    ? {
        top: Math.max(0, targetRect.top - highlightPadding),
        left: Math.max(0, targetRect.left - highlightPadding),
        right: Math.min(viewportWidth, targetRect.right + highlightPadding),
        bottom: Math.min(viewportHeight, targetRect.bottom + highlightPadding),
      }
    : null
  const haloRect = overlayRect
    ? {
        top: Math.max(0, overlayRect.top - 14),
        left: Math.max(0, overlayRect.left - 14),
        width: Math.min(viewportWidth, overlayRect.right + 14) - Math.max(0, overlayRect.left - 14),
        height: Math.min(viewportHeight, overlayRect.bottom + 14) - Math.max(0, overlayRect.top - 14),
      }
    : null
  const focusPillPosition = overlayRect
    ? {
        top: overlayRect.top > 56 ? overlayRect.top - 44 : overlayRect.bottom + 12,
        left: clamp(overlayRect.left, 16, Math.max(16, viewportWidth - 180)),
      }
    : null
  const spotlightOrbPosition = overlayRect
    ? {
        top: Math.max(10, overlayRect.top - 26),
        left: overlayRect.left + (overlayRect.right - overlayRect.left) / 2 - 11,
      }
    : null
  const cardPosition = resolveCardPosition({
    targetRect,
    cardWidth: cardSize.width,
    cardHeight: cardSize.height,
    placement: step.placement || 'auto',
  })
  const tutorialBadge = activeLanguage === 'zh' ? '首次教程' : 'Guided Tutorial'
  const routeBadge =
    step.route === 'landing'
      ? activeLanguage === 'zh'
        ? '启动页'
        : 'Launch Surface'
      : step.route === 'project'
        ? activeLanguage === 'zh'
          ? '项目工作区'
          : 'Project Workspace'
        : activeLanguage === 'zh'
          ? '设置与管理'
          : 'Settings & Admin'
  const focusLabel = activeLanguage === 'zh' ? '请看这里' : 'Look here'
  const infoMessage = step.hint?.[activeLanguage]
    ?? (isActionStep ? (targetFound ? copy.waitForAction : copy.waitingTarget) : copy.readingHint)

  return (
    <div className={cn('pointer-events-none fixed inset-0', ONBOARDING_LAYER_CLASS)}>
      <style>{ONBOARDING_ANIMATION_STYLES}</style>
      {overlayRect ? (
        <>
          <div
            className="fixed left-0 top-0 bg-[rgba(9,11,15,0.7)] backdrop-blur-[2px] pointer-events-auto"
            style={{ width: '100vw', height: overlayRect.top }}
          />
          <div
            className="fixed left-0 bg-[rgba(9,11,15,0.7)] backdrop-blur-[2px] pointer-events-auto"
            style={{
              top: overlayRect.top,
              width: overlayRect.left,
              height: overlayRect.bottom - overlayRect.top,
            }}
          />
          <div
            className="fixed bg-[rgba(9,11,15,0.7)] backdrop-blur-[2px] pointer-events-auto"
            style={{
              top: overlayRect.top,
              left: overlayRect.right,
              width: Math.max(0, viewportWidth - overlayRect.right),
              height: overlayRect.bottom - overlayRect.top,
            }}
          />
          <div
            className="fixed left-0 bg-[rgba(9,11,15,0.7)] backdrop-blur-[2px] pointer-events-auto"
            style={{
              top: overlayRect.bottom,
              width: '100vw',
              height: Math.max(0, viewportHeight - overlayRect.bottom),
            }}
          />
          {haloRect ? (
            <div
              className="pointer-events-none fixed rounded-[30px] bg-[radial-gradient(circle_at_center,rgba(255,243,224,0.22)_0%,rgba(255,243,224,0.1)_42%,rgba(255,243,224,0.03)_62%,transparent_78%)] blur-[4px]"
              style={{
                top: haloRect.top,
                left: haloRect.left,
                width: haloRect.width,
                height: haloRect.height,
                animation: 'ds-onboarding-halo 1.9s ease-in-out infinite',
              }}
            />
          ) : null}
          <div
            className="pointer-events-none fixed rounded-[26px] border border-[rgba(255,249,239,0.94)] shadow-[0_0_0_1px_rgba(255,255,255,0.35),0_0_24px_rgba(255,230,197,0.24)]"
            style={{
              top: overlayRect.top,
              left: overlayRect.left,
              width: Math.max(0, overlayRect.right - overlayRect.left),
              height: Math.max(0, overlayRect.bottom - overlayRect.top),
            }}
          />
          {focusPillPosition ? (
            <div
              className="pointer-events-none fixed inline-flex items-center gap-2 rounded-full border border-[rgba(255,247,232,0.28)] bg-[rgba(255,248,239,0.14)] px-3 py-1.5 text-[11px] font-semibold tracking-[0.08em] text-white shadow-[0_16px_40px_-28px_rgba(0,0,0,0.58)] backdrop-blur-[10px]"
              style={{
                top: focusPillPosition.top,
                left: focusPillPosition.left,
                animation: 'ds-onboarding-float 2.3s ease-in-out infinite',
              }}
            >
              <span className="h-2 w-2 rounded-full bg-[rgba(255,233,200,0.96)] shadow-[0_0_14px_rgba(255,223,182,0.9)]" />
              {focusLabel}
            </div>
          ) : null}
          {spotlightOrbPosition ? (
            <div
              className="pointer-events-none fixed h-[22px] w-[22px] rounded-full bg-[radial-gradient(circle,rgba(255,244,220,0.98)_0%,rgba(255,223,182,0.85)_42%,rgba(255,223,182,0.16)_72%,transparent_100%)] shadow-[0_0_28px_rgba(255,224,182,0.88)]"
              style={{
                top: spotlightOrbPosition.top,
                left: spotlightOrbPosition.left,
                animation: 'ds-onboarding-float 1.8s ease-in-out infinite',
              }}
            />
          ) : null}
        </>
      ) : (
        <div className="absolute inset-0 bg-[rgba(9,11,15,0.72)] backdrop-blur-[3px] pointer-events-auto" />
      )}

      <div
        ref={cardRef}
        className="pointer-events-auto fixed w-[min(466px,calc(100vw-32px))] overflow-hidden rounded-[30px] border border-[rgba(255,255,255,0.28)] bg-[linear-gradient(180deg,rgba(255,252,248,0.98),rgba(246,239,231,0.95))] p-5 shadow-[0_32px_110px_-44px_rgba(15,23,42,0.62)] backdrop-blur-xl"
        style={{
          top: cardPosition.top,
          left: cardPosition.left,
        }}
      >
        <div className="absolute inset-x-0 top-0 h-px bg-[linear-gradient(90deg,transparent,rgba(160,133,103,0.4),transparent)]" />
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[rgba(199,173,150,0.22)] text-[rgba(92,78,58,0.95)]">
            {step.route === 'landing' ? <Compass className="h-5 w-5" /> : <Sparkles className="h-5 w-5" />}
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center justify-between gap-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="inline-flex rounded-full border border-[rgba(148,118,82,0.14)] bg-[rgba(255,255,255,0.58)] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-[rgba(126,108,82,0.86)]">
                  {tutorialBadge}
                </span>
                <span className="inline-flex rounded-full border border-[rgba(148,118,82,0.1)] bg-[rgba(244,239,233,0.72)] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-[rgba(126,108,82,0.72)]">
                  {routeBadge}
                </span>
              </div>
              <button
                type="button"
                onClick={() => exitTutorial('close')}
                className="inline-flex h-8 w-8 items-center justify-center rounded-full text-[rgba(107,103,97,0.76)] transition hover:bg-black/[0.04] hover:text-[rgba(38,36,33,0.95)]"
                aria-label="Close tutorial"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="mt-3 text-[11px] font-semibold uppercase tracking-[0.18em] text-[rgba(126,108,82,0.76)]">
              {copy.progress(stepIndex + 1, ONBOARDING_STEPS.length)}
            </div>
            <h3 className="mt-2 text-lg font-semibold tracking-tight text-[rgba(38,36,33,0.96)]">
              {step.title[activeLanguage]}
            </h3>
            <div className="mt-2 text-sm leading-7 text-[rgba(70,61,49,0.84)]">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  p: ({ children }) => <p className="mb-3 last:mb-0">{children}</p>,
                  ul: ({ children }) => <ul className="mb-3 list-disc space-y-1 pl-5 last:mb-0">{children}</ul>,
                  ol: ({ children }) => <ol className="mb-3 list-decimal space-y-1 pl-5 last:mb-0">{children}</ol>,
                  li: ({ children }) => <li>{children}</li>,
                  strong: ({ children }) => <strong className="font-semibold text-[rgba(38,36,33,0.96)]">{children}</strong>,
                  code: ({ children }) => (
                    <code className="rounded bg-black/[0.05] px-1.5 py-0.5 text-[12px] text-[rgba(58,50,40,0.92)]">
                      {children}
                    </code>
                  ),
                }}
              >
                {step.body[activeLanguage]}
              </ReactMarkdown>
            </div>
            {isActionStep ? (
              <div className="mt-4 rounded-[20px] border border-[rgba(126,77,42,0.12)] bg-[linear-gradient(180deg,rgba(251,248,244,0.92),rgba(241,234,225,0.82))] px-3.5 py-3 text-[12px] leading-6 text-[rgba(86,82,77,0.84)] shadow-[inset_0_1px_0_rgba(255,255,255,0.45)]">
                {infoMessage}
              </div>
            ) : null}
            {!isActionStep ? (
              <div className="mt-4 rounded-[20px] border border-[rgba(126,77,42,0.12)] bg-[linear-gradient(180deg,rgba(251,248,244,0.92),rgba(241,234,225,0.82))] px-3.5 py-3 text-[12px] leading-6 text-[rgba(86,82,77,0.84)] shadow-[inset_0_1px_0_rgba(255,255,255,0.45)]">
                {infoMessage}
              </div>
            ) : null}
          </div>
        </div>

        <div className={cn('mt-6 flex gap-2', stepIndex === 0 ? 'justify-end' : 'justify-between')}>
          {stepIndex > 0 ? (
            <Button variant="ghost" onClick={previousStep}>
              <ChevronLeft className="mr-1 h-4 w-4" />
              {copy.back}
            </Button>
          ) : (
            <span />
          )}
          <div className="flex items-center gap-2">
            <Button variant="secondary" onClick={() => exitTutorial('close')}>
              <BookOpen className="mr-2 h-4 w-4" />
              {copy.skip}
            </Button>
            <Button onClick={isActionStep ? advanceWithAction : advance}>
              {stepIndex >= ONBOARDING_STEPS.length - 1 ? copy.finish : copy.next}
              {stepIndex < ONBOARDING_STEPS.length - 1 ? <ChevronRight className="ml-1 h-4 w-4" /> : null}
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}

export default OnboardingOverlay
