#!/usr/bin/env node

import fs, { existsSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawn } from 'node:child_process'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const repoRoot = path.resolve(__dirname, '..')
const lifecycleEvent = String(process.env.npm_lifecycle_event || '').trim()
const runningFromPrepack = lifecycleEvent === 'prepack'
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
const parallelBundleBuilds = ['1', 'true', 'yes', 'on'].includes(
  String(process.env.DEEPSCIENTIST_PARALLEL_BUNDLE_BUILDS || '')
    .trim()
    .toLowerCase()
)

function run(command, args, cwd = repoRoot) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd,
      stdio: 'inherit',
      env: process.env,
    })
    child.on('error', reject)
    child.on('close', (code) => {
      if (code === 0) {
        resolve()
        return
      }
      const error = new Error(`${command} ${args.join(' ')} exited with code ${code ?? 1}`)
      error.exitCode = code ?? 1
      reject(error)
    })
  })
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

function latestMtimeForPaths(relativePaths) {
  let latest = 0
  const stack = relativePaths
    .map((relativePath) => path.join(repoRoot, relativePath))
    .filter((fullPath) => existsSync(fullPath))

  while (stack.length > 0) {
    const current = stack.pop()
    if (!current) continue
    const stats = fs.statSync(current)
    latest = Math.max(latest, stats.mtimeMs)
    if (!stats.isDirectory()) continue
    for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
      if (entry.name === 'node_modules' || entry.name === 'dist') continue
      stack.push(path.join(current, entry.name))
    }
  }

  return latest
}

function latestMtimeForTree(relativePath) {
  const fullPath = path.join(repoRoot, relativePath)
  if (!existsSync(fullPath)) return 0
  let latest = 0
  const stack = [fullPath]
  while (stack.length > 0) {
    const current = stack.pop()
    if (!current) continue
    const stats = fs.statSync(current)
    latest = Math.max(latest, stats.mtimeMs)
    if (!stats.isDirectory()) continue
    for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
      stack.push(path.join(current, entry.name))
    }
  }
  return latest
}

function bundleFreshness() {
  const webSourceMtime = latestMtimeForPaths([
    'src/ui/src',
    'src/ui/public',
    'src/ui/package.json',
    'src/ui/package-lock.json',
    'src/ui/postcss.config.cjs',
    'src/ui/tailwind.config.ts',
    'src/ui/tsconfig.json',
    'src/ui/vite.config.ts',
    'src/ui/index.html',
  ])
  const tuiSourceMtime = latestMtimeForPaths([
    'src/tui/src',
    'src/tui/package.json',
    'src/tui/package-lock.json',
    'src/tui/tsconfig.json',
  ])
  const webDistMtime = latestMtimeForTree('src/ui/dist')
  const tuiDistMtime = latestMtimeForTree('src/tui/dist')
  return {
    webFresh: webDistMtime >= webSourceMtime && webDistMtime > 0,
    tuiFresh: tuiDistMtime >= tuiSourceMtime && tuiDistMtime > 0,
  }
}

function installMarkerMtime(relativePath) {
  const packageRoot = path.join(repoRoot, relativePath)
  const markerCandidates = [
    path.join(packageRoot, 'node_modules', '.package-lock.json'),
    path.join(packageRoot, 'node_modules'),
  ]
  for (const candidate of markerCandidates) {
    if (existsSync(candidate)) {
      return fs.statSync(candidate).mtimeMs
    }
  }
  return 0
}

function dependenciesNeedInstall(relativePath) {
  const manifestMtime = latestMtimeForPaths([
    path.join(relativePath, 'package.json'),
    path.join(relativePath, 'package-lock.json'),
  ])
  const installedMtime = installMarkerMtime(relativePath)
  return installedMtime === 0 || installedMtime < manifestMtime
}

async function main() {
  const freshness = bundleFreshness()
  const bundlesFresh = freshness.webFresh && freshness.tuiFresh

  if (runningFromPrepack && !forceRebuild) {
    ensureFile(webBundle)
    ensureFile(tuiBundle)
    if (!bundlesFresh) {
      console.error('Prebuilt UI/TUI bundles are stale for npm pack/publish.')
      console.error('Run `npm run build:release` first, then rerun `npm pack` or `npm publish`.')
      process.exit(1)
    }
    return
  }

  if (bundlesFresh && !forceRebuild) {
    console.log('UI/TUI bundles are already fresh; skipping rebuild.')
    ensureFile(webBundle)
    ensureFile(tuiBundle)
    return
  }

  if (!skipRebuild || forceRebuild) {
    const installTasks = []
    if (dependenciesNeedInstall('src/ui')) {
      installTasks.push(
        run('npm', ['--prefix', 'src/ui', 'ci', '--include=dev', '--no-audit', '--no-fund', '--prefer-offline'])
      )
    } else {
      console.log('Skipping npm ci for src/ui; dependencies look fresh.')
    }
    if (dependenciesNeedInstall('src/tui')) {
      installTasks.push(
        run('npm', ['--prefix', 'src/tui', 'ci', '--include=dev', '--no-audit', '--no-fund', '--prefer-offline'])
      )
    } else {
      console.log('Skipping npm ci for src/tui; dependencies look fresh.')
    }
    if (installTasks.length > 0) {
      await Promise.all(installTasks)
    }
    const buildSteps = [
      () => run('npm', ['--prefix', 'src/ui', 'run', 'build']),
      () => run('npm', ['--prefix', 'src/tui', 'run', 'build']),
    ]
    if (parallelBundleBuilds) {
      await Promise.all(buildSteps.map((step) => step()))
    } else {
      for (const step of buildSteps) {
        await step()
      }
    }
  }

  ensureFile(webBundle)
  ensureFile(tuiBundle)
}

try {
  await main()
} catch (error) {
  if (error && typeof error === 'object' && 'exitCode' in error && typeof error.exitCode === 'number') {
    process.exit(error.exitCode)
  }
  throw error
}
