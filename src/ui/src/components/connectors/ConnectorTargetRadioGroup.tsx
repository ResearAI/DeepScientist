import * as React from 'react'
import { CheckCircle2, Unlink2 } from 'lucide-react'

import { connectorBrandIcons } from '@/components/settings/connectorBrandIcons'
import { cn } from '@/lib/utils'

export type ConnectorTargetRadioItem = {
  value: string
  connectorName: string
  connectorLabel: string
  targetId: string
  boundQuestLabel: string
  disabled?: boolean
  localOnly?: boolean
}

type ConnectorTargetRadioGroupProps = {
  items: ConnectorTargetRadioItem[]
  value: string
  onChange: (value: string) => void
  ariaLabel: string
  className?: string
}

function LocalOnlyIcon(props: { className?: string }) {
  return <Unlink2 aria-hidden="true" className={props.className} />
}

export function ConnectorTargetRadioGroup({
  items,
  value,
  onChange,
  ariaLabel,
  className,
}: ConnectorTargetRadioGroupProps) {
  return (
    <div role="radiogroup" aria-label={ariaLabel} className={cn('grid gap-3 sm:grid-cols-2 xl:grid-cols-3', className)}>
      {items.map((item) => {
        const active = item.value === value
        const Icon = item.localOnly ? LocalOnlyIcon : connectorBrandIcons[item.connectorName] || LocalOnlyIcon
        const showTargetId = Boolean(item.targetId) && item.targetId !== item.connectorLabel
        return (
          <button
            key={item.value}
            type="button"
            role="radio"
            aria-checked={active}
            disabled={item.disabled}
            onClick={() => onChange(item.value)}
            className={cn(
              'relative flex min-h-[112px] w-full items-start gap-3 rounded-[18px] border px-4 py-4 text-left transition',
              'disabled:cursor-not-allowed disabled:opacity-55',
              active
                ? 'border-[var(--ds-brand)]/45 bg-[var(--ds-brand)]/8 shadow-[0_18px_36px_-28px_rgba(111,78,55,0.65)]'
                : 'border-border/60 bg-[var(--ds-panel-elevated)]/70 hover:border-[var(--ds-brand)]/28 hover:bg-[var(--ds-panel-elevated)]/90'
            )}
          >
            <span
              className={cn(
                'flex h-11 w-11 shrink-0 items-center justify-center rounded-[14px] border',
                active
                  ? 'border-[var(--ds-brand)]/35 bg-[var(--ds-brand)]/10 text-[var(--ds-brand)]'
                  : 'border-border/60 bg-background/70 text-foreground'
              )}
            >
              <Icon className="h-5 w-5" />
            </span>

            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-semibold text-foreground" title={item.connectorLabel}>
                {item.connectorLabel}
              </span>
              {showTargetId ? (
                <span
                  className="mt-1 block truncate font-mono text-[11px] leading-5 text-muted-foreground"
                  title={item.targetId}
                >
                  {item.targetId}
                </span>
              ) : null}
              {item.boundQuestLabel ? (
                <span
                  className="mt-3 block truncate text-[11px] leading-5 text-muted-foreground"
                  title={item.boundQuestLabel}
                >
                  {item.boundQuestLabel}
                </span>
              ) : null}
            </span>

            <CheckCircle2
              aria-hidden="true"
              className={cn(
                'h-4.5 w-4.5 shrink-0 transition',
                active ? 'text-[var(--ds-brand)] opacity-100' : 'text-muted-foreground/40 opacity-55'
              )}
            />
          </button>
        )
      })}
    </div>
  )
}

export default ConnectorTargetRadioGroup
