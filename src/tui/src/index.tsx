import React from 'react'
import { render } from 'ink'

import { AppContainer } from './app/AppContainer.js'
import { setDaemonAuthToken } from './lib/api.js'
import { isAlternateBufferEnabled, isIncrementalRenderingEnabled } from './utils/terminal.js'

const CLEAR_TO_END = '\x1b[0K'
const BRACKETED_PASTE_ENABLE = '\x1b[?2004h'
const BRACKETED_PASTE_DISABLE = '\x1b[?2004l'

const withLineClearing = (stdout: NodeJS.WriteStream): NodeJS.WriteStream => {
  const transform = (chunk: unknown) => {
    const text = Buffer.isBuffer(chunk) ? chunk.toString('utf8') : String(chunk)
    if (!text) return text
    const cleared = text.replace(/\r?\n/g, (match) => `${CLEAR_TO_END}${match}`)
    return cleared.endsWith('\n') ? cleared : `${cleared}${CLEAR_TO_END}`
  }

  return new Proxy(stdout, {
    get(target, prop, receiver) {
      if (prop === 'write') {
        return (chunk: unknown, encoding?: unknown, callback?: unknown) =>
          (target as typeof stdout).write(transform(chunk), encoding as BufferEncoding, callback as () => void)
      }
      return Reflect.get(target, prop, receiver)
    },
  }) as NodeJS.WriteStream
}

function parseArg(name: string): string | null {
  const index = process.argv.indexOf(name)
  if (index >= 0 && index + 1 < process.argv.length) {
    return process.argv[index + 1] ?? null
  }
  return null
}

const baseUrl = parseArg('--base-url') ?? 'http://0.0.0.0:20999'
const questId = parseArg('--quest-id')
const authToken = parseArg('--auth-token')

setDaemonAuthToken(authToken)

const useAlternateBuffer = isAlternateBufferEnabled()
const useIncrementalRendering = isIncrementalRenderingEnabled()

const setBracketedPasteMode = (enabled: boolean) => {
  if (!process.stdout.isTTY) {
    return
  }
  try {
    process.stdout.write(enabled ? BRACKETED_PASTE_ENABLE : BRACKETED_PASTE_DISABLE)
  } catch {
    // Ignore terminal write failures during startup or shutdown.
  }
}

let bracketedPasteClosed = false
const closeBracketedPasteMode = () => {
  if (bracketedPasteClosed) {
    return
  }
  bracketedPasteClosed = true
  setBracketedPasteMode(false)
}

setBracketedPasteMode(true)
process.once('exit', closeBracketedPasteMode)

const instance = render(<AppContainer baseUrl={baseUrl} initialQuestId={questId} authToken={authToken} />, {
  stdout: withLineClearing(process.stdout),
  stderr: process.stderr,
  stdin: process.stdin,
  exitOnCtrlC: false,
  patchConsole: false,
  alternateBuffer: useAlternateBuffer,
  incrementalRendering: useIncrementalRendering,
})

void instance.waitUntilExit().finally(() => {
  closeBracketedPasteMode()
  process.off('exit', closeBracketedPasteMode)
})
