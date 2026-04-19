'use client'

import * as React from 'react'
import { ArrowUp, FileText, Image as ImageIcon, Loader2, Paperclip, Slash, Square, X } from 'lucide-react'

import OrbitLogoStatus from '@/lib/plugins/ai-manus/components/OrbitLogoStatus'
import { cn } from '@/lib/utils'
import type { QuestMessageAttachmentDraft } from '@/lib/hooks/useQuestMessageAttachments'

type ComposerCommand = {
  name: string
  description?: string
}

type QuestCopilotComposerProps = {
  value: string
  onValueChange: (value: string) => void
  onSubmit: () => Promise<void> | void
  onStop?: () => Promise<void> | void
  submitting?: boolean
  stopping?: boolean
  showStopButton?: boolean
  slashCommands?: ComposerCommand[]
  placeholder: string
  enterHint: string
  sendLabel: string
  stopLabel: string
  focusToken?: number | null
  attachments?: QuestMessageAttachmentDraft[]
  onQueueFiles?: (files: File[]) => void
  onRemoveAttachment?: (draftId: string) => void
}

const MIN_ROWS = 2
const MAX_ROWS = 5

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max)
}

function isSlashCommandQueryActive(value: string) {
  const raw = value.trimStart()
  return raw.startsWith('/') && !/\s/.test(raw.slice(1))
}

function compactHintText(value: string, availableWidth: number) {
  const normalized = String(value || '').trim()
  if (!normalized) return ''
  if (availableWidth >= 240) return normalized

  const segments = normalized.split('·').map((item) => item.trim()).filter(Boolean)
  if (availableWidth >= 170 && segments.length > 0) {
    return segments[0]
  }

  if (availableWidth >= 128) {
    return normalized.length > 18 ? `${normalized.slice(0, 17).trimEnd()}…` : normalized
  }

  return ''
}

export function QuestCopilotComposer({
  value,
  onValueChange,
  onSubmit,
  onStop,
  submitting = false,
  stopping = false,
  showStopButton = false,
  slashCommands = [],
  placeholder,
  enterHint,
  sendLabel,
  stopLabel,
  focusToken = null,
  attachments = [],
  onQueueFiles,
  onRemoveAttachment,
}: QuestCopilotComposerProps) {
  const textareaRef = React.useRef<HTMLTextAreaElement | null>(null)
  const shellRef = React.useRef<HTMLDivElement | null>(null)
  const actionsRef = React.useRef<HTMLDivElement | null>(null)
  const fileInputRef = React.useRef<HTMLInputElement | null>(null)
  const [activeCommandIndex, setActiveCommandIndex] = React.useState(0)
  const [layoutMetrics, setLayoutMetrics] = React.useState({
    shellWidth: 0,
    actionsWidth: 0,
  })

  const hasAttachments = attachments.length > 0
  const hasSuccessfulAttachments = attachments.some((item) => item.status === 'success')
  const hasAttachmentFailures = attachments.some((item) => item.status === 'failed')
  const hasUploadingAttachments = attachments.some(
    (item) => item.status === 'queued' || item.status === 'uploading'
  )
  const sendDisabled = submitting || hasUploadingAttachments || hasAttachmentFailures || (!value.trim() && !hasSuccessfulAttachments)

  const filteredCommands = React.useMemo(() => {
    const raw = value.trimStart()
    if (!raw.startsWith('/')) return []
    const query = raw.slice(1).toLowerCase()
    return slashCommands
      .filter((item) => {
        if (!query) return true
        return (
          item.name.toLowerCase().includes(query) ||
          (item.description || '').toLowerCase().includes(query)
        )
      })
      .slice(0, 8)
  }, [slashCommands, value])

  const commandQueryActive = React.useMemo(
    () => isSlashCommandQueryActive(value),
    [value]
  )

  const adjustHeight = React.useCallback(() => {
    const node = textareaRef.current
    if (!node) return
    node.style.height = 'auto'
    const computed = window.getComputedStyle(node)
    const lineHeight = Number.parseFloat(computed.lineHeight || '') || 21
    const paddingTop = Number.parseFloat(computed.paddingTop || '') || 0
    const paddingBottom = Number.parseFloat(computed.paddingBottom || '') || 0
    const borderTop = Number.parseFloat(computed.borderTopWidth || '') || 0
    const borderBottom = Number.parseFloat(computed.borderBottomWidth || '') || 0
    const minHeight = lineHeight * MIN_ROWS + paddingTop + paddingBottom + borderTop + borderBottom
    const maxHeight = lineHeight * MAX_ROWS + paddingTop + paddingBottom + borderTop + borderBottom
    const nextHeight = clamp(node.scrollHeight, minHeight, maxHeight)
    node.style.height = `${nextHeight}px`
    node.style.overflowY = node.scrollHeight > maxHeight ? 'auto' : 'hidden'
  }, [])

  React.useEffect(() => {
    adjustHeight()
  }, [adjustHeight, value])

  React.useEffect(() => {
    if (focusToken == null) return
    window.requestAnimationFrame(() => {
      textareaRef.current?.focus()
    })
  }, [focusToken])

  React.useEffect(() => {
    setActiveCommandIndex((current) => {
      if (filteredCommands.length === 0) return 0
      return clamp(current, 0, filteredCommands.length - 1)
    })
  }, [filteredCommands.length])

  React.useEffect(() => {
    const shell = shellRef.current
    const actions = actionsRef.current
    if (!shell || !actions) return

    const measure = () => {
      const shellWidth = Math.ceil(shell.getBoundingClientRect().width || 0)
      const actionsWidth = Math.ceil(actions.getBoundingClientRect().width || 0)
      setLayoutMetrics((current) =>
        current.shellWidth === shellWidth && current.actionsWidth === actionsWidth
          ? current
          : { shellWidth, actionsWidth }
      )
    }

    measure()
    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', measure)
      return () => window.removeEventListener('resize', measure)
    }

    const observer = new ResizeObserver(measure)
    observer.observe(shell)
    observer.observe(actions)
    return () => observer.disconnect()
  }, [])

  const applyCommand = React.useCallback(
    (name: string) => {
      onValueChange(`/${name} `)
      window.requestAnimationFrame(() => {
        textareaRef.current?.focus()
      })
    },
    [onValueChange]
  )

  const handleKeyDown = React.useCallback(
    (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if ((event.nativeEvent as { isComposing?: boolean })?.isComposing) {
        return
      }

      if (filteredCommands.length > 0 && commandQueryActive) {
        if (event.key === 'ArrowDown') {
          event.preventDefault()
          setActiveCommandIndex((current) => (current + 1) % filteredCommands.length)
          return
        }
        if (event.key === 'ArrowUp') {
          event.preventDefault()
          setActiveCommandIndex((current) => (current - 1 + filteredCommands.length) % filteredCommands.length)
          return
        }
        if (event.key === 'Tab') {
          event.preventDefault()
          const selected = filteredCommands[activeCommandIndex]
          if (selected) {
            applyCommand(selected.name)
          }
          return
        }
        if (event.key === 'Escape') {
          event.preventDefault()
          return
        }
        if (event.key === 'Enter' && !event.shiftKey) {
          const selected = filteredCommands[activeCommandIndex]
          if (selected) {
            event.preventDefault()
            applyCommand(selected.name)
            return
          }
        }
      }

      if (event.key === 'Enter' && !event.shiftKey) {
        if (sendDisabled) return
        event.preventDefault()
        void onSubmit()
      }
    },
    [activeCommandIndex, applyCommand, commandQueryActive, filteredCommands, onSubmit, sendDisabled]
  )

  const showRunningIndicator = showStopButton || stopping

  const textareaRightInset = React.useMemo(() => {
    const base = layoutMetrics.actionsWidth > 0 ? layoutMetrics.actionsWidth + 28 : showRunningIndicator ? 160 : 96
    return Math.max(base, showRunningIndicator ? 140 : 88)
  }, [layoutMetrics.actionsWidth, showRunningIndicator])

  const resolvedHint = React.useMemo(() => {
    const available = Math.max(0, layoutMetrics.shellWidth - layoutMetrics.actionsWidth - 44)
    return compactHintText(enterHint, available)
  }, [enterHint, layoutMetrics.actionsWidth, layoutMetrics.shellWidth])

  const handleAttachmentInput = React.useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      const files = Array.from(event.target.files ?? [])
      if (files.length > 0) {
        onQueueFiles?.(files)
      }
      event.target.value = ''
    },
    [onQueueFiles]
  )

  const handleDrop = React.useCallback(
    (event: React.DragEvent<HTMLDivElement>) => {
      if (!onQueueFiles) return
      const files = Array.from(event.dataTransfer.files ?? [])
      if (!files.length) return
      event.preventDefault()
      onQueueFiles(files)
    },
    [onQueueFiles]
  )

  const handlePaste = React.useCallback(
    (event: React.ClipboardEvent<HTMLTextAreaElement>) => {
      if (!onQueueFiles) return
      const files = Array.from(event.clipboardData.files ?? [])
      if (!files.length) return
      event.preventDefault()
      onQueueFiles(files)
    },
    [onQueueFiles]
  )

  return (
    <div className="relative" data-copilot-composer="true">
      {filteredCommands.length > 0 ? (
        <div className="absolute bottom-full left-0 right-0 z-10 mb-2 overflow-hidden rounded-[16px] border border-black/[0.08] bg-[rgba(252,250,246,0.98)] shadow-[0_20px_44px_-34px_rgba(24,28,32,0.24)] backdrop-blur-xl dark:border-white/[0.10] dark:bg-[rgba(28,31,36,0.98)]">
          {filteredCommands.map((item, index) => {
            const active = index === activeCommandIndex
            return (
              <button
                key={item.name}
                type="button"
                className={cn(
                  'flex w-full items-center gap-2 px-3 py-2.5 text-left text-[12px] leading-5 transition',
                  active ? 'bg-black/[0.05] dark:bg-white/[0.08]' : 'hover:bg-black/[0.03] dark:hover:bg-white/[0.05]'
                )}
                onMouseEnter={() => setActiveCommandIndex(index)}
                onClick={() => applyCommand(item.name)}
              >
                <Slash className="h-3.5 w-3.5 text-muted-foreground" />
                <span className="font-medium text-foreground">/{item.name}</span>
                {item.description ? (
                  <span className="ml-auto line-clamp-1 text-[12px] text-muted-foreground">
                    {item.description}
                  </span>
                ) : null}
              </button>
            )
          })}
        </div>
      ) : null}

      {showRunningIndicator ? (
        <div
          className="pointer-events-none absolute right-4 top-0 z-[11] -translate-y-1/2"
          aria-hidden="true"
        >
          <OrbitLogoStatus
            compact
            sizePx={26}
            className="shrink-0 gap-0"
            resetKey={stopping ? 'stopping' : 'running'}
          />
        </div>
      ) : null}

      <div
        ref={shellRef}
        className="relative overflow-hidden rounded-[18px] border border-black/[0.08] bg-[rgba(252,250,246,0.94)] shadow-[0_14px_34px_-30px_rgba(24,28,32,0.22)] dark:border-white/[0.10] dark:bg-[rgba(28,31,36,0.9)]"
        onDragOver={(event) => {
          if (!onQueueFiles) return
          event.preventDefault()
        }}
        onDrop={handleDrop}
      >
        <input
          ref={fileInputRef}
          type="file"
          multiple
          className="hidden"
          onChange={handleAttachmentInput}
        />
        {hasAttachments ? (
          <div className="px-3.5 pt-3 pb-1">
            <div className="flex justify-end">
              <div className="flex max-w-full gap-2 overflow-x-auto pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
              {attachments.map((attachment) => {
                const isImage = String(attachment.contentType || '').startsWith('image/')
                const previewUrl = attachment.previewUrl || attachment.assetUrl || undefined
                const statusText =
                  attachment.status === 'success'
                    ? isImage
                      ? 'Image'
                      : 'File'
                    : attachment.status === 'failed'
                      ? 'Upload failed'
                      : attachment.status === 'uploading'
                        ? `${attachment.progress}%`
                        : 'Queued'
                return (
                  <div
                    key={attachment.draftId}
                    title={
                      attachment.status === 'failed'
                        ? attachment.error || attachment.name
                        : attachment.name
                    }
                    className={cn(
                      'group relative flex h-11 min-w-0 max-w-[228px] shrink-0 items-center gap-2.5 overflow-hidden rounded-full border px-2.5 pr-8',
                      'border-black/[0.06] bg-black/[0.03] dark:border-white/[0.08] dark:bg-white/[0.05]',
                      attachment.status === 'failed' && 'border-rose-300/70 bg-rose-50/70 dark:border-rose-400/40 dark:bg-rose-500/10'
                    )}
                  >
                    <div className="shrink-0">
                      {isImage && previewUrl ? (
                        <img
                          src={previewUrl}
                          alt={attachment.name}
                          className="h-8 w-8 rounded-[10px] object-cover ring-1 ring-black/6 dark:ring-white/10"
                        />
                      ) : (
                        <div className="flex h-8 w-8 items-center justify-center rounded-[10px] bg-black/[0.04] text-muted-foreground dark:bg-white/[0.06]">
                          {isImage ? <ImageIcon className="h-3.5 w-3.5" /> : <FileText className="h-3.5 w-3.5" />}
                        </div>
                      )}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-[12px] font-medium leading-4 text-foreground">
                        {attachment.name}
                      </div>
                      <div
                        className={cn(
                          'mt-0.5 truncate text-[10px] leading-4 text-muted-foreground',
                          attachment.status === 'failed' && 'text-rose-600 dark:text-rose-300'
                        )}
                      >
                        {statusText}
                      </div>
                    </div>
                    <div className="absolute inset-x-0 bottom-0 h-px bg-black/[0.05] dark:bg-white/[0.08]">
                      <div
                        className={cn(
                          'h-full transition-[width] duration-200 ease-out',
                          attachment.status === 'failed'
                            ? 'bg-rose-400'
                            : attachment.status === 'success'
                              ? 'bg-emerald-500'
                              : 'bg-[#9b8352]'
                        )}
                        style={{
                          width: `${attachment.status === 'failed' ? 100 : attachment.progress || (attachment.status === 'success' ? 100 : 0)}%`,
                        }}
                      />
                    </div>
                    <button
                      type="button"
                      className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded-full p-1 text-muted-foreground transition hover:bg-black/[0.05] hover:text-foreground dark:hover:bg-white/[0.08]"
                      onClick={() => onRemoveAttachment?.(attachment.draftId)}
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </div>
                )
              })}
              </div>
            </div>
          </div>
        ) : null}
        <textarea
          ref={textareaRef}
          value={value}
          rows={MIN_ROWS}
          data-copilot-textarea="true"
          className={cn(
            'block w-full resize-none border-0 bg-transparent px-4 pt-4 pb-14 text-[12.5px] leading-[1.7] text-foreground outline-none placeholder:text-muted-foreground/90'
          )}
          style={{ paddingRight: `${textareaRightInset}px` }}
          placeholder={placeholder}
          onChange={(event) => onValueChange(event.target.value)}
          onKeyDown={handleKeyDown}
          onPaste={handlePaste}
        />

        <div className="absolute inset-x-0 bottom-0 flex items-center justify-between px-4 pb-3">
          <div className="min-w-0 pr-4 text-[12px] leading-5 text-muted-foreground">
            <div className="flex items-center gap-2">
              {onQueueFiles ? (
                <button
                  type="button"
                  className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-black/[0.08] bg-white/[0.78] text-foreground transition hover:bg-black/[0.03] dark:border-white/[0.10] dark:bg-white/[0.04] dark:hover:bg-white/[0.08]"
                  onClick={() => fileInputRef.current?.click()}
                  aria-label="Attach files"
                >
                  <Paperclip className="h-4 w-4" />
                </button>
              ) : null}
              {resolvedHint ? (
                <span className="block truncate" title={enterHint}>
                  {resolvedHint}
                </span>
              ) : null}
            </div>
          </div>

          <div ref={actionsRef} className="flex shrink-0 items-center gap-2">
            {showStopButton || stopping ? (
              <button
                type="button"
                className="inline-flex h-8 items-center rounded-full border border-black/[0.08] bg-white/[0.82] px-3 text-[12px] font-medium text-foreground transition hover:bg-black/[0.03] disabled:cursor-not-allowed disabled:opacity-50 dark:border-white/[0.10] dark:bg-white/[0.04] dark:hover:bg-white/[0.08]"
                disabled={stopping}
                onClick={() => {
                  if (!onStop) return
                  void onStop()
                }}
              >
                {stopping ? (
                  <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Square className="mr-1.5 h-3.5 w-3.5" />
                )}
                {stopLabel}
              </button>
            ) : null}

            <button
              type="button"
              className="inline-flex h-8 items-center rounded-full bg-[#2F3437] px-3 text-[12px] font-medium text-white transition hover:bg-[#23282b] disabled:cursor-not-allowed disabled:opacity-50 dark:bg-[#E7DFD2] dark:text-[#1E1D1A] dark:hover:bg-[#efe7dc]"
              disabled={sendDisabled}
              onClick={() => {
                void onSubmit()
              }}
            >
              {submitting ? (
                <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
              ) : (
                <ArrowUp className="mr-1.5 h-3.5 w-3.5" />
              )}
              {sendLabel}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

export default QuestCopilotComposer
