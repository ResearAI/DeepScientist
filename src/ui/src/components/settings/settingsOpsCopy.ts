export type SettingsOpsLocale = 'en' | 'zh'

export function adminLocaleFromLanguage(language: string): SettingsOpsLocale {
  return language === 'zh-CN' ? 'zh' : 'en'
}

export function pickAdminCopy<T>(
  language: string,
  copy: {
    en: T
    zh: T
  }
): T {
  return copy[adminLocaleFromLanguage(language)]
}

const ENUM_LABELS: Record<SettingsOpsLocale, Record<string, string>> = {
  en: {
    enabled: 'enabled',
    disabled: 'disabled',
    available: 'available',
    missing: 'missing',
    present: 'Present',
    clear: 'Clear',
    degraded: 'degraded',
    open: 'open',
    closed: 'closed',
    running: 'running',
    active: 'active',
    paused: 'paused',
    stopped: 'stopped',
    completed: 'completed',
    failed: 'failed',
    error: 'error',
    idle: 'idle',
    queued: 'queued',
    unknown: 'unknown',
    terminating: 'terminating',
    diagnose_only: 'diagnose only',
    system: 'system',
    quest: 'quest',
    copilot: 'Copilot',
    autonomous: 'autonomous',
    runtime: 'runtime',
    connector: 'connector',
    log: 'log',
  },
  zh: {
    enabled: '已启用',
    disabled: '已禁用',
    available: '可用',
    missing: '缺失',
    present: '存在',
    clear: '正常',
    degraded: '退化',
    open: '打开',
    closed: '关闭',
    running: '运行中',
    active: '活动中',
    paused: '已暂停',
    stopped: '已停止',
    completed: '已完成',
    failed: '失败',
    error: '错误',
    idle: '空闲',
    queued: '排队中',
    unknown: '未知',
    terminating: '终止中',
    diagnose_only: '仅诊断',
    system: '系统',
    quest: 'Quest',
    copilot: 'Copilot',
    autonomous: '自动',
    runtime: '运行时',
    connector: '连接器',
    log: '日志',
  },
}

export function adminEnumLabel(value: unknown, locale: SettingsOpsLocale): string {
  const normalized = String(value || '').trim().toLowerCase()
  if (!normalized) {
    return ENUM_LABELS[locale].unknown
  }
  return ENUM_LABELS[locale][normalized] || String(value)
}
