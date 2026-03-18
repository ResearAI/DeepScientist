'use client'

import * as React from 'react'
import { AlertTriangle, CheckCircle2, Link2, Moon, RefreshCw, Sun, Unlink2 } from 'lucide-react'

import { EnhancedCard } from '@/components/ui/enhanced-card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { ConfirmModal } from '@/components/ui/modal'
import { SegmentedControl } from '@/components/ui/segmented-control'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'
import { useToast } from '@/components/ui/toast'
import { client } from '@/lib/api'
import { connectorTargetLabel, conversationIdentityKey, normalizeConnectorTargets, parseConversationId } from '@/lib/connectors'
import { useThemeStore, type Theme } from '@/lib/stores/theme'
import { cn } from '@/lib/utils'
import type { ConnectorSnapshot, ConnectorTargetSnapshot, QuestSummary } from '@/types'

type ConflictItem = {
  quest_id: string
  title?: string | null
  reason?: string | null
}

function connectorLabel(connector: ConnectorSnapshot) {
  const name = String(connector.name || '').trim()
  if (!name) return 'Connector'
  if (name.toLowerCase() === 'qq') return 'QQ'
  return name[0].toUpperCase() + name.slice(1)
}

function connectionBadge(connector: ConnectorSnapshot) {
  const enabled = Boolean(connector.enabled)
  const connection = String(connector.connection_state || '').trim().toLowerCase()
  if (!enabled) return { label: 'disabled', variant: 'secondary' as const }
  if (connection === 'connected') return { label: 'connected', variant: 'default' as const }
  if (connection === 'ready') return { label: 'ready', variant: 'default' as const }
  if (connection === 'awaiting_first_message') return { label: 'awaiting message', variant: 'secondary' as const }
  if (connection === 'needs_credentials') return { label: 'needs credentials', variant: 'secondary' as const }
  if (connection === 'error') return { label: 'error', variant: 'destructive' as const }
  if (connection) return { label: connection.replace(/_/g, ' '), variant: 'secondary' as const }
  return { label: 'unknown', variant: 'secondary' as const }
}

function targetLabel(target: ConnectorTargetSnapshot) {
  return connectorTargetLabel(target) || String(target.conversation_id)
}

export function QuestSettingsSurface({
  questId,
  snapshot,
  onRefresh,
}: {
  questId: string
  snapshot: QuestSummary | null
  onRefresh: () => Promise<void>
}) {
  const { toast } = useToast()
  const boundConversationByConnector = React.useMemo(() => {
    const mapping: Record<string, string> = {}
    for (const raw of snapshot?.bound_conversations || []) {
      const parsed = parseConversationId(raw)
      if (!parsed || parsed.connector === 'local') continue
      mapping[parsed.connector] = parsed.conversation_id
    }
    return mapping
  }, [snapshot?.bound_conversations])

  const [connectors, setConnectors] = React.useState<ConnectorSnapshot[]>([])
  const [loadingConnectors, setLoadingConnectors] = React.useState(true)
  const [binding, setBinding] = React.useState(false)
  const [selection, setSelection] = React.useState<Record<string, string>>({})

  const [confirmOpen, setConfirmOpen] = React.useState(false)
  const [confirmPayload, setConfirmPayload] = React.useState<Array<{ connector: string; conversation_id?: string | null }>>([])
  const [conflicts, setConflicts] = React.useState<ConflictItem[]>([])

  const theme = useThemeStore((state) => state.theme)
  const setTheme = useThemeStore((state) => state.setTheme)

  const reloadConnectors = React.useCallback(async () => {
    setLoadingConnectors(true)
    try {
      const payload = await client.connectors()
      setConnectors(payload.filter((item) => item.name !== 'local'))
    } finally {
      setLoadingConnectors(false)
    }
  }, [])

  React.useEffect(() => {
    void reloadConnectors()
    const timer = window.setInterval(() => {
      void reloadConnectors()
    }, 4000)
    return () => {
      window.clearInterval(timer)
    }
  }, [reloadConnectors])

  React.useEffect(() => {
    if (!connectors.length) {
      return
    }
    setSelection(() => {
      const next: Record<string, string> = {}
      for (const connector of connectors) {
        const name = connector.name
        const boundConversation = boundConversationByConnector[name.toLowerCase()] || ''
        const targets = normalizeConnectorTargets(connector)
        const defaultId =
          boundConversation ||
          connector.default_target?.conversation_id ||
          targets[0]?.conversation_id ||
          ''
        next[name] = defaultId
      }
      return next
    })
  }, [boundConversationByConnector, connectors])

  const saveBindings = React.useCallback(
    async (bindings: Array<{ connector: string; conversation_id?: string | null }>, { force }: { force: boolean }) => {
      setBinding(true)
      try {
        const result = (await client.updateQuestBindings(questId, {
          bindings,
          force,
        })) as Record<string, unknown>
        const ok = Boolean(result.ok)
        const status = Number(result.status || 200)
        if (!ok && status === 409) {
          const items = Array.isArray(result.conflicts)
            ? (result.conflicts.filter(
                (item): item is ConflictItem =>
                  Boolean(item) && typeof item === 'object' && !Array.isArray(item) && typeof (item as any).quest_id === 'string'
              ) as ConflictItem[])
            : []
          setConflicts(items)
          setConfirmPayload(bindings)
          setConfirmOpen(true)
          return
        }
        if (!ok) {
          toast({
            title: 'Binding failed',
            description: String(result.message || 'Unable to update connector bindings.'),
            variant: 'destructive',
          })
          return
        }

        toast({
          title: 'Saved',
          description: 'Connector bindings updated.',
        })
        await Promise.all([onRefresh(), reloadConnectors()])
      } finally {
        setBinding(false)
      }
    },
    [onRefresh, questId, reloadConnectors, toast]
  )

  const pendingBindings = React.useMemo(
    () =>
      connectors.map((connector) => ({
        connector: connector.name,
        conversation_id: selection[connector.name] || null,
      })),
    [connectors, selection]
  )

  const hasPendingChanges = React.useMemo(
    () =>
      connectors.some((connector) => {
        const name = connector.name.toLowerCase()
        return (selection[connector.name] || '') !== (boundConversationByConnector[name] || '')
      }),
    [boundConversationByConnector, connectors, selection]
  )

  const themeItems = React.useMemo(
    () => [
      { value: 'system' as Theme, label: 'System', icon: <Sun className="h-4 w-4" /> },
      { value: 'light' as Theme, label: 'Light', icon: <Sun className="h-4 w-4" /> },
      { value: 'dark' as Theme, label: 'Dark', icon: <Moon className="h-4 w-4" /> },
    ],
    []
  )

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden p-4 sm:p-5">
      <div className="flex min-h-0 flex-1 flex-col gap-4 rounded-[28px] border border-black/[0.06] bg-white/[0.42] p-4 shadow-card backdrop-blur-xl dark:border-white/[0.08] dark:bg-white/[0.03] sm:p-5">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="text-sm font-semibold text-foreground">Project settings</div>
            <div className="mt-1 text-xs text-muted-foreground">
              Select which connector receives progress updates for <span className="font-mono">{questId}</span>.
            </div>
          </div>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={() => void reloadConnectors()}
            disabled={loadingConnectors}
            className="shrink-0"
          >
            <RefreshCw className={cn('mr-2 h-4 w-4', loadingConnectors && 'animate-spin')} />
            Refresh
          </Button>
        </div>

        <div className="flex-1 min-h-0 overflow-auto pr-1 space-y-5">
          <EnhancedCard
            enableSpotlight={false}
            className="border border-border/60 bg-[var(--ds-panel-elevated)]/70 backdrop-blur-xl shadow-[var(--ds-shadow-md)]"
          >
            <div className="p-4 space-y-3">
              <div className="flex items-center justify-between gap-3">
                <div className="text-sm font-medium text-foreground">Theme</div>
                <SegmentedControl
                  value={theme}
                  onValueChange={(value) => setTheme(value)}
                  items={themeItems}
                  size="sm"
                  ariaLabel="Theme selection"
                />
              </div>
              <div className="text-xs text-muted-foreground">
                This setting applies to the whole web workspace (not just this project).
              </div>
            </div>
          </EnhancedCard>

          <EnhancedCard
            enableSpotlight={false}
            className="border border-border/60 bg-[var(--ds-panel-elevated)]/70 backdrop-blur-xl shadow-[var(--ds-shadow-md)]"
          >
            <div className="p-4 space-y-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="text-sm font-medium text-foreground">Connector bindings</div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    Choose one target per connector for <span className="font-mono">{questId}</span>. Saving here keeps different connectors independent.
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    onClick={() =>
                      setSelection((current) => {
                        const next = { ...current }
                        for (const connector of connectors) {
                          next[connector.name] = ''
                        }
                        return next
                      })
                    }
                    disabled={binding || connectors.length === 0}
                  >
                    <Unlink2 className="mr-2 h-4 w-4" />
                    Local only
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    onClick={() => void saveBindings(pendingBindings, { force: false })}
                    disabled={binding || !hasPendingChanges}
                  >
                    <Link2 className="mr-2 h-4 w-4" />
                    Save bindings
                  </Button>
                </div>
              </div>

              <Separator className="bg-border/50" />

              {connectors.length === 0 ? (
                <div className="text-sm text-muted-foreground">
                  {loadingConnectors ? 'Loading connectors…' : 'No connector configured yet.'}
                </div>
              ) : (
                <div className="grid grid-cols-1 gap-3">
                  {connectors.map((connector) => {
                    const badge = connectionBadge(connector)
                    const targets = normalizeConnectorTargets(connector)
                    const chosen = selection[connector.name] ?? ''
                    const chosenTarget =
                      targets.find((item) => conversationIdentityKey(item.conversation_id) === conversationIdentityKey(chosen)) ||
                      null
                    const isBound =
                      Boolean(chosen) &&
                      conversationIdentityKey(chosen) === conversationIdentityKey(boundConversationByConnector[connector.name.toLowerCase()] || '')
                    const boundQuestId = chosenTarget?.bound_quest_id

                    return (
                      <div
                        key={connector.name}
                        className={cn(
                          'rounded-2xl border px-3 py-3 bg-background/40 backdrop-blur-md',
                          isBound ? 'border-[var(--ds-brand)]/40 shadow-sm' : 'border-border/50'
                        )}
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="text-sm font-semibold text-foreground">
                                {connectorLabel(connector)}
                              </span>
                              <Badge variant={badge.variant} className="text-[10px] uppercase tracking-wide">
                                {badge.label}
                              </Badge>
                              {isBound ? (
                                <span className="inline-flex items-center gap-1 text-xs text-[var(--success-foreground)]">
                                  <CheckCircle2 className="h-3.5 w-3.5" />
                                  bound
                                </span>
                              ) : null}
                            </div>
                            <div className="mt-1 text-xs text-muted-foreground">
                              {connector.transport ? `transport: ${connector.transport}` : ' '}
                            </div>
                          </div>
                          {isBound ? (
                            <Badge variant="secondary" className="text-[10px] uppercase tracking-wide">
                              active
                            </Badge>
                          ) : null}
                        </div>

                        <div className="mt-3 flex flex-col gap-2">
                          <div className="flex items-center gap-2">
                            <div className="text-xs text-muted-foreground shrink-0">Target</div>
                            <div className="flex-1 min-w-0">
                              <Select
                                value={chosen || '__none__'}
                                onValueChange={(value) =>
                                  setSelection((current) => ({
                                    ...current,
                                    [connector.name]: value === '__none__' ? '' : value,
                                  }))
                                }
                                disabled={!connector.enabled || targets.length === 0}
                              >
                                <SelectTrigger className="h-8 rounded-xl bg-background/40 border-border/60">
                                  <SelectValue placeholder={targets.length ? 'Select target…' : 'No target yet'} />
                                </SelectTrigger>
                                <SelectContent>
                                  <SelectItem value="__none__">Not bound</SelectItem>
                                  {targets.map((item) => (
                                    <SelectItem key={item.conversation_id} value={item.conversation_id}>
                                      {targetLabel(item)}
                                    </SelectItem>
                                  ))}
                                </SelectContent>
                              </Select>
                            </div>
                          </div>

                          {chosenTarget ? (
                            <div className="rounded-xl border border-border/50 bg-background/30 px-3 py-2 text-xs text-muted-foreground">
                              <div className="font-mono text-[11px] text-foreground">{chosenTarget.conversation_id}</div>
                              {chosenTarget.bound_quest_id ? (
                                <div className="mt-1">
                                  Bound to <span className="font-mono">{chosenTarget.bound_quest_id}</span>
                                  {chosenTarget.bound_quest_title ? ` · ${chosenTarget.bound_quest_title}` : ''}
                                </div>
                              ) : (
                                <div className="mt-1">Currently not bound to another project.</div>
                              )}
                            </div>
                          ) : null}

                          {boundQuestId && boundQuestId !== questId ? (
                            <div className="flex items-start gap-2 rounded-xl border border-amber-500/30 bg-amber-500/10 px-3 py-2">
                              <AlertTriangle className="mt-0.5 h-4 w-4 text-amber-600" />
                              <div className="text-xs text-amber-800 dark:text-amber-200">
                                This target is currently bound to <span className="font-mono">{boundQuestId}</span>.
                                Binding here will reassign it.
                              </div>
                            </div>
                          ) : null}
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          </EnhancedCard>
        </div>
      </div>

      <ConfirmModal
        open={confirmOpen}
        onClose={() => {
          if (binding) return
          setConfirmOpen(false)
        }}
        onConfirm={() => {
          if (!confirmPayload.length) return
          setConfirmOpen(false)
          void saveBindings(confirmPayload, { force: true })
        }}
        loading={binding}
        title="Rebind connector?"
        description={
          conflicts.length
            ? `This will unbind the conversation from: ${conflicts
                .map((item) => item.quest_id)
                .filter(Boolean)
                .join(', ')}`
            : 'This connector target is already bound elsewhere.'
        }
        confirmText="Rebind"
        cancelText="Cancel"
        variant="warning"
      />
    </div>
  )
}

export default QuestSettingsSurface
