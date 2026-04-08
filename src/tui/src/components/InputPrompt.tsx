import React, { useEffect, useMemo, useRef, useState } from 'react'
import { Box, Text, useInput, useStdin } from 'ink'
import stringWidth from 'string-width'
import { theme } from '../semantic-colors.js'
import { useTerminalSize } from '../hooks/useTerminalSize.js'

type InputPromptProps = {
  value: string
  placeholder?: string
  disabled?: boolean
  glowActive?: boolean
  suggestionsVisible?: boolean
  mentionsEnabled?: boolean
  selectedSuggestion?: { command: string; requiresArg?: boolean } | null
  onSuggestionNavigate?: (direction: number) => void
  historyItems?: string[]
  historyKey?: string
  onChange: (next: string) => void
  onSubmit: (override?: string) => void
  onCancel: () => void
}

const PASTE_START = '\x1b[200~'
const PASTE_END = '\x1b[201~'
const PASTE_START_BARE = '[200~'
const PASTE_END_BARE = '[201~'
const PASTE_START_TOKENS = [PASTE_START, PASTE_START_BARE]
const PASTE_END_TOKENS = [PASTE_END, PASTE_END_BARE]
const MODIFIED_ENTER_SEQUENCES = new Set(['\x1b[13;2u', '\x1b[13;5u', '\x1b[27;2;13~'])
const BARE_ENTER_SEQUENCES = new Set(['\r', '\n'])

const clampCursor = (value: string, cursorIndex: number) =>
  Math.max(0, Math.min(cursorIndex, value.length))

const padToWidth = (value: string, width: number) => {
  const currentWidth = stringWidth(value)
  if (currentWidth >= width) return value
  return `${value}${' '.repeat(width - currentWidth)}`
}

const wrapTextWithCursor = (
  text: string,
  cursorIndex: number,
  firstWidth: number,
  otherWidth: number
) => {
  const safeFirst = Math.max(1, firstWidth)
  const safeOther = Math.max(1, otherWidth)
  const clampedCursor = clampCursor(text, cursorIndex)
  const lines: string[] = ['']
  const lineWidths: number[] = [0]
  const lineCharCounts: number[] = [0]
  let isFirst = true
  let lineIndex = 0
  let columnWidth = 0
  let codeUnitIndex = 0
  let cursorRow = 0
  let cursorCharIndex = 0

  const setCursor = () => {
    cursorRow = lineIndex
    cursorCharIndex = lineCharCounts[lineIndex] ?? 0
  }

  for (const char of text) {
    if (codeUnitIndex === clampedCursor) {
      setCursor()
    }
    if (char === '\n') {
      lines.push('')
      lineWidths.push(0)
      lineCharCounts.push(0)
      lineIndex += 1
      columnWidth = 0
      isFirst = false
      codeUnitIndex += char.length
      continue
    }

    const widthLimit = isFirst ? safeFirst : safeOther
    const charWidth = Math.max(0, stringWidth(char))

    if (columnWidth + charWidth > widthLimit && columnWidth > 0) {
      lines.push('')
      lineWidths.push(0)
      lineCharCounts.push(0)
      lineIndex += 1
      columnWidth = 0
      isFirst = false
    }

    lines[lineIndex] += char
    columnWidth += charWidth
    lineWidths[lineIndex] = columnWidth
    lineCharCounts[lineIndex] += 1
    codeUnitIndex += char.length
  }

  if (codeUnitIndex === clampedCursor) {
    setCursor()
  }

  const finalWidth = cursorRow === 0 ? safeFirst : safeOther
  const cursorLineWidth = lineWidths[cursorRow] ?? 0
  const cursorLineChars = lineCharCounts[cursorRow] ?? 0
  if (cursorCharIndex >= cursorLineChars && cursorLineWidth >= finalWidth) {
    lines.push('')
    lineWidths.push(0)
    lineCharCounts.push(0)
    cursorRow += 1
    cursorCharIndex = 0
  }

  return { lines, lineWidths, cursorRow, cursorCharIndex }
}

const normalizeNewlines = (text: string) => text.replace(/\r\n/g, '\n').replace(/\r/g, '\n')

const splitTrailingPartial = (data: string, token: string) => {
  const maxCheck = Math.min(token.length - 1, data.length)
  for (let i = maxCheck; i > 0; i -= 1) {
    const suffix = data.slice(-i)
    if (token.startsWith(suffix)) {
      return { head: data.slice(0, -i), tail: suffix }
    }
  }
  return { head: data, tail: '' }
}

const splitTrailingPartialAny = (data: string, tokens: string[]) => {
  let best = { head: data, tail: '' }
  for (const token of tokens) {
    const candidate = splitTrailingPartial(data, token)
    if (candidate.tail.length > best.tail.length) {
      best = candidate
    }
  }
  return best
}

const hasPasteTokenFragment = (data: string) => {
  if (!data) {
    return false
  }
  return splitTrailingPartialAny(data, [...PASTE_START_TOKENS, ...PASTE_END_TOKENS]).tail.length > 0
}

const findToken = (data: string, tokens: string[]) => {
  let bestIndex = -1
  let bestToken: string | null = null
  for (const token of tokens) {
    const index = data.indexOf(token)
    if (index !== -1 && (bestIndex === -1 || index < bestIndex)) {
      bestIndex = index
      bestToken = token
    }
  }
  return { index: bestIndex, token: bestToken }
}

const buildMentionRanges = (text: string, mentionsEnabled: boolean) => {
  if (!mentionsEnabled) return []
  if (!text.startsWith('@')) return []
  const ranges: Array<{ start: number; end: number }> = []
  const match = text.match(/^@[a-zA-Z0-9_-]+/)
  if (match) {
    ranges.push({ start: 0, end: match[0].length })
  }
  return ranges
}

const getLeadingMentionDeleteRange = (text: string) => {
  if (!text.startsWith('@')) return null
  const firstSpace = text.search(/\s/)
  const end = firstSpace === -1 ? text.length : firstSpace
  let deleteEnd = end
  if (text[deleteEnd] === ' ') {
    deleteEnd += 1
  }
  return { start: 0, end: Math.min(deleteEnd, text.length) }
}

const isMentionIndex = (ranges: Array<{ start: number; end: number }>, index: number) =>
  ranges.some((range) => index >= range.start && index < range.end)

const renderMentionSegments = (
  text: string,
  offset: number,
  ranges: Array<{ start: number; end: number }>,
  baseColor: string,
  mentionColor: string,
  keyPrefix: string
) => {
  if (!text) return null
  const nodes: React.ReactNode[] = []
  let buffer = ''
  let currentColor = isMentionIndex(ranges, offset) ? mentionColor : baseColor
  for (let i = 0; i < text.length; i += 1) {
    const nextColor = isMentionIndex(ranges, offset + i) ? mentionColor : baseColor
    if (nextColor !== currentColor) {
      if (buffer) {
        nodes.push(
          <Text key={`${keyPrefix}-${nodes.length}`} color={currentColor}>
            {buffer}
          </Text>
        )
        buffer = ''
      }
      currentColor = nextColor
    }
    buffer += text[i]
  }
  if (buffer) {
    nodes.push(
      <Text key={`${keyPrefix}-${nodes.length}`} color={currentColor}>
        {buffer}
      </Text>
    )
  }
  return nodes
}

export const InputPrompt: React.FC<InputPromptProps> = ({
  value,
  placeholder = 'Type a message',
  disabled,
  glowActive = false,
  suggestionsVisible = false,
  selectedSuggestion,
  onSuggestionNavigate,
  historyItems = [],
  historyKey,
  onChange,
  onSubmit,
  onCancel,
  mentionsEnabled = false,
}) => {
  const { isRawModeSupported } = useStdin()
  const canUseInput = Boolean(isRawModeSupported)
  const { columns } = useTerminalSize()
  const valueRef = useRef(value)
  const cursorIndexRef = useRef(value.length)
  const pasteActiveRef = useRef(false)
  const pasteBufferRef = useRef('')
  const pastePendingRef = useRef('')
  const historyRef = useRef<string[]>(historyItems)
  const historyStashRef = useRef('')
  const [historyIndex, setHistoryIndex] = useState<number | null>(null)
  const [cursorIndex, setCursorIndex] = useState(value.length)

  const outerWidth = Math.max(10, columns)
  const innerWidth = Math.max(4, outerWidth - 2)
  const prefix = '> '
  const indent = '  '
  const firstLineWidth = Math.max(1, innerWidth - prefix.length)
  const otherLineWidth = Math.max(1, innerWidth - indent.length)
  const isPlaceholder = value.length === 0
  const { contentLines, cursorRow, cursorCharIndex } = useMemo(() => {
    const minRows = 2
    const wrappedValue = wrapTextWithCursor(value, cursorIndex, firstLineWidth, otherLineWidth)
    const wrappedDisplay = isPlaceholder
      ? wrapTextWithCursor(placeholder, 0, firstLineWidth, otherLineWidth)
      : wrappedValue
    const padded = [...wrappedDisplay.lines]
    while (padded.length < minRows) {
      padded.push('')
    }
    while (wrappedValue.cursorRow >= padded.length) {
      padded.push('')
    }
    return {
      contentLines: padded,
      cursorRow: wrappedValue.cursorRow,
      cursorCharIndex: wrappedValue.cursorCharIndex,
    }
  }, [value, cursorIndex, firstLineWidth, otherLineWidth, isPlaceholder, placeholder])

  const outerHeight = contentLines.length + 2
  const borderColor = glowActive ? theme.text.accent : theme.border.default
  const cursorBackground = theme.ui.cursor.background
  const cursorTextColor = theme.ui.cursor.text

  const topBorder = useMemo(() => {
    const middle = '─'.repeat(Math.max(0, outerWidth - 2))
    return `╭${middle}╮`
  }, [outerWidth])

  const bottomBorder = useMemo(() => {
    const middle = '─'.repeat(Math.max(0, outerWidth - 2))
    return `╰${middle}╯`
  }, [outerWidth])

  useEffect(() => {
    const isExternal = value !== valueRef.current
    valueRef.current = value
    if (isExternal) {
      const nextCursor = value.length
      cursorIndexRef.current = nextCursor
      setCursorIndex(nextCursor)
    } else {
      cursorIndexRef.current = clampCursor(value, cursorIndexRef.current)
      setCursorIndex((prev) => clampCursor(value, prev))
    }
    if (value === '' && historyIndex !== null) {
      setHistoryIndex(null)
      historyStashRef.current = ''
    }
  }, [value, historyIndex])

  useEffect(() => {
    historyRef.current = historyItems
    if (historyIndex !== null && historyIndex >= historyItems.length) {
      setHistoryIndex(null)
      historyStashRef.current = ''
    }
  }, [historyItems, historyIndex])

  useEffect(() => {
    if (historyKey === undefined) return
    setHistoryIndex(null)
    historyStashRef.current = ''
  }, [historyKey])

  const setValue = (next: string, nextCursor?: number) => {
    valueRef.current = next
    onChange(next)
    const clamped = clampCursor(next, nextCursor ?? cursorIndexRef.current)
    cursorIndexRef.current = clamped
    setCursorIndex(clamped)
  }

  const insertValue = (text: string) => {
    if (!text) return
    const current = valueRef.current
    const cursor = clampCursor(current, cursorIndexRef.current)
    const next = `${current.slice(0, cursor)}${text}${current.slice(cursor)}`
    setValue(next, cursor + text.length)
  }

  const deleteBeforeCursor = (count: number) => {
    if (count <= 0) return
    const current = valueRef.current
    const cursor = clampCursor(current, cursorIndexRef.current)
    if (cursor === 0) return
    const removeStart = Math.max(0, cursor - count)
    const next = `${current.slice(0, removeStart)}${current.slice(cursor)}`
    setValue(next, removeStart)
  }

  const deleteAtCursor = (count: number) => {
    if (count <= 0) return
    const current = valueRef.current
    const cursor = clampCursor(current, cursorIndexRef.current)
    if (cursor >= current.length) return
    const next = `${current.slice(0, cursor)}${current.slice(cursor + count)}`
    setValue(next, cursor)
  }

  const moveCursor = (direction: number) => {
    const current = valueRef.current
    const nextCursor = clampCursor(current, cursorIndexRef.current + direction)
    cursorIndexRef.current = nextCursor
    setCursorIndex(nextCursor)
  }

  const handlePasteChunk = (chunk: string) => {
    let data = pastePendingRef.current + chunk
    pastePendingRef.current = ''
    let handled = false

    while (data.length > 0) {
      if (pasteActiveRef.current) {
        const { index: endIndex, token: endToken } = findToken(data, PASTE_END_TOKENS)
        if (endIndex === -1 || !endToken) {
          const { head, tail } = splitTrailingPartialAny(data, PASTE_END_TOKENS)
          pasteBufferRef.current += head
          if (tail) pastePendingRef.current = tail
          return true
        }
        pasteBufferRef.current += data.slice(0, endIndex)
        insertValue(normalizeNewlines(pasteBufferRef.current))
        pasteBufferRef.current = ''
        pasteActiveRef.current = false
        handled = true
        data = data.slice(endIndex + endToken.length)
        continue
      }

      const { index: startIndex, token: startToken } = findToken(data, PASTE_START_TOKENS)
      if (startIndex === -1 || !startToken) {
        const { head, tail } = splitTrailingPartialAny(data, PASTE_START_TOKENS)
        if (head) {
          insertValue(head)
          handled = true
        }
        if (tail) {
          pastePendingRef.current = tail
          return true
        }
        return handled
      }

      if (startIndex > 0) {
        insertValue(data.slice(0, startIndex))
        handled = true
      }
      data = data.slice(startIndex + startToken.length)
      pasteActiveRef.current = true
    }

    return handled || pasteActiveRef.current || pastePendingRef.current.length > 0
  }

  useInput(
    (input, key) => {
      if (disabled) return
      const submitRequested = key.return || BARE_ENTER_SEQUENCES.has(input)
      const newlineRequested = (key.return && key.shift) || MODIFIED_ENTER_SEQUENCES.has(input)
      if (key.ctrl && (input === 'c' || input === '\u0003')) {
        return
      }
      const hasPasteMarkers =
        pasteActiveRef.current ||
        pastePendingRef.current.length > 0 ||
        PASTE_START_TOKENS.some((token) => input.includes(token)) ||
        PASTE_END_TOKENS.some((token) => input.includes(token)) ||
        hasPasteTokenFragment(input)

      if (hasPasteMarkers) {
        const handled = handlePasteChunk(input)
        if (handled) return
      }

      const backspaceMatches = input.match(/[\x7f\b]/g)
      if (key.backspace || backspaceMatches) {
        const removalCount = Math.max(backspaceMatches?.length || 0, key.backspace ? 1 : 0)
        if (removalCount > 0) {
          if (mentionsEnabled) {
            const range = getLeadingMentionDeleteRange(valueRef.current)
            const currentCursorIndex = cursorIndexRef.current
            if (range && currentCursorIndex > 0 && currentCursorIndex <= range.end) {
              const nextValue = valueRef.current.slice(range.end)
              setValue(nextValue, 0)
              return
            }
          }
          deleteBeforeCursor(removalCount)
          const cleanedInput = input.replace(/[\x7f\b]/g, '')
          if (cleanedInput) {
            insertValue(cleanedInput)
          }
          return
        }
      }

      if (key.delete) {
        const current = valueRef.current
        const cursor = clampCursor(current, cursorIndexRef.current)
        if (cursor < current.length) {
          deleteAtCursor(1)
        } else {
          deleteBeforeCursor(1)
        }
        return
      }

      if ((key.ctrl || key.meta) && !(key.ctrl && input === 'j')) {
        return
      }

      if (suggestionsVisible) {
        if ((key.upArrow || key.downArrow) && onSuggestionNavigate) {
          onSuggestionNavigate(key.upArrow ? -1 : 1)
          return
        }
        if (submitRequested && !newlineRequested) {
          const currentValue = valueRef.current
          const suggestion = selectedSuggestion?.command
          if (suggestion) {
            const trimmedInput = currentValue.trim()
            const normalizedInput = trimmedInput.toLowerCase()
            const normalizedSuggestion = suggestion.toLowerCase()
            const isPrefix = normalizedSuggestion.startsWith(normalizedInput)
            const isShorterOrEqual = trimmedInput.length <= suggestion.length
            const shouldComplete = isPrefix && isShorterOrEqual
            if (selectedSuggestion?.requiresArg && shouldComplete) {
              if (normalizedInput === normalizedSuggestion) {
                onSubmit(suggestion)
              } else {
                const nextValue = `${suggestion} `
                setValue(nextValue, nextValue.length)
              }
              return
            }
            if (shouldComplete) {
              onSubmit(suggestion)
              return
            }
          }
          onSubmit(currentValue)
          return
        }
      }

      if (!suggestionsVisible && (key.upArrow || key.downArrow)) {
        const history = historyRef.current
        if (history.length === 0) return
        const direction = key.upArrow ? -1 : 1
        if (historyIndex === null) {
          if (direction > 0) return
          historyStashRef.current = valueRef.current
          const newIndex = history.length - 1
          setHistoryIndex(newIndex)
          const nextValue = history[newIndex] || ''
          setValue(nextValue, nextValue.length)
          return
        }
        const nextIndex = historyIndex + direction
        if (nextIndex < 0) {
          setHistoryIndex(0)
          const nextValue = history[0] || ''
          setValue(nextValue, nextValue.length)
          return
        }
        if (nextIndex >= history.length) {
          setHistoryIndex(null)
          const nextValue = historyStashRef.current || ''
          setValue(nextValue, nextValue.length)
          return
        }
        setHistoryIndex(nextIndex)
        const nextValue = history[nextIndex] || ''
        setValue(nextValue, nextValue.length)
        return
      }

      if (key.leftArrow) {
        moveCursor(-1)
        return
      }
      if (key.rightArrow) {
        moveCursor(1)
        return
      }

      if (newlineRequested) {
        insertValue('\n')
        return
      }

      if ((input.includes('\n') || input.includes('\r')) && input.length > 1) {
        insertValue(normalizeNewlines(input))
        return
      }

      if (key.escape) {
        onCancel()
        return
      }
      if (submitRequested) {
        onSubmit(valueRef.current)
        return
      }
      if (key.ctrl && input === 'j') {
        insertValue('\n')
        return
      }

      if (input.includes('\x1b')) {
        return
      }

      const sanitized = input.replace(/[\x00-\x1f\x7f]/g, '')
      if (!sanitized) return
      insertValue(sanitized)
    },
    { isActive: canUseInput && !disabled }
  )

  const textColor = isPlaceholder ? theme.text.secondary : theme.text.primary

  return (
    <Box flexDirection="column" width={outerWidth} height={outerHeight}>
      <Text color={borderColor}>{topBorder}</Text>
      {contentLines.map((line, rowIndex) => {
        const prefixText = rowIndex === 0 ? prefix : indent
        const prefixColor = rowIndex === 0 ? theme.text.accent : textColor
        const lineWidth = innerWidth - prefixText.length
        const paddedLine = padToWidth(line, Math.max(0, lineWidth))
        const showCursor = rowIndex === cursorRow
        const lineChars = Array.from(paddedLine)
        const safeCursorIndex = showCursor
          ? Math.min(cursorCharIndex, Math.max(0, lineChars.length - 1))
          : 0
        const beforeCursor = showCursor ? lineChars.slice(0, safeCursorIndex).join('') : paddedLine
        let cursorChar = showCursor ? lineChars[safeCursorIndex] || ' ' : ''
        const afterCursor = showCursor ? lineChars.slice(safeCursorIndex + 1).join('') : ''
        const mentionRanges = buildMentionRanges(paddedLine, mentionsEnabled)
        if (isPlaceholder && showCursor) {
          cursorChar = ' '
        }

        return (
          <Text key={`row-${rowIndex}`}>
            <Text color={borderColor}>│</Text>
            <Text color={prefixColor}>{prefixText}</Text>
            {renderMentionSegments(
              beforeCursor,
              0,
              mentionRanges,
              textColor,
              theme.text.mention,
              `row-${rowIndex}-before`
            )}
            {showCursor && (
              <Text backgroundColor={cursorBackground} color={cursorTextColor}>
                {cursorChar}
              </Text>
            )}
            {showCursor &&
              renderMentionSegments(
                afterCursor,
                safeCursorIndex + 1,
                mentionRanges,
                textColor,
                theme.text.mention,
                `row-${rowIndex}-after`
              )}
            <Text color={borderColor}>│</Text>
          </Text>
        )
      })}
      <Text color={borderColor}>{bottomBorder}</Text>
    </Box>
  )
}
