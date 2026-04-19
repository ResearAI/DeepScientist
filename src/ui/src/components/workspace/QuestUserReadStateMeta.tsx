import * as React from 'react'

import { useI18n } from '@/lib/i18n/useI18n'
import { cn } from '@/lib/utils'

function normalizeReadState(value?: string | null) {
  const normalized = String(value || '').trim().toLowerCase()
  if (normalized === 'unread') return 'unread'
  return 'read'
}

function normalizeDisplayState(args: { readState?: string | null; readReason?: string | null }) {
  const readReason = String(args.readReason || '').trim().toLowerCase()
  if (readReason === 'withdrawn_by_user') return 'withdrawn'
  return normalizeReadState(args.readState)
}

type QuestUserReadStateMetaProps = {
  readState?: string | null
  readReason?: string | null
  messageId?: string | null
  busyAction?: 'read_now' | 'withdraw' | null
  className?: string
  onReadNow?: ((messageId: string) => void | Promise<void>) | null
  onWithdraw?: ((messageId: string) => void | Promise<void>) | null
}

export function QuestUserReadStateMeta({
  readState,
  readReason,
  messageId,
  busyAction = null,
  className,
  onReadNow,
  onWithdraw,
}: QuestUserReadStateMetaProps) {
  const { t } = useI18n('workspace')
  const normalizedState = normalizeDisplayState({ readState, readReason })
  const canReadNow = normalizedState === 'unread' && Boolean(messageId) && Boolean(onReadNow)
  const canWithdraw = normalizedState === 'unread' && Boolean(messageId) && Boolean(onWithdraw)

  return (
    <div className={cn('flex items-center gap-2 text-[10px] leading-none', className)}>
      <span>
        {normalizedState === 'unread'
          ? t('copilot_message_unread', undefined, 'Unread')
          : normalizedState === 'withdrawn'
            ? t('copilot_message_withdrawn', undefined, 'Withdrawn')
            : t('copilot_message_read', undefined, 'Read')}
      </span>
      {canReadNow ? (
        <button
          type="button"
          className="rounded-sm underline underline-offset-2 transition hover:text-foreground disabled:cursor-default disabled:no-underline disabled:opacity-60"
          disabled={busyAction !== null}
          onClick={() => {
            if (!messageId || !onReadNow) return
            void onReadNow(messageId)
          }}
        >
          {busyAction === 'read_now'
            ? t('copilot_message_read_now_busy', undefined, 'Reading now...')
            : t('copilot_message_read_now', undefined, 'Read now')}
        </button>
      ) : null}
      {canWithdraw ? (
        <button
          type="button"
          className="rounded-sm underline underline-offset-2 transition hover:text-foreground disabled:cursor-default disabled:no-underline disabled:opacity-60"
          disabled={busyAction !== null}
          onClick={() => {
            if (!messageId || !onWithdraw) return
            void onWithdraw(messageId)
          }}
        >
          {busyAction === 'withdraw'
            ? t('copilot_message_withdraw_busy', undefined, 'Withdrawing...')
            : t('copilot_message_withdraw', undefined, 'Withdraw')}
        </button>
      ) : null}
    </div>
  )
}

export default QuestUserReadStateMeta
