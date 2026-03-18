#!/usr/bin/env node

import { existsSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawnSync } from 'node:child_process'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const repoRoot = path.resolve(__dirname, '..')
const forceRebuild = ['1', 'true', 'yes', 'on'].includes(
  String(process.env.DEEPSCIENTIST_FORCE_REBUILD_BUNDLES || '')
    .trim()
    .toLowerCase()
)
const skipRebuild = ['1', 'true', 'yes', 'on'].includes(
  String(process.env.DEEPSCIENTIST_SKIP_BUNDLE_REBUILD || '')
    .trim()
    .toLowerCase()
)

function run(command, args, cwd = repoRoot) {
  const result = spawnSync(command, args, {
    cwd,
    stdio: 'inherit',
    env: process.env,
  })
  if (result.error) {
    throw result.error
  }
  if (result.status !== 0) {
    process.exit(result.status ?? 1)
  }
}

function ensureFile(relativePath) {
  const fullPath = path.join(repoRoot, relativePath)
  if (!existsSync(fullPath)) {
    console.error(`Missing required release artifact: ${relativePath}`)
    process.exit(1)
  }
}

const webBundle = 'src/ui/dist/index.html'
const tuiBundle = 'src/tui/dist/index.js'

if (!skipRebuild || forceRebuild) {
  run('npm', ['--prefix', 'src/ui', 'ci', '--include=dev', '--no-audit', '--no-fund'])
  run('npm', ['--prefix', 'src/ui', 'run', 'build'])

  run('npm', ['--prefix', 'src/tui', 'ci', '--include=dev', '--no-audit', '--no-fund'])
  run('npm', ['--prefix', 'src/tui', 'run', 'build'])
}

ensureFile(webBundle)
ensureFile(tuiBundle)
