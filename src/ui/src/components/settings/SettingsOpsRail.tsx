import * as React from 'react'
import { PanelLeft, Wrench, X } from 'lucide-react'

import { QuestCopilotComposer } from '@/components/workspace/QuestCopilotComposer'
import { QuestCopilotDockPanel } from '@/components/workspace/QuestCopilotDockPanel'
import { Button } from '@/components/ui/button'
import { useToast } from '@/components/ui/toast'
import { createAdminRepair } from '@/lib/api/admin'
import { useI18n } from '@/lib/i18n/useI18n'
import { useAdminOpsStore } from '@/lib/stores/admin-ops'
import { cn } from '@/lib/utils'

import { adminEnumLabel, adminLocaleFromLanguage } from '@/components/settings/settingsOpsCopy'

function countTargets(targets: Record<string, unknown> | undefined): number {
  if (!targets) return 0
  let total = 0
  for (const value of Object.values(targets)) {
    if (Array.isArray(value)) {
      total += value.length
      continue
    }
    if (value && typeof value === 'object') {
      total += Object.keys(value as Record<string, unknown>).length || 1
      continue
    }
    if (value !== undefined && value !== null && String(value).trim()) {
      total += 1
    }
  }
  return total
}

function buildCommandRecipes(context: {
  sourcePage?: string
  scope?: string
  targets?: Record<string, unknown>
  selectedPaths?: string[]
}, t: (key: string, params?: Record<string, string | number>) => string) {
  const page = String(context.sourcePage || '/settings').trim() || '/settings'
  const scope = String(context.scope || 'system').trim() || 'system'
  const selectedPaths = (context.selectedPaths || []).filter((item) => item.trim())
  const targets = summarizeTargets(context.targets, 'none')
  const pathBlock = selectedPaths.length > 0 ? `\nPaths:\n${selectedPaths.slice(0, 6).map((item) => `- ${item}`).join('\n')}` : ''
  return [
    { label: t('dock_recipe_inspect'), value: `INSPECT ${scope}\nPage: ${page}\nTargets: ${targets}` },
    { label: t('dock_recipe_logs'), value: `LOGS ${scope}\nPage: ${page}\nTargets: ${targets}` },
    { label: t('dock_recipe_search'), value: `SEARCH <query>\nPage: ${page}\nTargets: ${targets}${pathBlock}` },
    { label: t('dock_recipe_repro'), value: `REPRO <bug or mismatch>\nPage: ${page}\nExpected:\nActual:\nTargets: ${targets}${pathBlock}` },
    { label: t('dock_recipe_patch'), value: `PATCH <goal>\nPage: ${page}\nTargets: ${targets}${pathBlock}\nChange plan:\n- file:\n- reason:` },
    { label: t('dock_recipe_verify'), value: `VERIFY <change or claim>\nPage: ${page}${pathBlock}\nChecks:\n-` },
    { label: t('dock_recipe_issue'), value: `ISSUE <summary>\nPage: ${page}\nTargets: ${targets}${pathBlock}\nEvidence:\n-` },
    { label: t('dock_recipe_pr'), value: `PR <summary>\nPage: ${page}${pathBlock}\nChanged files:\n-\nVerification:\n-` },
  ]
}

function summarizeTargets(targets: Record<string, unknown> | undefined, noneLabel: string): string {
  if (!targets) return noneLabel
  const items = Object.entries(targets)
    .map(([key, value]) => {
      if (Array.isArray(value)) {
        return value.length > 0 ? `${key}:${value.length}` : null
      }
      if (value && typeof value === 'object') {
        const size = Object.keys(value as Record<string, unknown>).length
        return size > 0 ? `${key}:${size}` : null
      }
      if (value !== undefined && value !== null && String(value).trim()) {
        return `${key}:1`
      }
      return null
    })
    .filter((item): item is string => Boolean(item))
  return items.length > 0 ? items.join(' · ') : noneLabel
}

export function SettingsOpsLauncher() {
  const { t } = useI18n('admin')
  const dockOpen = useAdminOpsStore((state) => state.dockOpen)
  const startFreshSession = useAdminOpsStore((state) => state.startFreshSession)
  const launcherLabel = dockOpen ? t('dock_launcher_open') : t('dock_launcher_closed')

  if (dockOpen) {
    return null
  }

  return (
    <Button
      type="button"
      variant="secondary"
      size="sm"
      aria-pressed={false}
      data-testid="settings-copilot-launcher"
      data-onboarding-id="settings-admin-copilot-launcher"
      className="fixed bottom-4 left-4 z-[72] h-10 rounded-full border border-black/8 bg-[rgba(250,247,241,0.94)] px-4 shadow-[0_20px_44px_-32px_rgba(18,24,32,0.28)] backdrop-blur-xl hover:bg-[rgba(250,247,241,0.98)] dark:border-white/10 dark:bg-[rgba(18,20,24,0.92)] dark:hover:bg-[rgba(18,20,24,0.96)]"
      onClick={() => startFreshSession(window.location.pathname || '/settings')}
    >
      <PanelLeft className="mr-2 h-4 w-4" />
      {launcherLabel}
    </Button>
  )
}

export function SettingsOpsRail() {
  const { t, language } = useI18n('admin')
  const { addToast } = useToast()
  const locale = adminLocaleFromLanguage(language)
  const activeRepair = useAdminOpsStore((state) => state.activeRepair)
  const dockOpen = useAdminOpsStore((state) => state.dockOpen)
  const context = useAdminOpsStore((state) => state.context)
  const closeDock = useAdminOpsStore((state) => state.closeDock)
  const openRepair = useAdminOpsStore((state) => state.openRepair)
  const startFreshSession = useAdminOpsStore((state) => state.startFreshSession)
  const clearContext = useAdminOpsStore((state) => state.clearContext)
  const [input, setInput] = React.useState('')
  const [submitting, setSubmitting] = React.useState(false)

  const handleCreateRepair = React.useCallback(async () => {
    const trimmed = input.trim()
    if (!trimmed || submitting) return
    setSubmitting(true)
    try {
      const response = await createAdminRepair({
        request_text: trimmed,
        source_page: context.sourcePage,
        scope: context.scope || 'system',
        targets: context.targets || {},
        repair_policy: 'diagnose_only',
        selected_paths: context.selectedPaths || [],
      })
      openRepair(response.repair)
      setInput('')
    } catch (caught) {
      addToast({
        title: t('dock_failed_title'),
        message: caught instanceof Error ? caught.message : String(caught),
        variant: 'error',
      })
    } finally {
      setSubmitting(false)
    }
  }, [addToast, context.scope, context.selectedPaths, context.sourcePage, context.targets, input, openRepair, submitting, t])

  const opsQuestId = String(activeRepair?.ops_quest_id || '').trim()
  const selectedPaths = (context.selectedPaths || []).filter((item) => item.trim())
  const commandRecipes = React.useMemo(() => buildCommandRecipes(context, t), [context, t])

  if (!dockOpen) {
    return null
  }

  return (
    <aside
      data-testid="settings-copilot-rail"
      data-onboarding-id="settings-admin-copilot-rail"
      className={cn(
        'feed-scrollbar flex min-h-0 h-full flex-col overflow-hidden border-l border-black/8 bg-[rgba(250,247,241,0.92)] backdrop-blur-2xl dark:border-white/10 dark:bg-[rgba(18,20,24,0.9)]'
      )}
    >
      <div className="flex shrink-0 items-center justify-between gap-3 border-b border-black/8 px-4 py-3 dark:border-white/10">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-foreground">
            {activeRepair ? t('dock_title_active', { repairId: activeRepair.repair_id }) : t('dock_title_idle')}
          </div>
          <div className="truncate text-xs text-muted-foreground">
            {activeRepair
              ? `${adminEnumLabel(activeRepair.repair_policy || 'diagnose_only', locale)} · ${adminEnumLabel(activeRepair.scope || 'system', locale)}`
              : t('dock_subtitle_idle')}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {activeRepair ? (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setInput('')
                startFreshSession(context.sourcePage || window.location.pathname || '/settings')
              }}
            >
              {t('dock_new_session')}
            </Button>
          ) : null}
          <Button variant="ghost" size="icon" onClick={() => closeDock()} aria-label={t('dock_close')}>
            <X className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {opsQuestId ? (
        <div className="min-h-0 flex-1">
          <QuestCopilotDockPanel
            questId={opsQuestId}
            title={t('dock_title_active', { repairId: activeRepair?.repair_id || '' })}
          />
        </div>
      ) : (
        <div className="flex min-h-0 flex-1 flex-col">
          <div className="feed-scrollbar min-h-0 flex-1 overflow-y-auto px-4 py-4">
            <div className="rounded-[20px] bg-white/40 p-4 dark:bg-white/[0.04]">
              <div className="flex items-center gap-2 text-sm font-medium">
                <Wrench className="h-4 w-4 text-[#7E8B97]" />
                <span>{t('dock_start_title')}</span>
              </div>
              <p className="mt-2 text-[12.5px] leading-6 text-soft-text-secondary">{t('dock_start_body')}</p>
            </div>

            <div className="mt-4 border-t border-black/8 pt-4 dark:border-white/10">
              <div className="flex items-center justify-between gap-3">
                <div className="text-sm font-medium">{t('dock_context_title')}</div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    setInput('')
                    clearContext(context.sourcePage || window.location.pathname || '/settings')
                  }}
                >
                  {t('dock_clear_context')}
                </Button>
              </div>
              <div className="mt-3 space-y-2 text-[12px] leading-6 text-soft-text-secondary">
                <div>
                  <span className="font-medium text-foreground">{t('dock_context_page')}:</span>{' '}
                  {context.sourcePage || t('dock_context_none')}
                </div>
                <div>
                  <span className="font-medium text-foreground">{t('dock_context_scope')}:</span>{' '}
                  {adminEnumLabel(context.scope || 'system', locale)}
                </div>
                <div>
                  <span className="font-medium text-foreground">{t('dock_context_targets')}:</span>{' '}
                  {summarizeTargets(context.targets, t('dock_context_none'))}
                  {countTargets(context.targets) > 0 ? ` (${countTargets(context.targets)})` : ''}
                </div>
                <div>
                  <span className="font-medium text-foreground">{t('dock_context_selected_paths')}:</span>{' '}
                  {selectedPaths.length > 0 ? `${selectedPaths.length}` : t('dock_context_none')}
                </div>
              </div>
              {selectedPaths.length > 0 ? (
                <div className="mt-3 space-y-1 border-l border-black/8 pl-3 text-[11px] leading-5 text-soft-text-secondary dark:border-white/10">
                  {selectedPaths.slice(0, 6).map((item) => (
                    <div key={item} className="truncate">
                      {item}
                    </div>
                  ))}
                  {selectedPaths.length > 6 ? <div>+{selectedPaths.length - 6}</div> : null}
                </div>
              ) : null}
            </div>

            <div className="mt-4 border-t border-black/8 pt-4 dark:border-white/10" data-onboarding-id="settings-admin-copilot-recipes">
              <div className="text-sm font-medium">{t('dock_recipe_title')}</div>
              <p className="mt-2 text-[12px] leading-6 text-soft-text-secondary">{t('dock_recipe_body')}</p>
              <div className="mt-3 flex flex-wrap gap-2">
                {commandRecipes.map((recipe) => (
                  <Button
                    key={recipe.label}
                    type="button"
                    size="sm"
                    variant="outline"
                    className="rounded-full"
                    onClick={() => setInput(recipe.value)}
                  >
                    {recipe.label}
                  </Button>
                ))}
              </div>
              <div className="mt-3 text-[11px] leading-5 text-soft-text-secondary">{t('dock_recipe_approval')}</div>
            </div>
          </div>

          <div className="shrink-0 px-4 pb-4">
            <QuestCopilotComposer
              value={input}
              onValueChange={setInput}
              onSubmit={handleCreateRepair}
              submitting={submitting}
              stopping={false}
              showStopButton={false}
              slashCommands={[]}
              placeholder={t('dock_placeholder')}
              enterHint={t('dock_enter_hint')}
              sendLabel={t('dock_send')}
              stopLabel={t('dock_stop')}
            />
          </div>
        </div>
      )}
    </aside>
  )
}
