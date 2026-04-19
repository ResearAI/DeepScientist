'use client'

import * as React from 'react'
import { CornerDownLeft, Search } from 'lucide-react'

import { FileIcon } from '@/components/file-tree'
import { useI18n } from '@/lib/i18n/useI18n'
import { flattenFileNodes } from '@/lib/search/file-search'
import type { FileNode } from '@/lib/types/file'
import { cn } from '@/lib/utils'
import {
  normalizeProjectRelativePath,
  toProjectRelativeDisplayPath,
} from '@/lib/utils/project-relative-path'

type ExplorerPathResult = {
  node: FileNode
  score: number
  exact: boolean
  displayPath: string
}

const MAX_RESULTS = 8

function searchablePath(node: FileNode): string {
  return normalizeProjectRelativePath(node.path || node.name)
}

function scoreExplorerPathNode(node: FileNode, query: string, rawQuery: string): number {
  const normalizedPath = searchablePath(node)
  if (!normalizedPath) return 0

  const path = normalizedPath.toLowerCase()
  const q = query.toLowerCase()
  const name = String(node.name || '').toLowerCase()
  const prefersFolder = rawQuery.trim().endsWith('/')
  const querySegments = q.split('/').filter(Boolean)

  let score = 0
  if (path === q) score += 1600
  if (path.startsWith(q)) score += Math.max(0, 1000 - (path.length - q.length))
  if (path.includes(`/${q}`)) score += 640
  if (path.includes(q)) score += 420
  if (name === q) score += 540
  if (name.startsWith(q)) score += 360
  if (name.includes(q)) score += 220
  if (querySegments.length > 1 && querySegments.every((segment) => path.includes(segment))) {
    score += 160
  }
  if (node.type !== 'folder') {
    score += 24
  }
  if (prefersFolder && node.type === 'folder') {
    score += 80
  }
  return score
}

function buildExplorerPathResults(nodes: FileNode[], rawQuery: string): ExplorerPathResult[] {
  const normalizedQuery = normalizeProjectRelativePath(rawQuery)
  if (!normalizedQuery) return []

  return nodes
    .map((node) => {
      const normalizedPath = searchablePath(node)
      const score = scoreExplorerPathNode(node, normalizedQuery, rawQuery)
      return {
        node,
        score,
        exact: normalizedPath.toLowerCase() === normalizedQuery.toLowerCase(),
        displayPath: toProjectRelativeDisplayPath(normalizedPath),
      }
    })
    .filter((entry) => entry.score > 0)
    .sort((left, right) => {
      if (left.exact !== right.exact) return left.exact ? -1 : 1
      if (left.score !== right.score) return right.score - left.score
      if (left.node.type !== right.node.type) return left.node.type === 'folder' ? -1 : 1
      return left.displayPath.localeCompare(right.displayPath)
    })
    .slice(0, MAX_RESULTS)
}

export interface ExplorerPathBarProps {
  nodes: FileNode[]
  loading?: boolean
  disabled?: boolean
  className?: string
  onReveal: (node: FileNode) => void
}

export function ExplorerPathBar({
  nodes,
  loading = false,
  disabled = false,
  className,
  onReveal,
}: ExplorerPathBarProps) {
  const { t } = useI18n('workspace')
  const inputRef = React.useRef<HTMLInputElement | null>(null)
  const closeTimerRef = React.useRef<number | null>(null)
  const suppressFocusOpenRef = React.useRef(false)
  const listboxId = React.useId()
  const [query, setQuery] = React.useState('')
  const [open, setOpen] = React.useState(false)
  const [activeIndex, setActiveIndex] = React.useState(0)

  const flatNodes = React.useMemo(() => flattenFileNodes(nodes), [nodes])
  const results = React.useMemo(() => buildExplorerPathResults(flatNodes, query), [flatNodes, query])
  const normalizedQuery = React.useMemo(() => normalizeProjectRelativePath(query), [query])

  React.useEffect(() => {
    setActiveIndex(0)
  }, [normalizedQuery, results.length])

  React.useEffect(() => {
    return () => {
      if (closeTimerRef.current != null) {
        window.clearTimeout(closeTimerRef.current)
      }
    }
  }, [])

  const exactResult = React.useMemo(
    () =>
      results.find((entry) => entry.exact) ||
      (normalizedQuery
        ? buildExplorerPathResults(flatNodes, normalizedQuery).find((entry) => entry.exact) || null
        : null),
    [flatNodes, normalizedQuery, results]
  )

  const visible = open && normalizedQuery.length > 0

  const handleSelect = React.useCallback(
    (node: FileNode) => {
      const nextPath = toProjectRelativeDisplayPath(node.path || node.name)
      setQuery(nextPath)
      setOpen(false)
      setActiveIndex(0)
      onReveal(node)
      suppressFocusOpenRef.current = true
      window.requestAnimationFrame(() => {
        inputRef.current?.focus()
        inputRef.current?.setSelectionRange(nextPath.length, nextPath.length)
      })
    },
    [onReveal]
  )

  const handleCommit = React.useCallback(() => {
    const target = results[activeIndex] || exactResult || results[0]
    if (!target) return
    handleSelect(target.node)
  }, [activeIndex, exactResult, handleSelect, results])

  const handleInputBlur = React.useCallback(() => {
    closeTimerRef.current = window.setTimeout(() => {
      setOpen(false)
    }, 120)
  }, [])

  const handleInputFocus = React.useCallback(() => {
    if (closeTimerRef.current != null) {
      window.clearTimeout(closeTimerRef.current)
      closeTimerRef.current = null
    }
    if (suppressFocusOpenRef.current) {
      suppressFocusOpenRef.current = false
      return
    }
    if (normalizedQuery) {
      setOpen(true)
    }
  }, [normalizedQuery])

  return (
    <div className={cn('explorer-pathbar', className)} data-explorer-pathbar="true">
      <div
        className={cn(
          'explorer-pathbar-field',
          visible && 'is-open',
          disabled && 'is-disabled'
        )}
      >
        <Search className="h-3.5 w-3.5 explorer-pathbar-icon" />
        <input
          ref={inputRef}
          type="text"
          value={query}
          disabled={disabled}
          onFocus={handleInputFocus}
          onBlur={handleInputBlur}
          onChange={(event) => {
            setQuery(event.target.value)
            setOpen(true)
          }}
          onKeyDown={(event) => {
            if (event.key === 'ArrowDown') {
              if (!results.length) return
              event.preventDefault()
              setOpen(true)
              setActiveIndex((current) => (current + 1) % results.length)
              return
            }
            if (event.key === 'ArrowUp') {
              if (!results.length) return
              event.preventDefault()
              setOpen(true)
              setActiveIndex((current) => (current - 1 + results.length) % results.length)
              return
            }
            if (event.key === 'Escape') {
              if (visible) {
                event.preventDefault()
                setOpen(false)
              }
              return
            }
            if (event.key === 'Enter') {
              event.preventDefault()
              handleCommit()
            }
          }}
          placeholder={
            disabled
              ? t('explorer_path_placeholder_disabled', undefined, 'Explorer is unavailable right now.')
              : loading
                ? t('explorer_path_placeholder_loading', undefined, 'Indexing workspace paths…')
                : t('explorer_path_placeholder', undefined, 'Jump to /path/to/file')
          }
          className="explorer-pathbar-input"
          role="combobox"
          aria-expanded={visible}
          aria-controls={visible ? listboxId : undefined}
          aria-autocomplete="list"
          aria-label={t('explorer_path_input_label', undefined, 'Jump to path')}
          data-explorer-path-input="true"
        />
        {normalizedQuery ? (
          <div className="explorer-pathbar-hint" aria-hidden="true">
            <CornerDownLeft className="h-3 w-3" />
            <span>{t('explorer_path_enter_hint', undefined, 'Jump')}</span>
          </div>
        ) : null}
      </div>

      {visible ? (
        <div
          id={listboxId}
          className="explorer-pathbar-results"
          role="listbox"
          aria-label={t('explorer_path_results', undefined, 'Path matches')}
          data-explorer-path-results="true"
        >
          {results.length > 0 ? (
            results.map((result, index) => {
              const isActive = index === activeIndex
              return (
                <button
                  key={`${result.node.id}:${result.displayPath}`}
                  type="button"
                  role="option"
                  aria-selected={isActive}
                  className={cn('explorer-pathbar-option', isActive && 'is-active')}
                  onMouseDown={(event) => {
                    event.preventDefault()
                    handleSelect(result.node)
                  }}
                  onMouseEnter={() => setActiveIndex(index)}
                  data-explorer-path-option={result.displayPath}
                >
                  <span className="explorer-pathbar-option-icon">
                    <FileIcon
                      type={result.node.type}
                      folderKind={result.node.folderKind}
                      mimeType={result.node.mimeType}
                      name={result.node.name}
                      isOpen={result.node.type === 'folder'}
                    />
                  </span>
                  <span className="explorer-pathbar-option-copy">
                    <span className="explorer-pathbar-option-name">{result.node.name}</span>
                    <span className="explorer-pathbar-option-path">{result.displayPath}</span>
                  </span>
                  <span className="explorer-pathbar-option-kind">
                    {result.node.type === 'folder'
                      ? t('explorer_path_kind_folder', undefined, 'Folder')
                      : t('explorer_path_kind_file', undefined, 'File')}
                  </span>
                </button>
              )
            })
          ) : (
            <div className="explorer-pathbar-empty">
              {t('explorer_path_no_results', undefined, 'No matching path found.')}
            </div>
          )}
        </div>
      ) : null}
    </div>
  )
}

export default ExplorerPathBar
