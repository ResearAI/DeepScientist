import { createContext, useContext, useEffect, useMemo, useRef, type ReactNode } from 'react'

import { client } from '@/lib/api'
import { useUILanguageStore } from '@/lib/stores/ui-language'
import type { Locale } from '@/types'

function resolveLegacyLocale(value: string | null | undefined): Locale {
  return String(value || '').toLowerCase().startsWith('zh') ? 'zh' : 'en'
}

const messages = {
  en: {
    brand: 'DeepScientist',
    projectsTitle: 'Home',
    docsTitle: 'Docs',
    settingsTitle: 'Settings',
    sharedApiHint: 'Web and TUI share the same daemon API and live event stream.',
    settingsHint: 'Edit runtime config, validate it, and keep the local daemon predictable.',
    searchPlaceholder: 'Search projects, project ids, branches, and notes…',
    navProjects: 'Home',
    navDocs: 'Docs',
    navSettings: 'Settings',
    landingEyebrow: 'Automated Research',
    landingTitle: 'Climb from local clues to global insight.',
    landingBody: 'DeepScientist keeps the browser, TUI, and daemon on one local session while every project lives in its own Git-backed workspace.',
    landingStart: 'Start Research',
    landingOpen: 'Open Project',
    landingDaemon: 'Daemon',
    landingShared: 'Shared with TUI',
    landingQuestCount: 'Local projects',
    landingSceneTitle: 'Exploring Unknown Scientific Frontiers',
    landingMetricProjects: 'Project repos',
    landingMetricPending: 'Pending',
    landingMetricDaemon: 'Daemon',
    landingNodeLocal: 'Local optimum',
    landingNodeMid: 'Midpoint',
    landingNodeGlobal: 'Global optimum',
    openQuestTitle: 'Open Project',
    openQuestBody: 'Resume a local project and reopen its workspace.',
    openQuestSearchPlaceholder: 'Search by title, project id, branch, or notes…',
    openQuestEmpty: 'No matching projects.',
    openQuestNoProjects: 'No projects were found in the current DeepScientist home.',
    openQuestCurrentHome: 'Current home',
    openQuestHomeHint: 'This list only shows quests stored under the active DeepScientist home. If your quests live elsewhere, relaunch with `ds --home <path>`.',
    openQuestLatest: 'Latest',
    openQuestUpdated: 'Updated',
    openQuestPending: 'Pending',
    openQuestBranch: 'Branch',
    openQuestNoDescription: 'Open the workspace to continue.',
    openQuestDelete: 'Delete project',
    openQuestDeleteTitle: 'Delete project?',
    openQuestDeleteBody: 'This will permanently delete the project repo on disk. This cannot be undone.',
    openQuestDeleteConfirm: 'Delete',
    openQuestDeleteCancel: 'Cancel',
    heroTitle: 'Local-first research workspaces',
    heroBody:
      'Open a project to keep the Codex stream alive in the browser, share the same backend session with the TUI, and inspect files, workflow, and artifacts in one place.',
    heroGuide:
      'Guide: sending a direct request from the projects page creates a new project repo; sending inside a bound project continues that project conversation.',
    createProject: 'New project',
    createDialogTitle: 'Create a project',
    createDialogBody: 'Start from a direct research goal. DeepScientist will create a project repository and open the workspace immediately.',
    createProjectTitle: 'Project title',
    createProjectGoal: 'Goal / request',
    createProjectAction: 'Create and open',
    cancel: 'Cancel',
    quickRequest: 'Direct request',
    quickRequestBody: 'No bound project yet? Send a request here and DeepScientist will create a new project automatically.',
    quickRequestAction: 'Start request',
    openProject: 'Open workspace',
    emptyProjects: 'No projects yet. Start with a direct request or create a workspace card.',
    status: 'Status',
    branch: 'Branch',
    metric: 'Metric',
    updated: 'Updated',
    pending: 'Pending',
    files: 'Files',
    memory: 'Memory',
    workflow: 'Workflow',
    graph: 'Graph',
    overview: 'Overview',
    copilot: 'Copilot',
    activity: 'Activity',
    directTab: 'Studio',
    groupTab: 'Chat',
    directTabHint: 'Shows the full studio trace: tool work, artifacts, milestones, and conversation from the shared daemon session.',
    groupTabHint: 'Shows only the conversation thread, like a focused chat surface.',
    toolActivity: 'Tool activity',
    toolActivityBody: 'Read, search, shell, and write operations surface here while the live stream stays attached.',
    showToolEffect: 'Show tool strip',
    hideToolEffect: 'Hide tool strip',
    toolLive: 'Live',
    toolDone: 'Done',
    toolLiveBody: 'This action is arriving from the same daemon session and updates in place while Codex is still working.',
    toolResultBody: 'This tool step has finished and stays pinned here until the next live tool event arrives.',
    showActivity: 'Show activity',
    hideActivity: 'Hide activity',
    jumpToLatest: 'Jump to latest',
    emptyCopilotTitle: 'Studio is ready',
    emptyCopilotBody: 'The stream stays attached here. Ask for a status summary, request a graph update, inspect tool traces, or continue the current research thread directly.',
    emptyGroupTitle: 'Chat is ready',
    emptyGroupBody: 'This view keeps only the dialogue thread. Switch to Studio if you want tool traces, artifacts, and run events.',
    activityBody: 'Recent runs, artifacts, decisions, and changed files from the same daemon session.',
    streamingNow: 'Streaming live…',
    copyCode: 'Copy',
    copiedCode: 'Copied',
    latestAssistant: 'Latest assistant reply',
    workspaceGuide: 'This workspace keeps the same daemon session and streams updates continuously after Codex responds.',
    sameSession: 'Same daemon session as TUI',
    streamLive: 'Live stream attached',
    replyTarget: 'Reply target',
    composerPlaceholder: 'Continue this project, ask for a summary, or send /status, /graph, /summary …',
    commandHelp: 'Press Ctrl/Cmd + Enter to send.',
    openDocs: 'Open docs',
    openSettings: 'Open settings',
    loadProjectsFailed: 'Failed to load projects.',
    createFailed: 'Failed to create project.',
    deleteFailed: 'Failed to delete project.',
    loading: 'Loading…',
    recentArtifacts: 'Recent artifacts',
    recentRuns: 'Recent runs',
    changedFiles: 'Changed files',
    guideCardTitle: 'Unified local surface',
    guideCardBody:
      'The project page, TUI, and connector feeds now read the same daemon events. Refreshing the page does not switch APIs.',
    projectNotFound: 'Project not found.',
    explorer: 'Explorer',
    documents: 'Documents',
    noDocuments: 'No documents yet.',
    noMemory: 'No memory cards yet.',
    noArtifacts: 'No artifacts yet.',
    noRuns: 'No runs yet.',
    noChangedFiles: 'No changed files yet.',
    noWorkflow: 'Workflow cards appear after the first meaningful run.',
    noExplorer: 'Project files will appear here after the project initializes.',
    workingTree: 'Working tree',
    suggestions: 'Suggestions',
    refresh: 'Refresh',
    send: 'Send',
    directRequestTitlePlaceholder: 'Optional title',
    directRequestGoalPlaceholder: 'Describe the research request or next objective…',
    projectGoalPlaceholder: 'Describe the project goal, hypothesis, or direct request…',
  },
  zh: {
    brand: 'DeepScientist',
    projectsTitle: '首页',
    docsTitle: '文档',
    settingsTitle: '设置',
    sharedApiHint: 'Web 与 TUI 共用同一个 daemon API 与实时事件流。',
    settingsHint: '在这里编辑运行时配置、执行校验，并保持本地 daemon 行为可预测。',
    searchPlaceholder: '搜索项目、项目 ID、分支与状态说明…',
    navProjects: '首页',
    navDocs: '文档',
    navSettings: '设置',
    landingEyebrow: '自动化科研',
    landingTitle: '从局部线索攀登到全局洞见。',
    landingBody: 'DeepScientist 让浏览器、TUI 与 daemon 共用同一本地会话，并让每个项目都落在独立的 Git 工作区里。',
    landingStart: '开始研究',
    landingOpen: '打开项目',
    landingDaemon: 'Daemon',
    landingShared: '与 TUI 共用',
    landingQuestCount: '本地项目',
    landingSceneTitle: '探索未知科学前沿',
    landingMetricProjects: '项目仓库',
    landingMetricPending: '待处理',
    landingMetricDaemon: 'Daemon',
    landingNodeLocal: '局部最优',
    landingNodeMid: '中段跃迁',
    landingNodeGlobal: '全局最优',
    openQuestTitle: '打开项目',
    openQuestBody: '恢复一个本地项目，并重新进入它的工作区。',
    openQuestSearchPlaceholder: '按标题、项目 ID、分支或状态搜索…',
    openQuestEmpty: '没有匹配的项目。',
    openQuestNoProjects: '当前 DeepScientist home 下还没有任何项目。',
    openQuestCurrentHome: '当前 home',
    openQuestHomeHint: '这里只会显示当前 DeepScientist home 下保存的 quest；如果你的 quest 在别的目录里，请使用 `ds --home <path>` 重新启动。',
    openQuestLatest: '最近',
    openQuestUpdated: '更新于',
    openQuestPending: '待处理',
    openQuestBranch: '分支',
    openQuestNoDescription: '打开工作区后继续。',
    openQuestDelete: '删除项目',
    openQuestDeleteTitle: '确认删除项目？',
    openQuestDeleteBody: '这会永久删除本地项目仓库内容，且无法恢复。',
    openQuestDeleteConfirm: '删除',
    openQuestDeleteCancel: '取消',
    heroTitle: '本地优先的科研工作区',
    heroBody:
      '打开任意项目后，浏览器会持续保持 Codex 流式连接，并与 TUI 共用同一后端会话，同时查看文件、工作流与 artifact。',
    heroGuide:
      '指引：在项目首页直接发送请求，会自动创建新的项目仓库；在已绑定项目里发送，则会继续该项目会话。',
    createProject: '新建项目',
    createDialogTitle: '创建项目',
    createDialogBody: '从一个直接的研究目标开始。DeepScientist 会创建项目仓库，并立即进入工作区。',
    createProjectTitle: '项目标题',
    createProjectGoal: '目标 / 请求',
    createProjectAction: '创建并打开',
    cancel: '取消',
    quickRequest: '直接请求',
    quickRequestBody: '当前还没有绑定项目？在这里直接发送请求，DeepScientist 会自动创建新的项目。',
    quickRequestAction: '开始请求',
    openProject: '打开工作区',
    emptyProjects: '暂时还没有项目。可以先直接发起请求，或点击工作区卡片创建。',
    status: '状态',
    branch: '分支',
    metric: '指标',
    updated: '更新于',
    pending: '待处理',
    files: '文件',
    memory: '记忆',
    workflow: '工作流',
    graph: '图谱',
    overview: '总览',
    copilot: 'Copilot',
    activity: '活动',
    directTab: 'Studio',
    groupTab: 'Chat',
    directTabHint: '显示完整 Studio 运行轨迹：工具调用、artifact、里程碑，以及来自同一 daemon 会话的对话流。',
    groupTabHint: '只显示聊天线程本身，适合专注对话。',
    toolActivity: '工具动态',
    toolActivityBody: '读取、搜索、命令行与写入等操作会在这里实时浮现，且与当前流式会话保持同步。',
    showToolEffect: '显示工具条',
    hideToolEffect: '隐藏工具条',
    toolLive: '进行中',
    toolDone: '已完成',
    toolLiveBody: '这个动作来自同一 daemon 会话，并会在 Codex 持续工作时原位刷新。',
    toolResultBody: '这个工具步骤已经完成，并会固定显示，直到下一次新的实时工具事件出现。',
    showActivity: '显示活动',
    hideActivity: '隐藏活动',
    jumpToLatest: '跳到最新',
    emptyCopilotTitle: 'Studio 已就绪',
    emptyCopilotBody: '这里会一直保持流式连接。你可以直接请求状态总结、图谱更新、查看工具轨迹，或继续当前研究线程。',
    emptyGroupTitle: 'Chat 视图已准备好',
    emptyGroupBody: '这里仅保留聊天内容。如果你要查看工具过程、artifact 与运行事件，请切换到 Studio。',
    activityBody: '来自同一 daemon 会话的最近运行、artifact、待决策与变更文件。',
    streamingNow: '正在实时流式输出…',
    copyCode: '复制',
    copiedCode: '已复制',
    latestAssistant: '最近一次助手回复',
    workspaceGuide: '这个工作区会与 TUI 共享同一个 daemon 会话，并在 Codex 返回后持续流式显示更新。',
    sameSession: '与 TUI 共用同一 daemon 会话',
    streamLive: '实时流已连接',
    replyTarget: '回复目标',
    composerPlaceholder: '继续推进这个项目，或发送 /status、/graph、/summary …',
    commandHelp: '按 Ctrl/Cmd + Enter 发送。',
    openDocs: '打开文档',
    openSettings: '打开设置',
    loadProjectsFailed: '加载项目失败。',
    createFailed: '创建项目失败。',
    deleteFailed: '删除项目失败。',
    loading: '加载中…',
    recentArtifacts: '最近产物',
    recentRuns: '最近运行',
    changedFiles: '变更文件',
    guideCardTitle: '统一的本地交互面',
    guideCardBody:
      '项目页、TUI 与连接器消息流现在都读取同一个 daemon 事件面。即使刷新页面，也不会切换后端 API。',
    projectNotFound: '未找到项目。',
    explorer: '资源树',
    documents: '文档',
    noDocuments: '暂无文档。',
    noMemory: '暂无 memory 卡片。',
    noArtifacts: '暂无 artifact。',
    noRuns: '暂无运行记录。',
    noChangedFiles: '暂无变更文件。',
    noWorkflow: '第一次有效运行后，这里会出现工作流卡片。',
    noExplorer: '项目初始化后，这里会出现项目文件。',
    workingTree: '工作树',
    suggestions: '快捷建议',
    refresh: '刷新',
    send: '发送',
    directRequestTitlePlaceholder: '可选标题',
    directRequestGoalPlaceholder: '描述研究请求或下一步目标…',
    projectGoalPlaceholder: '描述项目目标、假设，或直接请求内容…',
  },
} as const

type MessageKey = keyof typeof messages.en

type I18nValue = {
  locale: Locale
  toggleLocale: () => void
  t: (key: MessageKey) => string
}

const I18nContext = createContext<I18nValue | null>(null)

function resolveInitialLocale(): Locale {
  return 'en'
}

function resolveBrowserConfigLocale(): 'zh-CN' | 'en-US' {
  if (typeof navigator === 'undefined') {
    return 'en-US'
  }
  return navigator.language.toLowerCase().startsWith('zh') ? 'zh-CN' : 'en-US'
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const uiLanguage = useUILanguageStore((state) => state.language)
  const locale = resolveLegacyLocale(uiLanguage)
  const hydrated = useUILanguageStore((state) => state.hydrated)
  const hydrateFromPersistence = useUILanguageStore((state) => state.hydrateFromPersistence)
  const saveLanguagePreference = useUILanguageStore((state) => state.saveLanguagePreference)
  const bootstrapAttemptedRef = useRef(false)

  useEffect(() => {
    if (hydrated) return
    hydrateFromPersistence()
  }, [hydrateFromPersistence, hydrated])

  useEffect(() => {
    if (bootstrapAttemptedRef.current) {
      return
    }
    bootstrapAttemptedRef.current = true

    let cancelled = false

    async function bootstrapRuntimeLocale() {
      try {
        const targetLocale = resolveBrowserConfigLocale()
        const document = await client.configDocument('config')
        if (cancelled) {
          return
        }
        const structured =
          document.meta?.structured_config && typeof document.meta.structured_config === 'object'
            ? ({ ...(document.meta.structured_config as Record<string, unknown>) } as Record<string, unknown>)
            : null
        if (!structured) {
          return
        }
        const bootstrap =
          structured.bootstrap && typeof structured.bootstrap === 'object'
            ? ({ ...(structured.bootstrap as Record<string, unknown>) } as Record<string, unknown>)
            : {}
        const localeSource = String(bootstrap.locale_source || '').trim().toLowerCase()
        const browserInitialized = Boolean(bootstrap.locale_initialized_from_browser)
        if (localeSource === 'user' || browserInitialized) {
          return
        }
        const currentLocale = String(structured.default_locale || '').trim()
        if (localeSource === 'default' || !currentLocale || currentLocale !== targetLocale) {
          structured.default_locale = targetLocale
        }
        structured.bootstrap = {
          ...bootstrap,
          locale_source: 'browser',
          locale_initialized_from_browser: true,
          locale_initialized_at: new Date().toISOString(),
          locale_initialized_browser_locale: targetLocale,
        }
        await client.saveConfig('config', {
          structured,
          revision: document.revision,
        })
      } catch {
        // Locale bootstrap should never block the UI surface.
      }
    }

    void bootstrapRuntimeLocale()

    return () => {
      cancelled = true
    }
  }, [])

  const value = useMemo<I18nValue>(
    () => ({
      locale,
      toggleLocale: () => {
        void saveLanguagePreference(locale === 'zh' ? 'en' : 'zh')
      },
      t: (key) => messages[locale][key],
    }),
    [locale, saveLanguagePreference]
  )

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>
}

export function useI18n() {
  const value = useContext(I18nContext)
  if (!value) {
    throw new Error('useI18n must be used within I18nProvider.')
  }
  return value
}
