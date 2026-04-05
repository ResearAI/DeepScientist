'use client'

import { useCallback, useEffect, useRef } from 'react'
import type { MouseEvent } from 'react'
import type { IProgressState } from '@xterm/addon-progress'
import type { Terminal } from '@xterm/xterm'
import { useTerminal } from '../hooks/useTerminal'
import { useTerminalResize } from '../hooks/useTerminalResize'
import { TerminalSearchBar } from './TerminalSearchBar'
import { TerminalContextMenu } from './TerminalContextMenu'

export function EnhancedTerminal({
  onInput,
  onBinary,
  onResize,
  resizeKey,
  onReady,
  onProgress,
  searchOpen,
  onSearchOpenChange,
  appearance,
  autoFocus = true,
  showHeader = true,
  scrollback,
  convertEol,
}: {
  onInput: (data: string) => void
  onBinary?: (data: string) => void
  onResize: (cols: number, rows: number) => void
  resizeKey?: string | number | null
  onReady: (handlers: {
    write: (data: string, onComplete?: () => void) => void
    clear: () => void
    serialize: () => string
    resetProgress: () => void
    scrollToBottom: () => void
    focus: () => void
    search: (query: string) => boolean
    isScrolledToBottom: (thresholdPx?: number) => boolean
  }) => void
  onProgress?: (state: IProgressState) => void
  searchOpen: boolean
  onSearchOpenChange: (open: boolean) => void
  appearance?: 'terminal' | 'ui'
  autoFocus?: boolean
  showHeader?: boolean
  scrollback?: number
  convertEol?: boolean
}) {
  const enableAttach = process.env.NEXT_PUBLIC_CLI_ATTACH_ADDON === 'true'
  const scrollFollowThresholdPx = 120
  const { containerRef, fitAddonRef, terminalRef, write, clear, fit, search, serialize, resetProgress, scrollToBottom, focus } = useTerminal({
    onInput,
    onBinary,
    onReady: (terminal) => {
      if (!keyHandlerAttachedRef.current) {
        terminal.attachCustomKeyEventHandler((event) => {
          const hasModifier = event.ctrlKey || event.metaKey
          if (!hasModifier) return true
          if (event.key === 'c' || event.key === 'C') {
            const selection = terminal.getSelection()
            if (selection) {
              const canCopy = Boolean(navigator.clipboard?.writeText) || document.queryCommandSupported?.('copy')
              if (!canCopy) return true
              event.preventDefault()
              copyHandlerRef.current()
              return false
            }
            return true
          }
          if (event.key === 'v' || event.key === 'V') {
            if (!navigator.clipboard?.readText) return true
            event.preventDefault()
            pasteHandlerRef.current()
            return false
          }
          return true
        })
        keyHandlerAttachedRef.current = true
      }
      const isScrolledToBottom = (thresholdPx = scrollFollowThresholdPx) => {
        const root = terminalRef.current?.element
        if (!root) return true
        const viewport = root.querySelector('.xterm-viewport') as HTMLElement | null
        if (!viewport) return true
        const remaining = viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight
        return remaining <= thresholdPx
      }
      onReady({ write, clear, serialize, resetProgress, scrollToBottom, focus, search, isScrolledToBottom })
    },
    onProgress,
    enableAttach,
    appearance,
    autoFocus,
    scrollback,
    convertEol,
  })
  const getSize = useCallback(() => {
    if (!terminalRef.current?.element || !fitAddonRef.current) return null
    try {
      const dims = fitAddonRef.current.proposeDimensions()
      if (!dims || dims.cols <= 0 || dims.rows <= 0) return null
      return { cols: dims.cols, rows: dims.rows }
    } catch {
      return null
    }
  }, [fitAddonRef, terminalRef])

  const handleResize = useCallback((cols: number, rows: number) => {
    fit()
    onResize(cols, rows)
  }, [fit, onResize])

  useTerminalResize(containerRef, handleResize, getSize, resizeKey)

  const handleSearch = useCallback(
    (query: string) => {
      if (!query) return
      search(query)
    },
    [search]
  )

  const handleCopy = useCallback(async () => {
    const selection = terminalRef.current?.getSelection()
    if (!selection) return
    if (navigator.clipboard?.writeText) {
      try {
        await navigator.clipboard.writeText(selection)
        return
      } catch {
        // Ignore clipboard errors; fall back to document copy.
      }
    }
    try {
      document.execCommand('copy')
    } catch {
      // Ignore copy fallback errors.
    }
  }, [terminalRef])

  const handlePaste = useCallback(async () => {
    try {
      const text = await navigator.clipboard.readText()
      if (text) onInput(text)
    } catch {
      // Ignore clipboard errors; browser may block paste without permission.
    }
  }, [onInput])

  const copyHandlerRef = useRef(handleCopy)
  const pasteHandlerRef = useRef(handlePaste)
  const keyHandlerAttachedRef = useRef(false)

  useEffect(() => {
    copyHandlerRef.current = handleCopy
    pasteHandlerRef.current = handlePaste
  }, [handleCopy, handlePaste])

  const ensureTerminalFocus = useCallback((terminalInstance?: Terminal | null) => {
    if (terminalInstance) {
      terminalInstance.focus()
      return
    }
    terminalRef.current?.focus()
  }, [terminalRef])

  const handleMouseDown = useCallback(
    (event: MouseEvent<HTMLDivElement>) => {
      if (event.button !== 0) return
      ensureTerminalFocus()
    },
    [ensureTerminalFocus]
  )

  return (
    <div className="flex h-full min-h-0 flex-col gap-2">
      {showHeader ? (
        <div className="flex items-center justify-between">
          <div className="text-xs text-[var(--cli-muted-1)]">Terminal session</div>
          <div className="flex items-center gap-2">
            {searchOpen ? (
              <TerminalSearchBar onSearch={handleSearch} onClose={() => onSearchOpenChange(false)} />
            ) : null}
          </div>
        </div>
      ) : null}
      <TerminalContextMenu onCopy={handleCopy} onPaste={handlePaste}>
        <div className="cli-terminal flex-1" ref={containerRef} onMouseDown={handleMouseDown} />
      </TerminalContextMenu>
    </div>
  )
}
