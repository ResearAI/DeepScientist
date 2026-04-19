import * as React from 'react'
import { useLocation } from 'react-router-dom'

import { QuestActivitySurface } from '@/components/workspace/QuestActivitySurface'
import { QuestWorkspaceSurface } from '@/components/workspace/QuestWorkspaceSurface'
import { QuestSettingsSurface } from '@/components/workspace/QuestSettingsSurface'
import type { QuestWorkspaceView } from '@/components/workspace/workspace-events'
import { SettingsGuideCard } from '@/components/settings/SettingsGuideCard'
import { pickAdminCopy } from '@/components/settings/settingsOpsCopy'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useQuestWorkspace } from '@/lib/acp'
import { client } from '@/lib/api'
import { useI18n } from '@/lib/i18n/useI18n'
import { useAdminOpsStore } from '@/lib/stores/admin-ops'

const surfaceClassName =
  'rounded-[28px] border border-black/[0.06] bg-[rgba(255,251,246,0.76)] shadow-[0_18px_40px_-30px_rgba(18,24,32,0.24)] backdrop-blur-sm dark:border-white/[0.08] dark:bg-white/[0.03]'
const dividerClassName = 'border-black/[0.06] dark:border-white/[0.08]'

const PAGE_COPY = {
  en: {
    fallbackTitle: 'Quest Detail',
    fallbackSubtitle: 'Quest detail',
    subtitle: 'Detailed inspection and control for {questId}',
    guide: `
### What this page is for

- Use this page when a quest needs **deep inspection** rather than list-level supervision.
- It reuses the same durable quest surfaces as the main workspace, but from an operator perspective.

### Recommended reading order

1. **Details** for the high-signal summary.
2. **Canvas** when you need branch or route context.
3. **Memory** for durable operator-visible notes and lessons.
4. **Terminal** when you need live execution evidence.
5. **Settings** when the quest contract itself needs adjustment.
`,
    pause: 'Pause',
    resume: 'Resume',
    stop: 'Stop',
    refresh: 'Refresh',
    details: 'Details',
    activity: 'Activity',
    canvas: 'Canvas',
    memory: 'Memory',
    terminal: 'Terminal',
    settings: 'Settings',
  },
  zh: {
    fallbackTitle: 'Quest 详情',
    fallbackSubtitle: 'Quest 详情',
    subtitle: '{questId} 的详细检查与控制',
    guide: `
### 这一页用来做什么

- 当某个 quest 需要 **深度检查** 而不是列表级监管时，就进入这一页。
- 它复用了和主工作区同样的持久 quest 面，但视角切换成了运维视角。

### 推荐阅读顺序

1. 先看 **详情**，抓住高信号摘要。
2. 需要分支或路线背景时，再看 **Canvas**。
3. 需要持久化运维可见笔记与经验时，看 **Memory**。
4. 需要实时执行证据时，看 **终端**。
5. 需要调整 quest 合同时，看 **设置**。
`,
    pause: '暂停',
    resume: '恢复',
    stop: '停止',
    refresh: '刷新',
    details: '详情',
    activity: '活动',
    canvas: 'Canvas',
    memory: 'Memory',
    terminal: '终端',
    settings: '设置',
  },
} as const

type AdminQuestDetailView = QuestWorkspaceView | 'activity'

export function SettingsQuestDetailSection({ questId }: { questId: string }) {
  const { language } = useI18n('admin')
  const copy = pickAdminCopy(language, PAGE_COPY)
  const location = useLocation()
  const workspace = useQuestWorkspace(questId)
  const setContext = useAdminOpsStore((state) => state.setContext)
  const searchParams = React.useMemo(() => new URLSearchParams(location.search), [location.search])
  const requestedView = React.useMemo<AdminQuestDetailView>(
    () => {
      const raw = String(searchParams.get('view') || '').trim().toLowerCase()
      if (raw === 'activity' || raw === 'canvas' || raw === 'details' || raw === 'memory' || raw === 'terminal' || raw === 'settings' || raw === 'stage') {
        return raw
      }
      return 'details'
    },
    [searchParams]
  )
  const focusTarget = React.useMemo(() => String(searchParams.get('focus') || '').trim() || null, [searchParams])
  const [view, setView] = React.useState<AdminQuestDetailView>(requestedView)

  React.useEffect(() => {
    setView(requestedView)
  }, [requestedView, questId])

  React.useEffect(() => {
    const snapshot = workspace.snapshot
    if (!questId || !snapshot) return
    const selectedPaths = Object.values(snapshot.paths || {})
      .filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
      .slice(0, 12)
    setContext({
      sourcePage: `/settings/quests/${questId}`,
      scope: 'quest',
      targets: { quest_ids: [questId] },
      selectedPaths,
    })
  }, [questId, setContext, workspace.snapshot])

  const viewItems: Array<{ value: AdminQuestDetailView; label: string }> = [
    { value: 'details', label: copy.details },
    { value: 'activity', label: copy.activity },
    { value: 'canvas', label: copy.canvas },
    { value: 'memory', label: copy.memory },
    { value: 'terminal', label: copy.terminal },
    { value: 'settings', label: copy.settings },
  ]
  const settingsView = view === 'settings'
  const documentLikeView = view === 'settings' || view === 'activity'

  return (
    <div className="space-y-5">
      <SettingsGuideCard markdown={copy.guide} />

      <section className={`${surfaceClassName} px-5 py-5`}>
        <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
          <div>
            <div className="text-sm font-medium">{copy.fallbackTitle}</div>
            <div className="mt-1 text-xs text-muted-foreground">{copy.subtitle.replace('{questId}', questId)}</div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="outline" onClick={() => void client.controlQuest(questId, 'pause')}>
              {copy.pause}
            </Button>
            <Button size="sm" variant="outline" onClick={() => void client.controlQuest(questId, 'resume')}>
              {copy.resume}
            </Button>
            <Button size="sm" variant="destructive" onClick={() => void client.controlQuest(questId, 'stop')}>
              {copy.stop}
            </Button>
            <Button size="sm" variant="secondary" onClick={() => void workspace.refresh(false)}>
              {copy.refresh}
            </Button>
          </div>
        </div>
      </section>

      <Tabs
        value={view}
        onValueChange={(value) => setView(value as AdminQuestDetailView)}
        className={documentLikeView ? 'flex flex-col' : 'flex h-[78vh] min-h-[720px] max-h-[960px] flex-col'}
      >
        <div className={`${surfaceClassName} ${documentLikeView ? 'overflow-visible' : 'flex min-h-0 flex-1 flex-col overflow-hidden'}`}>
          <div className={`border-b ${dividerClassName} px-5 py-3`}>
            <TabsList className="h-auto flex-wrap justify-start gap-2 rounded-none bg-transparent p-0">
              {viewItems.map((item) => (
                <TabsTrigger
                  key={item.value}
                  value={item.value}
                  className="rounded-full border border-black/[0.08] bg-white/65 px-3 py-2 text-sm data-[state=active]:border-[#C7A57A] data-[state=active]:bg-[linear-gradient(180deg,rgba(222,196,158,0.28),rgba(222,196,158,0.12))] dark:border-white/[0.08] dark:bg-white/[0.03]"
                >
                  {item.label}
                </TabsTrigger>
              ))}
            </TabsList>
          </div>
          <TabsContent value={view} className={documentLikeView ? 'm-0' : 'm-0 flex min-h-0 flex-1'}>
            <div className={documentLikeView ? 'rounded-b-[28px]' : 'flex h-full min-h-0 flex-1 overflow-hidden rounded-b-[28px]'}>
              {view === 'settings' ? (
                <QuestSettingsSurface
                  questId={questId}
                  snapshot={workspace.snapshot}
                  onRefresh={async () => {
                    await workspace.refresh(false)
                  }}
                  layout="document"
                />
              ) : view === 'activity' ? (
                <QuestActivitySurface
                  questId={questId}
                  snapshot={workspace.snapshot}
                  focusTarget={focusTarget}
                  layout="document"
                />
              ) : (
                <QuestWorkspaceSurface
                  questId={questId}
                  safePaddingLeft={0}
                  safePaddingRight={0}
                  workspace={workspace}
                  view={view as QuestWorkspaceView}
                  settingsFocusTarget={focusTarget}
                />
              )}
            </div>
          </TabsContent>
        </div>
      </Tabs>
    </div>
  )
}
