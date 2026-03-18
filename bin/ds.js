#!/usr/bin/env node
const crypto = require('node:crypto');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const readline = require('node:readline');
const { pathToFileURL } = require('node:url');
const { spawn, spawnSync } = require('node:child_process');

const repoRoot = path.resolve(__dirname, '..');
const packageJson = JSON.parse(fs.readFileSync(path.join(repoRoot, 'package.json'), 'utf8'));
const pyprojectToml = fs.readFileSync(path.join(repoRoot, 'pyproject.toml'), 'utf8');
const pythonCandidates = process.platform === 'win32' ? ['python', 'py'] : ['python3', 'python'];
const requiredPythonSpec = parseRequiredPythonSpec(pyprojectToml);
const minimumPythonVersion = parseMinimumPythonVersion(requiredPythonSpec);
const launcherWrapperCommands = ['ds', 'ds-cli', 'research', 'resear'];
const pythonCommands = new Set([
  'init',
  'new',
  'status',
  'pause',
  'resume',
  'daemon',
  'run',
  'note',
  'approve',
  'graph',
  'doctor',
  'docker',
  'push',
  'memory',
  'baseline',
  'latex',
  'config',
]);
const UPDATE_PACKAGE_NAME = String(packageJson.name || '@researai/deepscientist').trim() || '@researai/deepscientist';
const UPDATE_CHECK_TTL_MS = 12 * 60 * 60 * 1000;
const UPDATE_PROMPT_TTL_MS = 12 * 60 * 60 * 1000;

const optionsWithValues = new Set(['--home', '--host', '--port', '--quest-id', '--mode']);

function printLauncherHelp() {
  console.log(`DeepScientist launcher

Usage:
  ds
  ds update
  ds update --check
  ds update --yes
  ds migrate /data/DeepScientist
  ds --hero
  ds --hero doctor
  ds --tui
  ds --both
  ds --host 0.0.0.0 --port 21000
  ds --stop
  ds --restart
  ds --status
  ds doctor
  ds latex status
  ds --home ~/DeepScientist --port 20999

Launcher flags:
  --host <host>         Bind host for the local web daemon
  --port <port>         Bind port for the local web daemon
  --tui                 Start the terminal workspace only
  --both                Start web + terminal workspace together
  --no-browser          Do not auto-open the browser
  --daemon-only         Start the managed daemon and exit
  --status              Print managed daemon health as JSON
  --stop                Stop the managed daemon
  --restart             Restart the managed daemon
  --home <path>         Use a custom DeepScientist home
  --hero                Use the current working directory as DeepScientist home
  --quest-id <id>       Open the TUI on one quest directly

Update:
  ds update             Check the npm package version and offer update actions
  ds update --check     Print structured update status
  ds update --yes       Install the latest npm release immediately

Migration:
  ds migrate <target>   Move the DeepScientist home/install root to a new absolute path
  ds migrate <target> --yes --restart

Runtime:
  DeepScientist uses uv to manage a locked local Python runtime.
  If uv is missing, ds bootstraps a local copy under the DeepScientist home automatically.
  If an active conda environment provides Python ${requiredPythonSpec}, ds prefers it.
  Otherwise uv provisions a managed Python under the DeepScientist home automatically.

Advanced Python CLI:
  ds init
  ds new "reproduce baseline and test one stronger idea"
  ds doctor
  ds latex install-runtime
  ds run decision --quest-id 001 --message "review current state"
`);
}

function ensureDir(targetPath) {
  fs.mkdirSync(targetPath, { recursive: true });
}

function expandUserPath(rawPath) {
  const normalized = String(rawPath || '').trim();
  if (!normalized) {
    return normalized;
  }
  if (normalized === '~') {
    return os.homedir();
  }
  if (normalized.startsWith(`~${path.sep}`) || normalized.startsWith('~/')) {
    return path.join(os.homedir(), normalized.slice(2));
  }
  return normalized;
}

function updateStatePath(home) {
  return path.join(home, 'runtime', 'update-state.json');
}

function readUpdateState(home) {
  return readJsonFile(updateStatePath(home)) || {};
}

function writeUpdateState(home, payload) {
  const statePath = updateStatePath(home);
  ensureDir(path.dirname(statePath));
  fs.writeFileSync(statePath, `${JSON.stringify(payload, null, 2)}\n`, 'utf8');
}

function mergeUpdateState(home, patch) {
  const current = readUpdateState(home);
  const next = {
    ...current,
    ...patch,
  };
  writeUpdateState(home, next);
  return next;
}

function parseTimestamp(value) {
  if (!value) {
    return null;
  }
  const parsed = Date.parse(String(value));
  return Number.isFinite(parsed) ? parsed : null;
}

function isExpired(value, ttlMs) {
  const parsed = parseTimestamp(value);
  if (parsed === null) {
    return true;
  }
  return Date.now() - parsed > ttlMs;
}

function normalizeVersion(value) {
  return String(value || '')
    .trim()
    .replace(/^v/i, '');
}

function compareVersions(left, right) {
  const leftParts = normalizeVersion(left).split('.').map((item) => Number.parseInt(item, 10) || 0);
  const rightParts = normalizeVersion(right).split('.').map((item) => Number.parseInt(item, 10) || 0);
  const length = Math.max(leftParts.length, rightParts.length, 3);
  for (let index = 0; index < length; index += 1) {
    const leftValue = leftParts[index] || 0;
    const rightValue = rightParts[index] || 0;
    if (leftValue > rightValue) {
      return 1;
    }
    if (leftValue < rightValue) {
      return -1;
    }
  }
  return 0;
}

function detectInstallMode(rootPath = repoRoot) {
  const normalized = String(rootPath || '');
  return normalized.includes(`${path.sep}node_modules${path.sep}`) ? 'npm-package' : 'source-checkout';
}

function updateManualCommand(installMode) {
  if (installMode === 'npm-package') {
    return `npm install -g ${UPDATE_PACKAGE_NAME}@latest`;
  }
  return 'git pull && bash install.sh';
}

function updateSupportSummary(installMode, npmBinary, launcherPath) {
  if (!npmBinary) {
    return {
      canCheck: false,
      canSelfUpdate: false,
      reason: '`npm` is not available on PATH.',
    };
  }
  if (installMode !== 'npm-package') {
    return {
      canCheck: true,
      canSelfUpdate: false,
      reason: 'This DeepScientist installation comes from a source checkout and should be updated from Git.',
    };
  }
  if (!launcherPath || !fs.existsSync(launcherPath)) {
    return {
      canCheck: true,
      canSelfUpdate: false,
      reason: 'The launcher entrypoint could not be resolved.',
    };
  }
  return {
    canCheck: true,
    canSelfUpdate: true,
    reason: null,
  };
}

function resolveNpmBinary() {
  return resolveExecutableOnPath(process.platform === 'win32' ? 'npm.cmd' : 'npm') || resolveExecutableOnPath('npm');
}

function resolveLauncherPath() {
  const configured = String(process.env.DEEPSCIENTIST_LAUNCHER_PATH || '').trim();
  if (configured && fs.existsSync(configured)) {
    return configured;
  }
  const candidate = path.join(repoRoot, 'bin', 'ds.js');
  return fs.existsSync(candidate) ? candidate : null;
}

function fetchLatestPublishedVersion({ npmBinary, timeoutMs = 3500 }) {
  if (!npmBinary) {
    return {
      ok: false,
      error: '`npm` is not available on PATH.',
      latestVersion: null,
    };
  }
  const result = spawnSync(npmBinary, ['view', UPDATE_PACKAGE_NAME, 'version', '--json'], {
    encoding: 'utf8',
    env: process.env,
    timeout: timeoutMs,
  });
  if (result.error) {
    return {
      ok: false,
      error: result.error.message,
      latestVersion: null,
    };
  }
  if (result.status !== 0) {
    return {
      ok: false,
      error: (result.stderr || result.stdout || '').trim() || `npm exited with status ${result.status}`,
      latestVersion: null,
    };
  }
  try {
    const parsed = JSON.parse(String(result.stdout || 'null'));
    const latestVersion = Array.isArray(parsed) ? normalizeVersion(parsed[parsed.length - 1]) : normalizeVersion(parsed);
    if (!latestVersion) {
      throw new Error('npm returned an empty version string.');
    }
    return {
      ok: true,
      error: null,
      latestVersion,
    };
  } catch (error) {
    return {
      ok: false,
      error: error instanceof Error ? error.message : 'Could not parse npm version output.',
      latestVersion: null,
    };
  }
}

function buildUpdateStatus(home, statePatch = {}) {
  const state = { ...readUpdateState(home), ...statePatch };
  const installMode = detectInstallMode(repoRoot);
  const npmBinary = resolveNpmBinary();
  const launcherPath = resolveLauncherPath();
  const support = updateSupportSummary(installMode, npmBinary, launcherPath);
  const currentVersion = normalizeVersion(state.current_version || packageJson.version);
  const latestVersion = normalizeVersion(state.latest_version || '');
  const updateAvailable = Boolean(latestVersion) && compareVersions(latestVersion, currentVersion) > 0;
  const skippedVersion = normalizeVersion(state.last_skipped_version || '');
  const skippedCurrentTarget = Boolean(updateAvailable && skippedVersion && skippedVersion === latestVersion);
  const promptRecommended =
    Boolean(updateAvailable)
    && !Boolean(state.busy)
    && !skippedCurrentTarget
    && isExpired(state.last_prompted_at || state.last_deferred_at, UPDATE_PROMPT_TTL_MS);

  return {
    ok: true,
    package_name: UPDATE_PACKAGE_NAME,
    install_mode: installMode,
    can_check: support.canCheck,
    can_self_update: support.canSelfUpdate,
    current_version: currentVersion,
    latest_version: latestVersion || null,
    update_available: updateAvailable,
    prompt_recommended: promptRecommended,
    busy: Boolean(state.busy),
    last_checked_at: state.last_checked_at || null,
    last_check_error: state.last_check_error || null,
    last_prompted_at: state.last_prompted_at || null,
    last_deferred_at: state.last_deferred_at || null,
    last_skipped_version: skippedVersion || null,
    last_update_started_at: state.last_update_started_at || null,
    last_update_finished_at: state.last_update_finished_at || null,
    last_update_result: state.last_update_result || null,
    target_version: normalizeVersion(state.target_version || '') || null,
    manual_update_command: updateManualCommand(installMode),
    reason: support.reason,
  };
}

function checkForUpdates(home, { force = false, timeoutMs = 3500 } = {}) {
  const currentVersion = normalizeVersion(packageJson.version);
  const existing = readUpdateState(home);
  const installMode = detectInstallMode(repoRoot);
  const npmBinary = resolveNpmBinary();
  const launcherPath = resolveLauncherPath();
  const support = updateSupportSummary(installMode, npmBinary, launcherPath);

  if (!force && existing.current_version === currentVersion && !isExpired(existing.last_checked_at, UPDATE_CHECK_TTL_MS)) {
    return buildUpdateStatus(home);
  }

  if (!support.canCheck) {
    const patched = mergeUpdateState(home, {
      current_version: currentVersion,
      last_checked_at: new Date().toISOString(),
      last_check_error: support.reason,
    });
    return buildUpdateStatus(home, patched);
  }

  const probe = fetchLatestPublishedVersion({ npmBinary, timeoutMs });
  const patched = mergeUpdateState(home, {
    current_version: currentVersion,
    latest_version: probe.latestVersion || existing.latest_version || null,
    last_checked_at: new Date().toISOString(),
    last_check_error: probe.ok ? null : probe.error,
  });
  return buildUpdateStatus(home, patched);
}

function markUpdateDeferred(home, version) {
  const patched = mergeUpdateState(home, {
    last_prompted_at: new Date().toISOString(),
    last_deferred_at: new Date().toISOString(),
    latest_version: normalizeVersion(version || readUpdateState(home).latest_version || '') || null,
  });
  return buildUpdateStatus(home, patched);
}

function markUpdateSkipped(home, version) {
  const normalized = normalizeVersion(version);
  const patched = mergeUpdateState(home, {
    last_prompted_at: new Date().toISOString(),
    last_skipped_version: normalized || null,
  });
  return buildUpdateStatus(home, patched);
}

function parseRequiredPythonSpec(pyprojectText) {
  const match = String(pyprojectText || '').match(/^\s*requires-python\s*=\s*["']([^"']+)["']/m);
  return match ? match[1].trim() : '>=3.11';
}

function parseMinimumPythonVersion(spec) {
  const match = String(spec || '').match(/>=\s*(\d+)\.(\d+)(?:\.(\d+))?/);
  if (!match) {
    return { major: 3, minor: 11, patch: 0 };
  }
  return {
    major: Number(match[1]),
    minor: Number(match[2]),
    patch: Number(match[3] || 0),
  };
}

function resolveHome(args) {
  const index = args.indexOf('--home');
  if (index >= 0 && index + 1 < args.length) {
    return path.resolve(args[index + 1]);
  }
  if (args.includes('--hero') || args.includes('--here')) {
    return process.cwd();
  }
  if (process.env.DEEPSCIENTIST_HOME) {
    return path.resolve(process.env.DEEPSCIENTIST_HOME);
  }
  if (process.env.DS_HOME) {
    return path.resolve(process.env.DS_HOME);
  }
  return path.join(os.homedir(), 'DeepScientist');
}

function formatHttpHost(host) {
  const normalized = String(host || '').trim();
  if (!normalized) {
    return '127.0.0.1';
  }
  if (normalized.startsWith('[') && normalized.endsWith(']')) {
    return normalized;
  }
  return normalized.includes(':') ? `[${normalized}]` : normalized;
}

function browserUiUrl(host, port) {
  const normalized = String(host || '').trim();
  const browserHost =
    !normalized || normalized === '0.0.0.0' || normalized === '::' || normalized === '[::]'
      ? '127.0.0.1'
      : normalized;
  return `http://${formatHttpHost(browserHost)}:${port}`;
}

function bindUiUrl(host, port) {
  const normalized = String(host || '').trim() || '0.0.0.0';
  return `http://${formatHttpHost(normalized)}:${port}`;
}

function normalizeMode(value) {
  const normalized = String(value || '')
    .trim()
    .toLowerCase();
  if (normalized === 'tui' || normalized === 'both' || normalized === 'web') {
    return normalized;
  }
  return 'web';
}

function parseBooleanSetting(rawValue, fallback = false) {
  if (typeof rawValue === 'boolean') {
    return rawValue;
  }
  const normalized = String(rawValue || '')
    .trim()
    .toLowerCase();
  if (['true', 'yes', 'on', '1'].includes(normalized)) {
    return true;
  }
  if (['false', 'no', 'off', '0'].includes(normalized)) {
    return false;
  }
  return fallback;
}

function supportsAnsi() {
  return Boolean(process.stdout.isTTY && process.env.TERM !== 'dumb');
}

function stripAnsi(text) {
  return String(text || '')
    .replace(/\u001B]8;;[^\u0007]*\u0007/g, '')
    .replace(/\u001B]8;;\u0007/g, '')
    .replace(/\u001B\[[0-9;]*m/g, '');
}

function visibleWidth(text) {
  return stripAnsi(text).length;
}

function centerText(text, width) {
  const targetWidth = Math.max(visibleWidth(text), width || 0);
  const padding = Math.max(0, Math.floor((targetWidth - visibleWidth(text)) / 2));
  return `${' '.repeat(padding)}${text}`;
}

function hyperlink(url, label = url) {
  if (!supportsAnsi()) {
    return label;
  }
  return `\u001B]8;;${url}\u0007${label}\u001B]8;;\u0007`;
}

function colorize(code, text) {
  if (!supportsAnsi()) {
    return text;
  }
  return `${code}${text}\u001B[0m`;
}

function renderBrandArtwork() {
  const brandPath = path.join(repoRoot, 'assets', 'branding', 'deepscientist-mark.png');
  const chafa = resolveExecutableOnPath('chafa');
  if (!supportsAnsi() || !chafa || !fs.existsSync(brandPath)) {
    return [];
  }
  const width = Math.max(18, Math.min(30, Math.floor((process.stdout.columns || 100) / 3)));
  const height = Math.max(8, Math.floor(width / 2));
  try {
    const result = spawnSync(
      chafa,
      ['--size', `${width}x${height}`, '--format', 'symbols', '--colors', '16', brandPath],
      { encoding: 'utf8' }
    );
    if (result.status === 0 && result.stdout && result.stdout.trim()) {
      return result.stdout.replace(/\s+$/, '').split(/\r?\n/);
    }
  } catch {}
  return [];
}

function truncateMiddle(text, maxLength = 120) {
  const value = String(text || '');
  if (value.length <= maxLength) {
    return value;
  }
  const head = Math.max(24, Math.floor((maxLength - 1) / 2));
  const tail = Math.max(16, maxLength - head - 1);
  return `${value.slice(0, head)}…${value.slice(-tail)}`;
}

function renderKeyValueRows(rows) {
  const labelWidth = Math.max(...rows.map(([label]) => String(label).length), 8);
  for (const [label, value] of rows) {
    console.log(`  ${String(label).padEnd(labelWidth)}  ${value}`);
  }
}

function pythonMajorMinor(probe) {
  if (!probe || typeof probe.major !== 'number' || typeof probe.minor !== 'number') {
    return '';
  }
  return `${probe.major}.${probe.minor}`;
}

function pythonVersionText(probe) {
  if (!probe) {
    return 'unknown';
  }
  const version = probe.version || pythonMajorMinor(probe) || 'unknown';
  if (probe.executable) {
    return `${version}  (${probe.executable})`;
  }
  return version;
}

function renderLaunchHints({ home, url, bindUrl, pythonSelection }) {
  const runtimeRows = [
    ['Version', packageJson.version],
    ['Home', truncateMiddle(home)],
    ['Browser URL', url],
    ['Bind URL', bindUrl],
    ['Python', truncateMiddle(pythonVersionText(pythonSelection))],
  ];
  if (pythonSelection && pythonSelection.sourceLabel) {
    runtimeRows.push(['Python source', pythonSelection.sourceLabel]);
  }
  console.log(colorize('\u001B[1;38;5;39m', 'Runtime'));
  renderKeyValueRows(runtimeRows);
  console.log('');

  console.log(colorize('\u001B[1;38;5;39m', 'Quick Flags'));
  renderKeyValueRows([
    ['ds --port 21000', 'Change the web port'],
    ['ds --host 0.0.0.0 --port 21000', 'Bind on all interfaces'],
    ['ds --hero', 'Use the current directory as home'],
    ['ds --both', 'Start web + TUI together'],
    ['ds --tui', 'Start the terminal workspace only'],
    ['ds --no-browser', 'Do not auto-open the browser'],
    ['ds --status', 'Show daemon health as JSON'],
    ['ds --restart', 'Restart the managed daemon'],
    ['ds --stop', 'Stop the managed daemon'],
    ['ds migrate /data/DeepScientist', 'Move the full home/install root safely'],
    ['ds --help', 'Show the full launcher help'],
  ]);
  console.log('');
}

function printLaunchCard({
  url,
  bindUrl,
  mode,
  autoOpenRequested,
  browserOpened,
  daemonOnly,
  home,
  pythonSelection,
}) {
  const width = Math.max(72, Math.min(process.stdout.columns || 100, 108));
  const divider = colorize('\u001B[38;5;245m', '─'.repeat(Math.max(36, width - 6)));
  const title = colorize('\u001B[1;38;5;39m', 'ResearAI');
  const subtitle = colorize('\u001B[38;5;110m', 'Local-first research operating system');
  const versionLine = colorize('\u001B[38;5;245m', `Version ${packageJson.version}`);
  const urlLabel = colorize('\u001B[1;38;5;45m', hyperlink(url, url));
  const workspaceMode =
    mode === 'both'
      ? 'Web workspace + terminal workspace'
      : mode === 'tui'
        ? 'Terminal workspace'
        : 'Web workspace';
  const browserLine = autoOpenRequested
    ? browserOpened
      ? 'Browser launch requested successfully.'
      : 'Browser auto-open was requested but is not available in this terminal session.'
    : 'Browser auto-open is disabled. Open the URL manually if needed.';
  const nextStep = daemonOnly
    ? 'Use ds --tui to enter the terminal workspace.'
    : mode === 'web'
      ? 'Use ds --tui to enter the terminal workspace.'
      : mode === 'both'
        ? 'The terminal workspace starts below.'
        : 'Use Ctrl+O inside TUI to reopen the web workspace.';

  console.log('');
  const artwork = renderBrandArtwork();
  for (const line of artwork) {
    console.log(centerText(line, width));
  }
  if (artwork.length === 0) {
    console.log(centerText(colorize('\u001B[1;38;5;39m', '⛰'), width));
  }
  const wordmark = [
    '  ____                  ____       _            _   _     _   ',
    ' |  _ \\  ___  ___ _ __ / ___|  ___(_) ___ _ __ | |_(_)___| |_ ',
    " | | | |/ _ \\/ _ \\ '_ \\\\___ \\ / __| |/ _ \\ '_ \\| __| / __| __|",
    ' | |_| |  __/  __/ |_) |___) | (__| |  __/ | | | |_| \\__ \\ |_ ',
    ' |____/ \\___|\\___| .__/|____/ \\___|_|\\___|_| |_|\\__|_|___/\\__|',
    '                 |_|                                          ',
  ];
  console.log(centerText(title, width));
  console.log(centerText(versionLine, width));
  for (const line of wordmark) {
    console.log(centerText(colorize('\u001B[1;38;5;39m', line), width));
  }
  console.log(centerText(subtitle, width));
  console.log('');
  console.log(centerText(divider, width));
  console.log(centerText(colorize('\u001B[1m', workspaceMode), width));
  console.log(centerText(urlLabel, width));
  console.log(centerText(divider, width));
  console.log(centerText(browserLine, width));
  console.log(centerText(nextStep, width));
  console.log(centerText('Run ds --stop to stop the managed daemon.', width));
  console.log(centerText('Need to move this installation later? Use ds migrate /new/path.', width));
  console.log('');
  renderLaunchHints({ home, url, bindUrl, pythonSelection });
}

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function writeCodexPreflightReport(home, probe) {
  const reportDir = path.join(home, 'runtime', 'preflight');
  ensureDir(reportDir);
  const reportPath = path.join(reportDir, 'codex-preflight.html');
  const warnings = Array.isArray(probe?.warnings) ? probe.warnings : [];
  const errors = Array.isArray(probe?.errors) ? probe.errors : [];
  const guidance = Array.isArray(probe?.guidance) ? probe.guidance : [];
  const details = probe && typeof probe.details === 'object' ? probe.details : {};
  const renderItems = (items, tone) =>
    items
      .map(
        (item) =>
          `<li class="item item--${tone}">${escapeHtml(item)}</li>`
      )
      .join('');
  const html = `<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>DeepScientist Codex check failed</title>
    <style>
      :root { color-scheme: light dark; font-family: Inter, system-ui, sans-serif; }
      body {
        margin: 0;
        min-height: 100vh;
        background:
          radial-gradient(120% 80% at 10% 0%, rgba(210, 198, 180, 0.28), transparent 58%),
          radial-gradient(80% 70% at 90% 10%, rgba(171, 186, 199, 0.24), transparent 55%),
          linear-gradient(180deg, rgba(250,247,241,0.98), rgba(244,239,233,0.98));
        color: #1f2937;
      }
      .page { max-width: 960px; margin: 0 auto; padding: 40px 20px 64px; }
      .panel {
        border: 1px solid rgba(15, 23, 42, 0.08);
        border-radius: 28px;
        background: rgba(255, 255, 255, 0.8);
        box-shadow: 0 24px 80px -52px rgba(18, 24, 32, 0.35);
        backdrop-filter: blur(18px);
        padding: 28px;
      }
      h1 { margin: 0 0 12px; font-size: 28px; }
      h2 { margin: 28px 0 10px; font-size: 16px; }
      p, li { line-height: 1.7; }
      .meta { color: #5b6472; font-size: 14px; }
      .item { margin: 8px 0; padding-left: 12px; border-left: 2px solid transparent; }
      .item--error { border-left-color: rgba(225, 72, 72, 0.55); color: #9f1d1d; }
      .item--warn { border-left-color: rgba(217, 149, 42, 0.55); color: #8a5a00; }
      pre {
        margin: 0;
        padding: 14px 16px;
        overflow: auto;
        border-radius: 18px;
        background: rgba(15, 23, 42, 0.05);
        white-space: pre-wrap;
        word-break: break-word;
      }
      .grid { display: grid; gap: 16px; }
      @media (min-width: 860px) { .grid { grid-template-columns: 1fr 1fr; } }
      .kv { margin: 0; }
      .kv dt { font-size: 12px; color: #667085; text-transform: uppercase; letter-spacing: .08em; }
      .kv dd { margin: 6px 0 0; font-size: 14px; word-break: break-all; }
    </style>
  </head>
  <body>
    <main class="page">
      <section class="panel">
        <h1>DeepScientist could not start Codex</h1>
        <p class="meta">DeepScientist blocked startup because the Codex hello probe did not pass. Please run <code>codex</code>, complete login, then launch <code>ds</code> again.</p>
        <p class="meta">DeepScientist 启动前进行了 Codex 可用性检查，但 hello 探测没有通过。请先手动运行 <code>codex</code> 并完成登录，再重新启动 <code>ds</code>。</p>

        <h2>Summary</h2>
        <p>${escapeHtml(probe?.summary || 'Codex startup probe failed.')}</p>

        ${errors.length ? `<h2>Errors</h2><ul>${renderItems(errors, 'error')}</ul>` : ''}
        ${warnings.length ? `<h2>Warnings</h2><ul>${renderItems(warnings, 'warn')}</ul>` : ''}
        ${guidance.length ? `<h2>What to do next</h2><ul>${guidance.map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ul>` : ''}

        <h2>Probe details</h2>
        <div class="grid">
          <dl class="kv">
            <dt>Binary</dt>
            <dd>${escapeHtml(details.binary || '')}</dd>
          </dl>
          <dl class="kv">
            <dt>Resolved binary</dt>
            <dd>${escapeHtml(details.resolved_binary || '')}</dd>
          </dl>
          <dl class="kv">
            <dt>Model</dt>
            <dd>${escapeHtml(details.model || '')}</dd>
          </dl>
          <dl class="kv">
            <dt>Exit code</dt>
            <dd>${escapeHtml(details.exit_code ?? '')}</dd>
          </dl>
        </div>

        ${details.stdout_excerpt ? `<h2>Stdout</h2><pre>${escapeHtml(details.stdout_excerpt)}</pre>` : ''}
        ${details.stderr_excerpt ? `<h2>Stderr</h2><pre>${escapeHtml(details.stderr_excerpt)}</pre>` : ''}
      </section>
    </main>
  </body>
</html>`;
  fs.writeFileSync(reportPath, html, 'utf8');
  return {
    path: reportPath,
    url: pathToFileURL(reportPath).toString(),
  };
}

function readCodexBootstrapState(home, runtimePython) {
  const snippet = [
    'import json, pathlib, sys',
    'from deepscientist.config import ConfigManager',
    'home = pathlib.Path(sys.argv[1])',
    'manager = ConfigManager(home)',
    'print(json.dumps(manager.codex_bootstrap_state(), ensure_ascii=False))',
  ].join('\n');
  const result = runSync(runtimePython, ['-c', snippet, home], { capture: true, allowFailure: true });
  if (result.status !== 0) {
    return { codex_ready: false, codex_last_checked_at: null, codex_last_result: {} };
  }
  try {
    return JSON.parse(result.stdout || '{}');
  } catch {
    return { codex_ready: false, codex_last_checked_at: null, codex_last_result: {} };
  }
}

function probeCodexBootstrap(home, runtimePython) {
  const snippet = [
    'import json, pathlib, sys',
    'from deepscientist.config import ConfigManager',
    'home = pathlib.Path(sys.argv[1])',
    'manager = ConfigManager(home)',
    'print(json.dumps(manager.probe_codex_bootstrap(persist=True), ensure_ascii=False))',
  ].join('\n');
  const result = runSync(runtimePython, ['-c', snippet, home], { capture: true, allowFailure: true });
  let payload = null;
  try {
    payload = JSON.parse(result.stdout || '{}');
  } catch {
    payload = null;
  }
  if (payload && typeof payload === 'object') {
    return payload;
  }
  return {
    ok: false,
    summary: 'Codex startup probe crashed before a structured result was returned.',
    warnings: [],
    errors: [result.stderr || 'Unable to parse the startup probe result.'],
    details: {
      exit_code: result.status ?? null,
      stdout_excerpt: result.stdout || '',
      stderr_excerpt: result.stderr || '',
    },
    guidance: [
      'Run `codex` manually and complete login.',
      'Then start DeepScientist again.',
    ],
  };
}

function createCodexPreflightError(home, probe) {
  const report = writeCodexPreflightReport(home, probe);
  const error = new Error(probe?.summary || 'Codex startup probe failed.');
  error.code = 'DS_CODEX_PREFLIGHT';
  error.reportPath = report.path;
  error.reportUrl = report.url;
  error.probe = probe;
  return error;
}

function parseLauncherArgs(argv) {
  const args = [...argv];
  let mode = null;
  let host = null;
  let port = null;
  let home = null;
  let stop = false;
  let restart = false;
  let openBrowser = null;
  let questId = null;
  let status = false;
  let daemonOnly = false;
  let skipUpdateCheck = false;

  if (args[0] === 'ui') {
    args.shift();
  }

  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    if (arg === 'ui') continue;
    if (arg === '--web') mode = 'web';
    else if (arg === '--tui') mode = 'tui';
    else if (arg === '--both') mode = 'both';
    else if (arg === '--stop') stop = true;
    else if (arg === '--restart') restart = true;
    else if (arg === '--status') status = true;
    else if (arg === '--no-browser') openBrowser = false;
    else if (arg === '--open-browser') openBrowser = true;
    else if (arg === '--daemon-only') daemonOnly = true;
    else if (arg === '--skip-update-check') skipUpdateCheck = true;
    else if (arg === '--host' && args[index + 1]) host = args[++index];
    else if (arg === '--port' && args[index + 1]) port = Number(args[++index]);
    else if (arg === '--home' && args[index + 1]) home = path.resolve(args[++index]);
    else if (arg === '--quest-id' && args[index + 1]) questId = args[++index];
    else if (arg === '--mode' && args[index + 1]) mode = normalizeMode(args[++index]);
    else if (arg === '--help' || arg === '-h') return { help: true };
    else if (!arg.startsWith('--')) return null;
  }

  return {
    help: false,
    mode,
    host,
    port,
    home,
    stop,
    restart,
    status,
    openBrowser,
    questId,
    daemonOnly,
    skipUpdateCheck,
  };
}

function printUpdateHelp() {
  console.log(`DeepScientist update

Usage:
  ds update
  ds update --check
  ds update --yes
  ds update --remind-later
  ds update --skip-version

Flags:
  --check            Return the current update status without installing
  --yes              Install the latest published npm package immediately
  --json             Print structured JSON output
  --force-check      Ignore the cached version probe
  --remind-later     Defer prompts for the current published version
  --skip-version     Skip reminders for the current published version
`);
}

function printMigrateHelp() {
  console.log(`DeepScientist migrate

Usage:
  ds migrate /absolute/target/path
  ds migrate /absolute/target/path --yes
  ds migrate /absolute/target/path --restart
  ds migrate /absolute/target/path --home /current/source/path

Flags:
  --yes              Skip the interactive double-confirmation prompt
  --restart          Start the managed daemon again from the migrated home
  --home <path>      Override the current DeepScientist source home/root
`);
}

function parseUpdateArgs(argv) {
  const args = [...argv];
  if (args[0] === 'update') {
    args.shift();
  }
  let json = false;
  let check = false;
  let yes = false;
  let forceCheck = false;
  let remindLater = false;
  let skipVersion = false;
  let background = false;
  let worker = false;
  let home = null;
  let host = null;
  let port = null;
  let restartDaemon = null;
  let skipUpdateCheck = false;

  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    if (arg === '--json') json = true;
    else if (arg === '--check') check = true;
    else if (arg === '--yes') yes = true;
    else if (arg === '--force-check') forceCheck = true;
    else if (arg === '--remind-later') remindLater = true;
    else if (arg === '--skip-version') skipVersion = true;
    else if (arg === '--background') background = true;
    else if (arg === '--worker') worker = true;
    else if (arg === '--restart-daemon') restartDaemon = true;
    else if (arg === '--skip-update-check') skipUpdateCheck = true;
    else if (arg === '--home' && args[index + 1]) home = path.resolve(args[++index]);
    else if (arg === '--host' && args[index + 1]) host = args[++index];
    else if (arg === '--port' && args[index + 1]) port = Number(args[++index]);
    else if (arg === '--help' || arg === '-h') return { help: true };
    else if (!arg.startsWith('--')) return null;
  }

  return {
    help: false,
    json,
    check,
    yes,
    forceCheck,
    remindLater,
    skipVersion,
    background,
    worker,
    home,
    host,
    port,
    restartDaemon,
    skipUpdateCheck,
  };
}

function parseMigrateArgs(argv) {
  const args = [...argv];
  if (args[0] === 'migrate') {
    args.shift();
  }
  let home = null;
  let target = null;
  let yes = false;
  let restart = false;

  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    if (arg === '--yes') yes = true;
    else if (arg === '--restart') restart = true;
    else if (arg === '--home' && args[index + 1]) home = path.resolve(expandUserPath(args[++index]));
    else if (arg === '--help' || arg === '-h') return { help: true };
    else if (arg.startsWith('--')) return null;
    else if (!target) target = path.resolve(expandUserPath(arg));
    else return null;
  }

  if (!target) {
    return null;
  }

  return {
    help: false,
    home,
    target,
    yes,
    restart,
  };
}

function findFirstPositionalArg(args) {
  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    if (optionsWithValues.has(arg)) {
      index += 1;
      continue;
    }
    if (arg.startsWith('--')) {
      continue;
    }
    return { index, value: arg };
  }
  return null;
}

function realpathOrSelf(targetPath) {
  try {
    return fs.realpathSync(targetPath);
  } catch {
    return targetPath;
  }
}

function isPathEqual(left, right) {
  return realpathOrSelf(path.resolve(left)) === realpathOrSelf(path.resolve(right));
}

function isPathInside(candidatePath, parentPath) {
  const candidate = realpathOrSelf(path.resolve(candidatePath));
  const parent = realpathOrSelf(path.resolve(parentPath));
  if (candidate === parent) {
    return false;
  }
  const relative = path.relative(parent, candidate);
  return Boolean(relative && !relative.startsWith('..') && !path.isAbsolute(relative));
}

function buildInstalledWrapperScript() {
  return [
    '#!/usr/bin/env bash',
    'set -euo pipefail',
    'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"',
    'HOME_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"',
    'if [ -z "${DEEPSCIENTIST_HOME:-}" ]; then',
    '  export DEEPSCIENTIST_HOME="$HOME_DIR"',
    'fi',
    'NODE_BIN="${DEEPSCIENTIST_NODE:-node}"',
    'exec "$NODE_BIN" "$SCRIPT_DIR/ds.js" "$@"',
    '',
  ].join('\n');
}

function buildGlobalWrapperScript({ installDir, home, commandName }) {
  return [
    '#!/usr/bin/env bash',
    'set -euo pipefail',
    'if [ -z "${DEEPSCIENTIST_HOME:-}" ]; then',
    `  export DEEPSCIENTIST_HOME="${home}"`,
    'fi',
    `exec "${path.join(installDir, 'bin', commandName)}" "$@"`,
    '',
  ].join('\n');
}

function writeExecutableScript(targetPath, content) {
  ensureDir(path.dirname(targetPath));
  fs.writeFileSync(targetPath, content, { encoding: 'utf8', mode: 0o755 });
  fs.chmodSync(targetPath, 0o755);
}

function repairMigratedInstallWrappers(targetHome) {
  const installBinDir = path.join(targetHome, 'cli', 'bin');
  if (!fs.existsSync(installBinDir)) {
    return;
  }
  const content = buildInstalledWrapperScript();
  for (const commandName of launcherWrapperCommands) {
    const wrapperPath = path.join(installBinDir, commandName);
    if (!fs.existsSync(wrapperPath)) {
      continue;
    }
    writeExecutableScript(wrapperPath, content);
  }
}

function candidateWrapperPathsForCommand(commandName) {
  const directories = String(process.env.PATH || '')
    .split(path.delimiter)
    .filter(Boolean);
  const candidates = [];
  for (const directory of directories) {
    candidates.push(path.join(directory, commandName));
    if (process.platform === 'win32') {
      candidates.push(path.join(directory, `${commandName}.cmd`));
      candidates.push(path.join(directory, `${commandName}.ps1`));
    }
  }
  return candidates;
}

function rewriteLauncherWrappersIfPointingAtSource({ sourceHome, targetHome }) {
  if (process.platform === 'win32') {
    return [];
  }
  const rewritten = [];
  const sourceInstallDir = path.join(sourceHome, 'cli');
  const targetInstallDir = path.join(targetHome, 'cli');
  for (const commandName of launcherWrapperCommands) {
    for (const candidate of candidateWrapperPathsForCommand(commandName)) {
      if (!fs.existsSync(candidate) || !fs.statSync(candidate).isFile()) {
        continue;
      }
      let text = '';
      try {
        text = fs.readFileSync(candidate, 'utf8');
      } catch {
        continue;
      }
      if (!text.includes(sourceInstallDir) && !text.includes(sourceHome)) {
        continue;
      }
      writeExecutableScript(
        candidate,
        buildGlobalWrapperScript({
          installDir: targetInstallDir,
          home: targetHome,
          commandName,
        })
      );
      rewritten.push(candidate);
    }
  }
  return rewritten;
}

function scheduleDeferredSourceCleanup({ sourceHome, targetHome }) {
  const logPath = path.join(targetHome, 'logs', 'migrate-cleanup.log');
  ensureDir(path.dirname(logPath));
  const helperScript = [
    "const fs = require('node:fs');",
    "const { setTimeout: sleep } = require('node:timers/promises');",
    'const parentPid = Number(process.argv[1]);',
    'const sourceHome = process.argv[2];',
    'const logPath = process.argv[3];',
    '(async () => {',
    '  for (let attempt = 0; attempt < 300; attempt += 1) {',
    '    try {',
    '      process.kill(parentPid, 0);',
    '      await sleep(100);',
    '      continue;',
    '    } catch {',
    '      break;',
    '    }',
    '  }',
    '  try {',
    '    fs.rmSync(sourceHome, { recursive: true, force: true });',
    '  } catch (error) {',
    "    fs.appendFileSync(logPath, `[${new Date().toISOString()}] ${error instanceof Error ? error.message : String(error)}\\n`, 'utf8');",
    '    process.exit(1);',
    '  }',
    '})();',
  ].join('\n');
  const child = spawn(process.execPath, ['-e', helperScript, String(process.pid), sourceHome, logPath], {
    detached: true,
    stdio: 'ignore',
    env: process.env,
  });
  child.unref();
}

async function promptMigrationConfirmation({ sourceHome, targetHome }) {
  if (!process.stdin.isTTY || !process.stdout.isTTY) {
    throw new Error('DeepScientist migration needs a TTY for confirmation. Re-run with `--yes` to continue non-interactively.');
  }
  console.log('');
  console.log('DeepScientist home migration');
  console.log('');
  console.log(`From: ${sourceHome}`);
  console.log(`To:   ${targetHome}`);
  console.log('');
  console.log('This will stop the managed daemon, copy the full DeepScientist root, verify the copy, update launcher wrappers, and delete the old path after success.');
  const ask = (question) => new Promise((resolve) => {
    const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
    rl.question(question, (answer) => {
      rl.close();
      resolve(String(answer || '').trim());
    });
  });
  const first = await ask('Type YES to continue: ');
  if (first !== 'YES') {
    return false;
  }
  const second = await ask('Type MIGRATE to confirm old-path deletion after a successful copy: ');
  return second === 'MIGRATE';
}

function printMigrationSummary({ sourceHome, targetHome, restart }) {
  console.log('');
  console.log('DeepScientist migrate');
  console.log('');
  console.log(`Source: ${sourceHome}`);
  console.log(`Target: ${targetHome}`);
  console.log(`Restart: ${restart ? 'yes' : 'no'}`);
}

function pythonMeetsMinimum(probe) {
  if (!probe || typeof probe.major !== 'number' || typeof probe.minor !== 'number') {
    return false;
  }
  if (probe.major !== minimumPythonVersion.major) {
    return probe.major > minimumPythonVersion.major;
  }
  if (probe.minor !== minimumPythonVersion.minor) {
    return probe.minor > minimumPythonVersion.minor;
  }
  return probe.patch >= minimumPythonVersion.patch;
}

function pythonSelectionLabel(source) {
  if (source === 'conda') {
    const envName = String(process.env.CONDA_DEFAULT_ENV || '').trim();
    return envName ? `conda:${envName}` : 'conda';
  }
  if (source === 'uv-managed') {
    return 'uv-managed';
  }
  return 'path';
}

function buildCondaPythonCandidates() {
  const prefix = String(process.env.CONDA_PREFIX || '').trim();
  if (!prefix) {
    return [];
  }
  if (process.platform === 'win32') {
    return [path.join(prefix, 'python.exe'), path.join(prefix, 'Scripts', 'python.exe')];
  }
  return [path.join(prefix, 'bin', 'python'), path.join(prefix, 'bin', 'python3')];
}

function probePython(binary) {
  const snippet = [
    'import json, sys',
    'print(json.dumps({',
    '  "executable": sys.executable,',
    '  "version": ".".join(str(part) for part in sys.version_info[:3]),',
    '  "major": sys.version_info[0],',
    '  "minor": sys.version_info[1],',
    '  "patch": sys.version_info[2],',
    '}, ensure_ascii=False))',
  ].join('\n');
  const result = spawnSync(binary, ['-c', snippet], {
    encoding: 'utf8',
    env: process.env,
  });
  if (result.error) {
    return {
      ok: false,
      binary,
      error: result.error.message,
    };
  }
  if (result.status !== 0) {
    return {
      ok: false,
      binary,
      error: (result.stderr || result.stdout || '').trim() || `exit ${result.status}`,
    };
  }
  try {
    const payload = JSON.parse(result.stdout || '{}');
    const executable = String(payload.executable || '').trim();
    return {
      ok: true,
      binary,
      executable,
      realExecutable: executable ? realpathOrSelf(executable) : '',
      version: String(payload.version || '').trim(),
      major: Number(payload.major),
      minor: Number(payload.minor),
      patch: Number(payload.patch),
    };
  } catch (error) {
    return {
      ok: false,
      binary,
      error: error instanceof Error ? error.message : 'Could not parse Python version probe.',
    };
  }
}

function minimumPythonRequest() {
  return `${minimumPythonVersion.major}.${minimumPythonVersion.minor}`;
}

function decoratePythonProbe(probe, source) {
  if (!probe || !probe.ok) {
    return null;
  }
  return {
    ...probe,
    source,
    sourceLabel: pythonSelectionLabel(source),
  };
}

function collectPythonProbes(binaries, source, seenExecutables) {
  const probes = [];
  for (const candidate of binaries) {
    const resolved = decoratePythonProbe(probePython(candidate), source);
    if (!resolved) {
      continue;
    }
    const executableKey = resolved.realExecutable || resolved.executable || resolved.binary;
    if (seenExecutables.has(executableKey)) {
      continue;
    }
    seenExecutables.add(executableKey);
    probes.push(resolved);
  }
  return probes;
}

function createPythonRuntimePlan({ condaProbes = [], pathProbes = [], minimumVersionRequest = minimumPythonRequest() }) {
  const validConda = condaProbes.find((probe) => pythonMeetsMinimum(probe)) || null;
  if (validConda) {
    return {
      runtimeKind: 'system',
      selectedProbe: validConda,
      source: 'conda',
      sourceLabel: validConda.sourceLabel,
    };
  }
  const firstConda = condaProbes[0] || null;
  if (firstConda) {
    return {
      runtimeKind: 'managed',
      selectedProbe: null,
      rejectedProbe: firstConda,
      source: 'conda',
      sourceLabel: pythonSelectionLabel('uv-managed'),
      minimumVersionRequest,
    };
  }

  const validPath = pathProbes.find((probe) => pythonMeetsMinimum(probe)) || null;
  if (validPath) {
    return {
      runtimeKind: 'system',
      selectedProbe: validPath,
      source: 'path',
      sourceLabel: validPath.sourceLabel,
    };
  }
  const firstPath = pathProbes[0] || null;
  if (firstPath) {
    return {
      runtimeKind: 'managed',
      selectedProbe: null,
      rejectedProbe: firstPath,
      source: 'path',
      sourceLabel: pythonSelectionLabel('uv-managed'),
      minimumVersionRequest,
    };
  }

  return {
    runtimeKind: 'managed',
    selectedProbe: null,
    rejectedProbe: null,
    source: 'uv-managed',
    sourceLabel: pythonSelectionLabel('uv-managed'),
    minimumVersionRequest,
  };
}

function printManagedPythonFallbackNotice({ rejectedProbe, source, minimumVersionRequest, installDir }) {
  if (!rejectedProbe) {
    return;
  }
  const envName = String(process.env.CONDA_DEFAULT_ENV || '').trim();
  const sourceLabel =
    source === 'conda'
      ? (envName ? `active conda environment \`${envName}\`` : 'active conda environment')
      : 'detected system Python';
  console.warn('');
  console.warn(
    `DeepScientist found ${sourceLabel} at ${pythonVersionText(rejectedProbe)}, which does not satisfy Python ${requiredPythonSpec}.`
  );
  console.warn(
    `DeepScientist will provision a uv-managed Python ${minimumVersionRequest}+ runtime under ${installDir}.`
  );
  console.warn('');
}

function resolvePythonRuntimePlan() {
  const seenExecutables = new Set();
  const condaProbes = collectPythonProbes(buildCondaPythonCandidates(), 'conda', seenExecutables);
  const pathProbes = collectPythonProbes(pythonCandidates, 'path', seenExecutables);
  return createPythonRuntimePlan({ condaProbes, pathProbes, minimumVersionRequest: minimumPythonRequest() });
}

function runtimePythonEnvPath(home) {
  return path.join(home, 'runtime', 'python-env');
}

function runtimePythonPath(home) {
  return process.platform === 'win32'
    ? path.join(runtimePythonEnvPath(home), 'Scripts', 'python.exe')
    : path.join(runtimePythonEnvPath(home), 'bin', 'python');
}

function runtimeUvCachePath(home) {
  return path.join(home, 'runtime', 'uv-cache');
}

function runtimeUvPythonInstallPath(home) {
  return path.join(home, 'runtime', 'python');
}

function runtimeToolsPath(home) {
  return path.join(home, 'runtime', 'tools');
}

function runtimeUvRootPath(home) {
  return path.join(runtimeToolsPath(home), 'uv');
}

function runtimeUvBinDir(home) {
  return path.join(runtimeUvRootPath(home), 'bin');
}

function runtimeUvBinaryPath(home) {
  return path.join(runtimeUvBinDir(home), process.platform === 'win32' ? 'uv.exe' : 'uv');
}

function legacyVenvRootPath(home) {
  return path.join(home, 'runtime', 'venv');
}

function useEditableProjectInstall() {
  return fs.existsSync(path.join(repoRoot, '.git'));
}

function uvLockPath() {
  return path.join(repoRoot, 'uv.lock');
}

function sha256File(filePath) {
  return crypto.createHash('sha256').update(fs.readFileSync(filePath)).digest('hex');
}

function hashDirectoryTree(rootPath, predicate = null) {
  const hasher = crypto.createHash('sha256');
  if (!fs.existsSync(rootPath)) {
    hasher.update('missing');
    return hasher.digest('hex');
  }
  const stack = [rootPath];
  const files = [];
  while (stack.length > 0) {
    const current = stack.pop();
    for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
      const fullPath = path.join(current, entry.name);
      if (entry.isDirectory()) {
        stack.push(fullPath);
        continue;
      }
      if (entry.isFile()) {
        if (typeof predicate === 'function' && !predicate(fullPath)) {
          continue;
        }
        files.push(fullPath);
      }
    }
  }
  files.sort();
  for (const filePath of files) {
    hasher.update(path.relative(rootPath, filePath));
    hasher.update(fs.readFileSync(filePath));
  }
  return hasher.digest('hex');
}

function hashSkillTree() {
  return hashDirectoryTree(path.join(repoRoot, 'src', 'skills'));
}

function hashPythonSourceTree() {
  return hashDirectoryTree(path.join(repoRoot, 'src', 'deepscientist'), (filePath) => filePath.endsWith('.py'));
}

function discoverSkillIds() {
  const skillsRoot = path.join(repoRoot, 'src', 'skills');
  if (!fs.existsSync(skillsRoot)) {
    return [];
  }
  return fs
    .readdirSync(skillsRoot, { withFileTypes: true })
    .filter(
      (entry) =>
        entry.isDirectory() &&
        !entry.name.startsWith('.') &&
        fs.existsSync(path.join(skillsRoot, entry.name, 'SKILL.md'))
    )
    .map((entry) => entry.name)
    .sort();
}

function globalSkillsInstalled() {
  const skillIds = discoverSkillIds();
  const codexRoot = path.join(os.homedir(), '.codex', 'skills');
  const claudeRoot = path.join(os.homedir(), '.claude', 'agents');
  return skillIds.every((skillId) => {
    const codexSkill = path.join(codexRoot, `deepscientist-${skillId}`, 'SKILL.md');
    const claudeSkill = path.join(claudeRoot, `deepscientist-${skillId}.md`);
    return fs.existsSync(codexSkill) && fs.existsSync(claudeSkill);
  });
}

function runSync(binary, args, options = {}) {
  const result = spawnSync(binary, args, {
    cwd: options.cwd || repoRoot,
    stdio: options.capture ? 'pipe' : 'inherit',
    env: options.env || process.env,
    encoding: 'utf8',
    input: options.input,
  });
  if (result.error) {
    throw result.error;
  }
  if (!options.allowFailure && result.status !== 0) {
    if (options.capture && result.stderr) {
      process.stderr.write(result.stderr);
    }
    process.exit(result.status ?? 1);
  }
  return result;
}

function step(index, total, message) {
  console.log(`[${index}/${total}] ${message}`);
}

function verifyPythonRuntime(runtimePython) {
  const result = runSync(
    runtimePython,
    ['-c', 'import deepscientist.cli; import cryptography; import _cffi_backend; print("ok")'],
    { capture: true, allowFailure: true }
  );
  return result.status === 0;
}

function readJsonFile(filePath) {
  if (!fs.existsSync(filePath)) {
    return null;
  }
  try {
    return JSON.parse(fs.readFileSync(filePath, 'utf8'));
  } catch {
    return null;
  }
}

function executableExtensions() {
  if (process.platform !== 'win32') {
    return [''];
  }
  return (process.env.PATHEXT || '.EXE;.CMD;.BAT;.COM')
    .split(';')
    .filter(Boolean);
}

function candidateExecutablePaths(basePath) {
  if (process.platform !== 'win32') {
    return [basePath];
  }
  const extension = path.extname(basePath);
  if (extension) {
    return [basePath];
  }
  return executableExtensions().map((suffix) => `${basePath}${suffix}`);
}

function isExecutableFile(candidate) {
  try {
    if (!fs.existsSync(candidate)) {
      return false;
    }
    const stat = fs.statSync(candidate);
    if (!stat.isFile()) {
      return false;
    }
    if (process.platform !== 'win32') {
      fs.accessSync(candidate, fs.constants.X_OK);
    }
    return true;
  } catch {
    return false;
  }
}

function resolveBinaryReference(reference) {
  const normalized = String(reference || '').trim();
  if (!normalized) {
    return null;
  }
  const expanded = expandUserPath(normalized);
  if (
    path.isAbsolute(expanded)
    || normalized.startsWith('.')
    || normalized.includes(path.sep)
    || (path.sep === '\\' ? normalized.includes('/') : normalized.includes('\\'))
  ) {
    const absolute = path.isAbsolute(expanded) ? expanded : path.resolve(expanded);
    for (const candidate of candidateExecutablePaths(absolute)) {
      if (isExecutableFile(candidate)) {
        return candidate;
      }
    }
    return null;
  }
  return resolveExecutableOnPath(expanded);
}

function resolveUvBinary(home) {
  const configured = String(process.env.DEEPSCIENTIST_UV || process.env.UV_BIN || '').trim();
  if (configured) {
    return {
      path: resolveBinaryReference(configured),
      source: 'env',
      configured,
    };
  }
  const local = resolveBinaryReference(runtimeUvBinaryPath(home));
  if (local) {
    return {
      path: local,
      source: 'local',
      configured: null,
    };
  }
  const discovered = resolveExecutableOnPath('uv');
  return {
    path: discovered,
    source: discovered ? 'path' : null,
    configured: null,
  };
}

function printUvInstallGuidance(home, errorMessage = null) {
  console.error('');
  if (errorMessage) {
    console.error(`DeepScientist could not prepare a local uv runtime manager: ${errorMessage}`);
  } else {
    console.error('DeepScientist could not find a usable uv runtime manager.');
  }
  console.error(`DeepScientist normally installs uv automatically under ${runtimeUvBinDir(home)}.`);
  console.error('If the automatic bootstrap fails, install uv manually and run `ds` again.');
  console.error('');
  if (process.platform === 'win32') {
    console.error('Windows PowerShell:');
    console.error('  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"');
  } else {
    console.error('macOS / Linux:');
    console.error('  curl -LsSf https://astral.sh/uv/install.sh | sh');
  }
  console.error('Alternative:');
  console.error('  pipx install uv');
  console.error('');
}

function downloadFileWithNode(url, destinationPath) {
  const downloader = [
    'const fs = require("node:fs");',
    'const url = process.argv[1];',
    'const destination = process.argv[2];',
    'const timeoutMs = Number(process.argv[3] || "45000");',
    '(async () => {',
    '  const controller = new AbortController();',
    '  const timer = setTimeout(() => controller.abort(), timeoutMs);',
    '  try {',
    '    const response = await fetch(url, { signal: controller.signal });',
    '    if (!response.ok) {',
    '      throw new Error(`HTTP ${response.status} ${response.statusText}`);',
    '    }',
    '    const body = await response.text();',
    '    fs.writeFileSync(destination, body, "utf8");',
    '  } finally {',
    '    clearTimeout(timer);',
    '  }',
    '})().catch((error) => {',
    '  console.error(error instanceof Error ? error.message : String(error));',
    '  process.exit(1);',
    '});',
  ].join('\n');
  const result = spawnSync(process.execPath, ['-e', downloader, url, destinationPath, '45000'], {
    cwd: repoRoot,
    stdio: 'inherit',
    env: process.env,
  });
  if (result.error) {
    throw result.error;
  }
  if (result.status !== 0) {
    throw new Error(`Download failed with status ${result.status ?? 1}.`);
  }
}

function installLocalUv(home) {
  const uvRoot = runtimeUvRootPath(home);
  const binDir = runtimeUvBinDir(home);
  const tempDir = path.join(uvRoot, 'tmp');
  const installerName = process.platform === 'win32' ? 'install-uv.ps1' : 'install-uv.sh';
  const installerUrl =
    process.platform === 'win32'
      ? 'https://astral.sh/uv/install.ps1'
      : 'https://astral.sh/uv/install.sh';
  const installerPath = path.join(tempDir, installerName);

  ensureDir(binDir);
  ensureDir(tempDir);

  console.log(`DeepScientist is installing a local uv runtime manager under ${binDir}.`);
  downloadFileWithNode(installerUrl, installerPath);

  const installEnv = {
    ...process.env,
    UV_UNMANAGED_INSTALL: binDir,
  };

  let shellBinary;
  let shellArgs;
  if (process.platform === 'win32') {
    shellBinary =
      resolveExecutableOnPath('powershell.exe')
      || resolveExecutableOnPath('powershell')
      || resolveExecutableOnPath('pwsh.exe')
      || resolveExecutableOnPath('pwsh');
    if (!shellBinary) {
      throw new Error('PowerShell is not available to run the official uv installer.');
    }
    shellArgs = ['-ExecutionPolicy', 'ByPass', '-File', installerPath];
  } else {
    shellBinary = resolveExecutableOnPath('sh');
    if (!shellBinary) {
      throw new Error('`sh` is not available to run the official uv installer.');
    }
    shellArgs = [installerPath];
  }

  const installResult = spawnSync(shellBinary, shellArgs, {
    cwd: repoRoot,
    stdio: 'inherit',
    env: installEnv,
  });
  if (installResult.error) {
    throw installResult.error;
  }
  if (installResult.status !== 0) {
    throw new Error(`The official uv installer exited with status ${installResult.status ?? 1}.`);
  }

  const installedBinary = resolveBinaryReference(runtimeUvBinaryPath(home));
  if (!installedBinary) {
    throw new Error(`uv installation finished, but no executable was found under ${binDir}.`);
  }
  return installedBinary;
}

function ensureUvBinary(home) {
  const resolved = resolveUvBinary(home);
  if (resolved.path) {
    return resolved.path;
  }
  if (resolved.source === 'env' && resolved.configured) {
    throw new Error(`Configured uv binary could not be resolved: ${resolved.configured}`);
  }
  return installLocalUv(home);
}

function buildUvRuntimeEnv(home, extraEnv = {}) {
  return {
    ...process.env,
    UV_CACHE_DIR: runtimeUvCachePath(home),
    UV_PROJECT_ENVIRONMENT: runtimePythonEnvPath(home),
    UV_PYTHON_INSTALL_DIR: runtimeUvPythonInstallPath(home),
    ...extraEnv,
  };
}

function ensureUvLockPresent() {
  const lockPath = uvLockPath();
  if (fs.existsSync(lockPath)) {
    return lockPath;
  }
  console.error('DeepScientist is missing `uv.lock` in the installed package.');
  console.error('Reinstall the npm package, or from a source checkout run `uv lock` and try again.');
  process.exit(1);
}

function resolveUvVersion(uvBinary) {
  const result = runSync(uvBinary, ['--version'], { capture: true, allowFailure: true });
  if (result.status !== 0) {
    return null;
  }
  return String(result.stdout || '').trim() || null;
}

function ensureUvManagedPython(home, uvBinary, minimumVersionRequest) {
  ensureDir(runtimeUvPythonInstallPath(home));
  ensureDir(runtimeUvCachePath(home));
  step(1, 4, `Provisioning uv-managed Python ${minimumVersionRequest}+`);
  const installResult = runSync(
    uvBinary,
    ['python', 'install', minimumVersionRequest],
    {
      allowFailure: true,
      env: buildUvRuntimeEnv(home),
    }
  );
  if (installResult.status !== 0) {
    console.error('DeepScientist could not install a uv-managed Python runtime.');
    process.exit(installResult.status ?? 1);
  }

  const findResult = runSync(
    uvBinary,
    ['python', 'find', '--managed-python', minimumVersionRequest],
    {
      capture: true,
      allowFailure: true,
      env: buildUvRuntimeEnv(home),
    }
  );
  const managedPython = String(findResult.stdout || '')
    .trim()
    .split(/\r?\n/)
    .filter(Boolean)
    .pop();
  if (!managedPython) {
    console.error('DeepScientist installed uv-managed Python, but could not locate the interpreter afterward.');
    process.exit(findResult.status ?? 1);
  }
  const probe = decoratePythonProbe(probePython(managedPython), 'uv-managed');
  if (!probe || !pythonMeetsMinimum(probe)) {
    console.error('DeepScientist found a uv-managed Python, but it does not satisfy the required version.');
    process.exit(1);
  }
  return probe;
}

function syncUvProjectEnvironment(home, uvBinary, pythonTarget, editable) {
  const args = ['sync', '--frozen', '--no-dev', '--compile-bytecode', '--python', pythonTarget];
  if (!editable) {
    args.push('--no-editable');
  }
  step(2, 4, 'Syncing locked Python environment');
  const result = runSync(uvBinary, args, {
    allowFailure: true,
    env: buildUvRuntimeEnv(home),
  });
  if (result.status === 0) {
    return;
  }
  console.error('DeepScientist could not sync the locked Python environment with uv.');
  console.error('If you are working from a source checkout, run `uv lock` after dependency changes and try again.');
  process.exit(result.status ?? 1);
}

function createRuntimeSelectionProbe(runtimeProbe, sourceLabel) {
  return {
    ...runtimeProbe,
    sourceLabel,
  };
}

function ensurePythonRuntime(home) {
  ensureDir(path.join(home, 'runtime'));
  ensureDir(path.join(home, 'runtime', 'bundle'));
  ensureDir(runtimeUvCachePath(home));
  ensureDir(runtimeUvPythonInstallPath(home));
  ensureDir(runtimeToolsPath(home));
  let uvBinary;
  try {
    uvBinary = ensureUvBinary(home);
  } catch (error) {
    printUvInstallGuidance(home, error instanceof Error ? error.message : String(error));
    process.exit(1);
  }
  const runtimePlan = resolvePythonRuntimePlan();
  if (runtimePlan.runtimeKind === 'managed') {
    printManagedPythonFallbackNotice({
      rejectedProbe: runtimePlan.rejectedProbe || null,
      source: runtimePlan.source,
      minimumVersionRequest: runtimePlan.minimumVersionRequest,
      installDir: runtimeUvPythonInstallPath(home),
    });
  }
  const lockPath = ensureUvLockPresent();
  const stampPath = path.join(home, 'runtime', 'bundle', 'python-stamp.json');
  const editable = useEditableProjectInstall();
  const desiredStamp = {
    runtimeManager: 'uv',
    version: packageJson.version,
    pyprojectHash: sha256File(path.join(repoRoot, 'pyproject.toml')),
    uvLockHash: sha256File(lockPath),
    editable,
    sourceTreeHash: editable ? null : hashPythonSourceTree(),
    uvVersion: resolveUvVersion(uvBinary),
    envPath: runtimePythonEnvPath(home),
    source:
      runtimePlan.runtimeKind === 'system'
        ? {
            kind: 'system',
            source: runtimePlan.selectedProbe.source,
            sourceExecutable:
              runtimePlan.selectedProbe.realExecutable
              || runtimePlan.selectedProbe.executable
              || runtimePlan.selectedProbe.binary,
            sourceVersion: runtimePlan.selectedProbe.version,
            sourceMajorMinor: pythonMajorMinor(runtimePlan.selectedProbe),
          }
        : {
            kind: 'uv-managed',
            minimumVersionRequest: runtimePlan.minimumVersionRequest,
          },
  };

  for (let attempt = 0; attempt < 2; attempt += 1) {
    const runtimePython = runtimePythonPath(home);
    const currentStamp = readJsonFile(stampPath);
    const runtimeProbe = fs.existsSync(runtimePython) ? probePython(runtimePython) : null;
    const runtimeBroken = !runtimeProbe || !runtimeProbe.ok || !pythonMeetsMinimum(runtimeProbe);
    const stampChanged = JSON.stringify(currentStamp || null) !== JSON.stringify(desiredStamp);

    if (runtimeBroken || stampChanged) {
      const reason = runtimeBroken
        ? 'DeepScientist is repairing the local uv-managed Python runtime.'
        : 'DeepScientist detected a runtime change and is rebuilding the local uv-managed environment.';
      console.warn(reason);
      fs.rmSync(stampPath, { force: true });
      fs.rmSync(runtimePythonEnvPath(home), { recursive: true, force: true });

      let pythonTarget = null;
      let sourceLabel = null;
      if (runtimePlan.runtimeKind === 'system' && runtimePlan.selectedProbe) {
        pythonTarget =
          runtimePlan.selectedProbe.realExecutable
          || runtimePlan.selectedProbe.executable
          || runtimePlan.selectedProbe.binary;
        sourceLabel = `${runtimePlan.selectedProbe.sourceLabel} via uv-env`;
        step(1, 4, 'Preparing uv-managed Python runtime');
      } else {
        const managedPython = ensureUvManagedPython(home, uvBinary, runtimePlan.minimumVersionRequest);
        pythonTarget = managedPython.realExecutable || managedPython.executable || managedPython.binary;
        sourceLabel = managedPython.sourceLabel;
      }

      syncUvProjectEnvironment(home, uvBinary, pythonTarget, editable);
      fs.writeFileSync(stampPath, `${JSON.stringify(desiredStamp, null, 2)}\n`, 'utf8');
      const syncedProbe = fs.existsSync(runtimePython) ? probePython(runtimePython) : null;
      if (syncedProbe && syncedProbe.ok && pythonMeetsMinimum(syncedProbe) && verifyPythonRuntime(runtimePython)) {
        fs.rmSync(legacyVenvRootPath(home), { recursive: true, force: true });
        return {
          runtimePython,
          uvBinary,
          runtimeManager: 'uv',
          runtimeProbe: createRuntimeSelectionProbe(syncedProbe, sourceLabel || 'uv-managed'),
          sourcePython: runtimePlan.selectedProbe || null,
        };
      }
    }

    if (runtimeProbe && runtimeProbe.ok && pythonMeetsMinimum(runtimeProbe) && verifyPythonRuntime(runtimePython)) {
      fs.rmSync(legacyVenvRootPath(home), { recursive: true, force: true });
      return {
        runtimePython,
        uvBinary,
        runtimeManager: 'uv',
        runtimeProbe: createRuntimeSelectionProbe(
          runtimeProbe,
          runtimePlan.runtimeKind === 'system' && runtimePlan.selectedProbe
            ? `${runtimePlan.selectedProbe.sourceLabel} via uv-env`
            : 'uv-managed'
        ),
        sourcePython: runtimePlan.selectedProbe || null,
      };
    }

    console.warn('DeepScientist is retrying the local uv-managed Python runtime repair.');
    fs.rmSync(stampPath, { force: true });
    fs.rmSync(runtimePythonEnvPath(home), { recursive: true, force: true });
  }

  console.error('DeepScientist could not prepare a healthy uv-managed Python runtime.');
  process.exit(1);
}

function runPythonCli(runtimePython, args, options = {}) {
  const env = {
    ...process.env,
    DEEPSCIENTIST_REPO_ROOT: repoRoot,
    ...(options.env || {}),
  };
  return runSync(runtimePython, ['-m', 'deepscientist.cli', ...args], { ...options, env });
}

function normalizePythonCliArgs(args, home) {
  const normalized = [];
  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    if (arg === '--home') {
      index += 1;
      continue;
    }
    if (arg === '--hero' || arg === '--here') {
      continue;
    }
    normalized.push(arg);
  }
  return ['--home', home, ...normalized];
}

function ensureInitialized(home, runtimePython) {
  const stampPath = path.join(home, 'runtime', 'bundle', 'init-stamp.json');
  let currentStamp = null;
  if (fs.existsSync(stampPath)) {
    try {
      currentStamp = JSON.parse(fs.readFileSync(stampPath, 'utf8'));
    } catch {
      currentStamp = null;
    }
  }
  const desired = {
    version: packageJson.version,
    skills_hash: hashSkillTree(),
  };
  const configPath = path.join(home, 'config', 'config.yaml');
  if (
    currentStamp
    && currentStamp.version === desired.version
    && currentStamp.skills_hash === desired.skills_hash
    && fs.existsSync(configPath)
    && globalSkillsInstalled()
  ) {
    return;
  }
  step(3, 4, 'Preparing DeepScientist home, config, skills, and Git checks');
  const result = runPythonCli(runtimePython, ['--home', home, 'init'], { capture: true, allowFailure: true });
  const stdout = result.stdout || '';
  let payload = {};
  try {
    payload = JSON.parse(stdout);
  } catch {
    payload = {};
  }
  if (payload.git && Array.isArray(payload.git.guidance) && payload.git.guidance.length > 0) {
    console.log('Git guidance:');
    for (const line of payload.git.guidance) {
      console.log(`  - ${line}`);
    }
  }
  if (payload.git && payload.git.installed === false) {
    console.error('Git is required before DeepScientist can run correctly.');
    process.exit(result.status || 1 || 1);
  }
  fs.writeFileSync(stampPath, `${JSON.stringify(desired, null, 2)}\n`, 'utf8');
}

function ensureNodeBundle(subdir, entryFile) {
  const fullEntry = path.join(repoRoot, subdir, entryFile);
  if (fs.existsSync(fullEntry)) {
    return fullEntry;
  }
  const subdirRoot = path.join(repoRoot, subdir);
  const manifestPath = path.join(subdirRoot, 'package.json');
  const sourcePath = path.join(subdirRoot, 'src');
  if (!fs.existsSync(manifestPath) || !fs.existsSync(sourcePath)) {
    console.error(
      `Missing prebuilt bundle for ${subdir} in the installed package (${fullEntry}). Reinstall the npm package or use a source checkout.`
    );
    process.exit(1);
  }
  console.log(`Building ${subdir}...`);
  runSync('npm', ['--prefix', path.join(repoRoot, subdir), 'install', '--include=dev', '--no-audit', '--no-fund']);
  runSync('npm', ['--prefix', path.join(repoRoot, subdir), 'run', 'build']);
  return fullEntry;
}

function daemonStatePath(home) {
  return path.join(home, 'runtime', 'daemon.json');
}

function normalizeHomePath(home) {
  try {
    return fs.realpathSync(home);
  } catch {
    return path.resolve(home);
  }
}

function resolveExecutableOnPath(commandName) {
  const pathValue = process.env.PATH || '';
  if (!pathValue) {
    return null;
  }
  const directories = pathValue.split(path.delimiter).filter(Boolean);
  for (const directory of directories) {
    const base = path.join(directory, commandName);
    for (const candidate of candidateExecutablePaths(base)) {
      if (isExecutableFile(candidate)) {
        return candidate;
      }
    }
  }
  return null;
}

function findOptionalLatexCompiler() {
  for (const compiler of ['pdflatex', 'xelatex', 'lualatex']) {
    const resolved = resolveExecutableOnPath(compiler);
    if (resolved) {
      return { compiler, path: resolved };
    }
  }
  return null;
}

function optionalRuntimeStatePath(home) {
  return path.join(home, 'runtime', 'bundle', 'optional-runtime.json');
}

function readOptionalRuntimeState(home) {
  const statePath = optionalRuntimeStatePath(home);
  if (!fs.existsSync(statePath)) {
    return null;
  }
  try {
    return JSON.parse(fs.readFileSync(statePath, 'utf8'));
  } catch {
    return null;
  }
}

function writeOptionalRuntimeState(home, payload) {
  const statePath = optionalRuntimeStatePath(home);
  ensureDir(path.dirname(statePath));
  fs.writeFileSync(statePath, `${JSON.stringify(payload, null, 2)}\n`, 'utf8');
}

function latexInstallGuidance() {
  if (resolveExecutableOnPath('apt-get')) {
    return 'sudo apt-get update && sudo apt-get install -y texlive-latex-base texlive-latex-recommended texlive-fonts-recommended texlive-bibtex-extra';
  }
  if (resolveExecutableOnPath('dnf')) {
    return 'sudo dnf install -y texlive-scheme-basic texlive-collection-latex texlive-bibtex';
  }
  if (resolveExecutableOnPath('yum')) {
    return 'sudo yum install -y texlive-scheme-basic texlive-collection-latex texlive-bibtex';
  }
  if (resolveExecutableOnPath('pacman')) {
    return 'sudo pacman -S --needed texlive-basic texlive-latex';
  }
  if (resolveExecutableOnPath('brew')) {
    return 'brew install --cask mactex-no-gui';
  }
  return 'Install a TeX distribution that provides `pdflatex` and `bibtex`.';
}

function maybePrintOptionalLatexNotice(home) {
  const detected = findOptionalLatexCompiler();
  const currentState = {
    version: packageJson.version,
    latex: detected
      ? {
          available: true,
          compiler: detected.compiler,
          path: detected.path,
        }
      : {
          available: false,
          compiler: null,
          path: null,
        },
  };
  const previousState = readOptionalRuntimeState(home);
  const changed = JSON.stringify(previousState || null) !== JSON.stringify(currentState);
  if (!changed) {
    return;
  }
  writeOptionalRuntimeState(home, currentState);
  console.log('');
  if (detected) {
    console.log(`Optional LaTeX runtime: detected ${detected.compiler} at ${detected.path}`);
    console.log('Local paper PDF compilation is available.');
    return;
  }
  console.log('Optional LaTeX runtime: not detected.');
  console.log('DeepScientist still installs and runs normally.');
  console.log('Install LaTeX only if you want local paper PDF compilation from the web workspace.');
  console.log(`Suggested install: ${latexInstallGuidance()}`);
}

function readDaemonState(home) {
  const statePath = daemonStatePath(home);
  if (!fs.existsSync(statePath)) {
    return null;
  }
  try {
    return JSON.parse(fs.readFileSync(statePath, 'utf8'));
  } catch {
    return null;
  }
}

function writeDaemonState(home, payload) {
  fs.writeFileSync(daemonStatePath(home), `${JSON.stringify(payload, null, 2)}\n`, 'utf8');
}

function removeDaemonState(home) {
  const statePath = daemonStatePath(home);
  if (fs.existsSync(statePath)) {
    fs.unlinkSync(statePath);
  }
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function isHealthy(url) {
  const payload = await fetchHealth(url);
  return Boolean(payload && payload.status === 'ok');
}

async function fetchHealth(url) {
  try {
    const response = await fetch(`${url}/api/health`);
    if (!response.ok) {
      return null;
    }
    return await response.json();
  } catch {
    return null;
  }
}

function healthMatchesManagedState({ health, state, home }) {
  if (!health || health.status !== 'ok') {
    return false;
  }
  const expectedHome = normalizeHomePath(home);
  const actualHome = typeof health.home === 'string' && health.home ? normalizeHomePath(health.home) : null;
  if (!actualHome || actualHome !== expectedHome) {
    return false;
  }
  const expectedDaemonId = typeof state?.daemon_id === 'string' ? state.daemon_id.trim() : '';
  const actualDaemonId = typeof health.daemon_id === 'string' ? health.daemon_id.trim() : '';
  if (!expectedDaemonId || !actualDaemonId) {
    return false;
  }
  return expectedDaemonId === actualDaemonId;
}

function healthMatchesHome({ health, home }) {
  if (!health || health.status !== 'ok') {
    return false;
  }
  const expectedHome = normalizeHomePath(home);
  const actualHome = typeof health.home === 'string' && health.home ? normalizeHomePath(health.home) : null;
  return Boolean(actualHome && actualHome === expectedHome);
}

function daemonIdentityError({ url, home, health, state }) {
  const expectedHome = normalizeHomePath(home);
  const actualHome = typeof health?.home === 'string' ? health.home : 'unknown';
  const actualDaemonId = typeof health?.daemon_id === 'string' ? health.daemon_id : 'unknown';
  const expectedDaemonId = typeof state?.daemon_id === 'string' ? state.daemon_id : 'missing';
  return [
    `Refusing to operate on daemon at ${url} because its identity does not match this launcher state.`,
    `Expected home: ${expectedHome}`,
    `Reported home: ${actualHome}`,
    `Expected daemon_id: ${expectedDaemonId}`,
    `Reported daemon_id: ${actualDaemonId}`,
  ].join('\n');
}

async function requestDaemonShutdown(url, daemonId) {
  try {
    const response = await fetch(`${url}/api/admin/shutdown`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ source: 'ds-launcher', daemon_id: daemonId || null }),
    });
    if (!response.ok) {
      return false;
    }
    const payload = await response.json().catch(() => ({}));
    return payload.ok !== false;
  } catch {
    return false;
  }
}

function isPidAlive(pid) {
  if (!pid) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

function killManagedProcess(pid, signal) {
  if (!pid) return false;
  if (process.platform === 'win32') {
    const taskkillArgs = ['/PID', String(pid)];
    if (signal === 'SIGKILL') {
      taskkillArgs.push('/T', '/F');
    }
    const result = spawnSync('taskkill', taskkillArgs, { stdio: 'ignore' });
    return result.status === 0;
  }
  try {
    process.kill(-pid, signal);
    return true;
  } catch {
    try {
      process.kill(pid, signal);
      return true;
    } catch {
      return false;
    }
  }
}

async function waitForDaemonStop({ url, pid, attempts = 20, delayMs = 200 }) {
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    const healthy = url ? await isHealthy(url) : false;
    const alive = pid ? isPidAlive(pid) : false;
    if (!healthy && !alive) {
      return true;
    }
    if (!healthy && !pid) {
      return true;
    }
    await sleep(delayMs);
  }
  return false;
}

function tailLog(logPath) {
  if (!fs.existsSync(logPath)) {
    return '';
  }
  const content = fs.readFileSync(logPath, 'utf8').trim();
  return content.split(/\r?\n/).slice(-20).join('\n');
}

async function stopDaemon(home) {
  const state = readDaemonState(home);
  const configured = readConfiguredUiAddressFromFile(home);
  const url = state?.url || browserUiUrl(state?.host || configured.host, state?.port || configured.port);
  const healthBefore = await fetchHealth(url);
  const healthyBefore = Boolean(healthBefore && healthBefore.status === 'ok');
  const sameHomeHealthy = healthMatchesHome({ health: healthBefore, home });
  const pid = state?.pid || (sameHomeHealthy ? healthBefore?.pid : null);
  const shutdownDaemonId = sameHomeHealthy ? healthBefore?.daemon_id : state?.daemon_id;

  if (!state && !healthyBefore) {
    console.log('No managed DeepScientist daemon is running.');
    removeDaemonState(home);
    return;
  }

  if (!state && healthyBefore) {
    if (!sameHomeHealthy) {
      console.error(
        [
          `A DeepScientist daemon is reachable at ${url}, but there is no managed daemon state for ${normalizeHomePath(home)}.`,
          'Refusing to stop an unverified daemon.',
        ].join('\n')
      );
      process.exit(1);
    }
  }

  if (healthyBefore && !healthMatchesManagedState({ health: healthBefore, state, home })) {
    if (!sameHomeHealthy) {
      console.error(daemonIdentityError({ url, home, health: healthBefore, state }));
      process.exit(1);
    }
  }

  let stopped = false;

  if (healthyBefore) {
    await requestDaemonShutdown(url, shutdownDaemonId || null);
    stopped = await waitForDaemonStop({ url, pid, attempts: 20, delayMs: 200 });
  }

  if (!stopped && pid && isPidAlive(pid)) {
    killManagedProcess(pid, 'SIGTERM');
    stopped = await waitForDaemonStop({ url, pid, attempts: 30, delayMs: 200 });
  }

  if (!stopped && pid && isPidAlive(pid)) {
    killManagedProcess(pid, 'SIGKILL');
    stopped = await waitForDaemonStop({ url, pid, attempts: 20, delayMs: 150 });
  }

  const stillHealthy = await isHealthy(url);
  if (!stopped && (stillHealthy || (pid && isPidAlive(pid)))) {
    console.error('DeepScientist daemon is still running after shutdown attempts.');
    process.exit(1);
  }

  removeDaemonState(home);
  console.log('DeepScientist daemon stopped.');
}

function writeUpdateLog(home, content) {
  const logPath = path.join(home, 'logs', 'update.log');
  ensureDir(path.dirname(logPath));
  fs.appendFileSync(logPath, `${content.replace(/\s+$/, '')}\n`, 'utf8');
  return logPath;
}

function summarizeUpdateFailure(result) {
  const lines = [];
  if (result.error) {
    lines.push(result.error);
  }
  if (result.stderr) {
    lines.push(String(result.stderr).trim());
  }
  if (result.stdout) {
    lines.push(String(result.stdout).trim());
  }
  return lines.filter(Boolean).join('\n').trim() || 'Unknown update failure.';
}

function runNpmInstallLatest(home, npmBinary) {
  const args = ['install', '-g', `${UPDATE_PACKAGE_NAME}@latest`, '--no-audit', '--no-fund'];
  const startedAt = new Date().toISOString();
  const result = spawnSync(npmBinary, args, {
    encoding: 'utf8',
    env: process.env,
    timeout: 15 * 60 * 1000,
  });
  const finishedAt = new Date().toISOString();
  const logPath = writeUpdateLog(
    home,
    [
      `=== ${startedAt} installing ${UPDATE_PACKAGE_NAME}@latest ===`,
      `$ ${npmBinary} ${args.join(' ')}`,
      String(result.stdout || '').trim(),
      String(result.stderr || '').trim(),
      `exit=${result.status ?? 'null'} error=${result.error ? result.error.message : 'none'}`,
      `=== finished ${finishedAt} ===`,
      '',
    ].join('\n')
  );
  return {
    ok: !result.error && result.status === 0,
    stdout: String(result.stdout || ''),
    stderr: String(result.stderr || ''),
    error: result.error ? result.error.message : null,
    status: result.status ?? null,
    logPath,
  };
}

async function promptUpdateAction(status) {
  const options = [
    {
      value: 'update',
      label: status.can_self_update ? 'Update now' : 'Show manual update',
    },
    { value: 'later', label: 'Remind me later' },
    { value: 'skip', label: 'Skip this version' },
  ];
  if (!process.stdin.isTTY || !process.stdout.isTTY) {
    return 'later';
  }
  return new Promise((resolve) => {
    let selected = 1;
    const lines = [
      '',
      'A new DeepScientist version is available.',
      '',
      `Current: ${status.current_version}`,
      `Latest:  ${status.latest_version || 'unknown'}`,
      '',
      status.can_self_update
        ? 'What do you want to do?'
        : 'Self-update is not available for this installation. Choose an action:',
    ];

    const cleanup = () => {
      process.stdin.off('keypress', onKeypress);
      if (process.stdin.isTTY) {
        process.stdin.setRawMode(false);
      }
      process.stdin.pause();
      console.log('');
    };

    const render = () => {
      console.clear();
      for (const line of lines) {
        console.log(line);
      }
      for (let index = 0; index < options.length; index += 1) {
        const option = options[index];
        console.log(`${index === selected ? '>' : ' '} ${option.label}`);
      }
      console.log('');
      console.log('Use ↑/↓ and Enter.');
    };

    const onKeypress = (_str, key) => {
      if (key?.name === 'up') {
        selected = (selected - 1 + options.length) % options.length;
        render();
        return;
      }
      if (key?.name === 'down') {
        selected = (selected + 1) % options.length;
        render();
        return;
      }
      if (key?.name === 'return') {
        const choice = options[selected].value;
        cleanup();
        resolve(choice);
        return;
      }
      if (key?.ctrl && key?.name === 'c') {
        cleanup();
        resolve('later');
      }
    };

    readline.emitKeypressEvents(process.stdin);
    process.stdin.setRawMode(true);
    process.stdin.resume();
    process.stdin.on('keypress', onKeypress);
    render();
  });
}

function printUpdateStatus(status, { compact = false } = {}) {
  if (compact) {
    if (status.update_available) {
      console.log(
        `DeepScientist update available: ${status.current_version} -> ${status.latest_version}`
      );
      if (status.can_self_update) {
        console.log('Run `ds update --yes` to install it.');
      } else {
        console.log(`Manual update: ${status.manual_update_command}`);
      }
      return;
    }
    console.log(`DeepScientist is up to date (${status.current_version}).`);
    return;
  }

  console.log('DeepScientist update status');
  renderKeyValueRows([
    ['Current', status.current_version],
    ['Latest', status.latest_version || 'unknown'],
    ['Available', status.update_available ? 'yes' : 'no'],
    ['Install mode', status.install_mode],
    ['Self-update', status.can_self_update ? 'supported' : 'manual-only'],
    ['Last checked', status.last_checked_at || 'never'],
  ]);
  if (status.last_check_error) {
    console.log('');
    console.log(`Version check error: ${status.last_check_error}`);
  }
  if (!status.can_self_update) {
    console.log('');
    console.log(`Manual update command: ${status.manual_update_command}`);
    if (status.reason) {
      console.log(status.reason);
    }
  }
  const npmBinary = resolveNpmBinary();
  if (!npmBinary) {
    return {
      ok: false,
      updated: false,
      status,
      message: '`npm` is not available on PATH.',
    };
  }
}

function spawnDetachedNode(args, options = {}) {
  const out = options.logPath ? fs.openSync(options.logPath, 'a') : 'ignore';
  const child = spawn(process.execPath, args, {
    cwd: options.cwd || repoRoot,
    detached: true,
    stdio: ['ignore', out, out],
    env: options.env || process.env,
  });
  child.unref();
  return child;
}

async function restartIntoUpdatedLauncher(rawArgs) {
  const launcherPath = resolveLauncherPath();
  if (!launcherPath) {
    throw new Error('Could not resolve the DeepScientist launcher after the update.');
  }
  const args = [launcherPath, '--skip-update-check', ...rawArgs.filter((item) => item !== '--skip-update-check')];
  const child = spawn(process.execPath, args, {
    cwd: repoRoot,
    stdio: 'inherit',
    env: process.env,
  });
  await new Promise((resolve, reject) => {
    child.on('error', reject);
    child.on('exit', (code) => {
      process.exit(code ?? 0);
      resolve();
    });
  });
}

async function performSelfUpdate(home, options = {}) {
  const status = checkForUpdates(home, { force: true });
  if (!status.update_available) {
    return {
      ok: true,
      updated: false,
      status,
      message: `DeepScientist is already on the latest version (${status.current_version}).`,
    };
  }
  if (!status.can_self_update) {
    return {
      ok: false,
      updated: false,
      status,
      message: status.reason || `Manual update required: ${status.manual_update_command}`,
    };
  }

  const daemonState = readDaemonState(home);
  const configuredUi = readConfiguredUiAddressFromFile(home, options.host, options.port);
  const host = options.host || daemonState?.host || configuredUi.host;
  const port = options.port || daemonState?.port || configuredUi.port;
  const targetVersion = status.latest_version;

  mergeUpdateState(home, {
    current_version: status.current_version,
    latest_version: targetVersion,
    target_version: targetVersion,
    busy: true,
    last_update_started_at: new Date().toISOString(),
    last_update_result: null,
  });

  try {
    if (daemonState?.pid || daemonState?.daemon_id) {
      await stopDaemon(home);
    }
  } catch (error) {
    mergeUpdateState(home, {
      busy: false,
      last_update_finished_at: new Date().toISOString(),
      last_update_result: {
        ok: false,
        target_version: targetVersion,
        message: error instanceof Error ? error.message : String(error),
      },
    });
    return {
      ok: false,
      updated: false,
      status,
      message: error instanceof Error ? error.message : String(error),
    };
  }

  const installResult = runNpmInstallLatest(home, npmBinary);
  if (!installResult.ok) {
    const message = summarizeUpdateFailure(installResult);
    mergeUpdateState(home, {
      busy: false,
      last_update_finished_at: new Date().toISOString(),
      last_update_result: {
        ok: false,
        target_version: targetVersion,
        message,
        log_path: installResult.logPath,
      },
    });
    return {
      ok: false,
      updated: false,
      status,
      message,
      log_path: installResult.logPath,
    };
  }

  const restartDaemon =
    options.restartDaemon === true
    || (options.restartDaemon !== false && Boolean(daemonState?.pid || daemonState?.daemon_id));
  if (restartDaemon) {
    const launcherPath = resolveLauncherPath();
    if (!launcherPath) {
      const message = 'DeepScientist was updated, but the new launcher path could not be resolved for daemon restart.';
      mergeUpdateState(home, {
        busy: false,
        last_update_finished_at: new Date().toISOString(),
        last_update_result: {
          ok: false,
          target_version: targetVersion,
          message,
          log_path: installResult.logPath,
        },
      });
      return {
        ok: false,
        updated: true,
        status,
        message,
        log_path: installResult.logPath,
      };
    }
    spawnDetachedNode(
      [
        launcherPath,
        '--home',
        home,
        '--host',
        String(host),
        '--port',
        String(port),
        '--daemon-only',
        '--no-browser',
        '--skip-update-check',
      ],
      {
        cwd: repoRoot,
        env: process.env,
        logPath: path.join(home, 'logs', 'daemon-restart.log'),
      }
    );
  }

  mergeUpdateState(home, {
    busy: false,
    current_version: targetVersion,
    latest_version: targetVersion,
    target_version: null,
    last_checked_at: new Date().toISOString(),
    last_check_error: null,
    last_update_finished_at: new Date().toISOString(),
    last_update_result: {
      ok: true,
      target_version: targetVersion,
      message: restartDaemon
        ? `DeepScientist updated to ${targetVersion}. The daemon is restarting.`
        : `DeepScientist updated to ${targetVersion}.`,
      log_path: installResult.logPath,
    },
  });

  return {
    ok: true,
    updated: true,
    status: buildUpdateStatus(home),
    message: restartDaemon
      ? `DeepScientist updated to ${targetVersion}. The daemon is restarting.`
      : `DeepScientist updated to ${targetVersion}.`,
    log_path: installResult.logPath,
  };
}

async function maybeHandleStartupUpdate(home, rawArgs, options = {}) {
  if (options.skipUpdateCheck || process.env.DS_SKIP_UPDATE_PROMPT === '1') {
    return false;
  }
  const status = checkForUpdates(home, { force: false });
  if (!status.update_available) {
    return false;
  }
  if (!status.prompt_recommended) {
    return false;
  }

  if (!process.stdin.isTTY || !process.stdout.isTTY) {
    printUpdateStatus(status, { compact: true });
    mergeUpdateState(home, {
      last_prompted_at: new Date().toISOString(),
    });
    return false;
  }

  const action = await promptUpdateAction(status);
  if (action === 'later') {
    markUpdateDeferred(home, status.latest_version);
    return false;
  }
  if (action === 'skip') {
    markUpdateSkipped(home, status.latest_version);
    return false;
  }
  if (action === 'update' && !status.can_self_update) {
    console.log(`Manual update required: ${status.manual_update_command}`);
    if (status.reason) {
      console.log(status.reason);
    }
    markUpdateDeferred(home, status.latest_version);
    return false;
  }
  if (action === 'update') {
    console.log(`Updating DeepScientist ${status.current_version} -> ${status.latest_version} ...`);
    const result = await performSelfUpdate(home, { restartDaemon: false });
    if (!result.ok) {
      console.error(result.message);
      return false;
    }
    console.log(result.message);
    await restartIntoUpdatedLauncher(rawArgs);
    return true;
  }
  return false;
}

async function startBackgroundUpdateWorker(home, options = {}) {
  const launcherPath = resolveLauncherPath();
  if (!launcherPath) {
    return {
      ok: false,
      started: false,
      message: 'Could not resolve the launcher path for the background update worker.',
    };
  }
  const status = checkForUpdates(home, { force: false });
  mergeUpdateState(home, {
    current_version: status.current_version,
    latest_version: status.latest_version,
    target_version: status.latest_version,
    busy: true,
    last_update_started_at: new Date().toISOString(),
    last_update_result: null,
  });
  const workerArgs = [
    launcherPath,
    'update',
    '--yes',
    '--worker',
    '--home',
    home,
    '--host',
    String(options.host || '0.0.0.0'),
    '--port',
    String(options.port || 20999),
    '--restart-daemon',
    '--skip-update-check',
  ];
  spawnDetachedNode(workerArgs, {
    cwd: repoRoot,
    env: process.env,
    logPath: path.join(home, 'logs', 'update-worker.log'),
  });
  return {
    ok: true,
    started: true,
    message: 'DeepScientist update worker started.',
    status: buildUpdateStatus(home),
  };
}

async function readConfiguredUiAddress(home, runtimePython, fallbackHost, fallbackPort) {
  try {
    const result = runPythonCli(runtimePython, ['--home', home, 'config', 'show', 'config'], { capture: true, allowFailure: true });
    const text = result.stdout || '';
    const hostMatch = text.match(/^\s*host:\s*["']?([^"'\n]+)["']?\s*$/m);
    const portMatch = text.match(/^\s*port:\s*(\d+)\s*$/m);
    const modeMatch = text.match(/^\s*default_mode:\s*["']?([^"'\n]+)["']?\s*$/m);
    const autoOpenMatch = text.match(/^\s*auto_open_browser:\s*([^\n]+)\s*$/m);
    return {
      host: fallbackHost || (hostMatch ? hostMatch[1].trim() : '0.0.0.0'),
      port: fallbackPort || (portMatch ? Number(portMatch[1]) : 20999),
      defaultMode: normalizeMode(modeMatch ? modeMatch[1].trim() : 'web'),
      autoOpenBrowser: parseBooleanSetting(autoOpenMatch ? autoOpenMatch[1].trim() : true, true),
    };
  } catch {
    return {
      host: fallbackHost || '0.0.0.0',
      port: fallbackPort || 20999,
      defaultMode: 'web',
      autoOpenBrowser: true,
    };
  }
}

function readConfiguredUiAddressFromFile(home, fallbackHost, fallbackPort) {
  const configPath = path.join(home, 'config', 'config.yaml');
  if (!fs.existsSync(configPath)) {
    return {
      host: fallbackHost || '0.0.0.0',
      port: fallbackPort || 20999,
      defaultMode: 'web',
      autoOpenBrowser: true,
    };
  }
  try {
    const text = fs.readFileSync(configPath, 'utf8');
    const hostMatch = text.match(/^\s*host:\s*["']?([^"'\n]+)["']?\s*$/m);
    const portMatch = text.match(/^\s*port:\s*(\d+)\s*$/m);
    const modeMatch = text.match(/^\s*default_mode:\s*["']?([^"'\n]+)["']?\s*$/m);
    const autoOpenMatch = text.match(/^\s*auto_open_browser:\s*([^\n]+)\s*$/m);
    return {
      host: fallbackHost || (hostMatch ? hostMatch[1].trim() : '0.0.0.0'),
      port: fallbackPort || (portMatch ? Number(portMatch[1]) : 20999),
      defaultMode: normalizeMode(modeMatch ? modeMatch[1].trim() : 'web'),
      autoOpenBrowser: parseBooleanSetting(autoOpenMatch ? autoOpenMatch[1].trim() : true, true),
    };
  } catch {
    return {
      host: fallbackHost || '0.0.0.0',
      port: fallbackPort || 20999,
      defaultMode: 'web',
      autoOpenBrowser: true,
    };
  }
}

async function startDaemon(home, runtimePython, host, port) {
  const browserUrl = browserUiUrl(host, port);
  const daemonBindUrl = bindUiUrl(host, port);
  const state = readDaemonState(home);
  const existingHealth = await fetchHealth(browserUrl);
  if (existingHealth && existingHealth.status === 'ok') {
    if (state && healthMatchesManagedState({ health: existingHealth, state, home })) {
      return { url: browserUrl, bindUrl: daemonBindUrl, reused: true };
    }
    console.error(
      state
        ? daemonIdentityError({ url: browserUrl, home, health: existingHealth, state })
        : [
            `A DeepScientist daemon is already listening at ${browserUrl}, but it is not associated with the managed state for ${normalizeHomePath(home)}.`,
            'Use a different port or stop the foreign daemon first.',
          ].join('\n')
    );
    process.exit(1);
  }

  if (state && state.pid && !isPidAlive(state.pid)) {
    removeDaemonState(home);
  }

  const bootstrapState = readCodexBootstrapState(home, runtimePython);
  if (!bootstrapState.codex_ready) {
    console.log('Codex is not marked ready yet. Running startup probe...');
    const probe = probeCodexBootstrap(home, runtimePython);
    if (!probe || probe.ok !== true) {
      throw createCodexPreflightError(home, probe);
    }
  }

  ensureNodeBundle('src/ui', 'dist/index.html');

  const logPath = path.join(home, 'logs', 'daemon.log');
  ensureDir(path.dirname(logPath));
  const out = fs.openSync(logPath, 'a');
  const daemonId = crypto.randomUUID();
  const child = spawn(
    runtimePython,
    ['-m', 'deepscientist.cli', '--home', home, 'daemon', '--host', host, '--port', String(port)],
    {
      cwd: repoRoot,
      detached: true,
      stdio: ['ignore', out, out],
      env: {
        ...process.env,
        DEEPSCIENTIST_REPO_ROOT: repoRoot,
        DEEPSCIENTIST_NODE_BINARY: process.execPath,
        DEEPSCIENTIST_LAUNCHER_PATH: path.join(repoRoot, 'bin', 'ds.js'),
        DS_DAEMON_ID: daemonId,
        DS_DAEMON_MANAGED_BY: 'ds-launcher',
      },
    }
  );
  child.unref();
  const statePayload = {
    pid: child.pid,
    host,
    port,
    url: browserUrl,
    bind_url: daemonBindUrl,
    log_path: logPath,
    started_at: new Date().toISOString(),
    home: normalizeHomePath(home),
    daemon_id: daemonId,
  };
  writeDaemonState(home, statePayload);

  for (let attempt = 0; attempt < 60; attempt += 1) {
    const health = await fetchHealth(browserUrl);
    if (health && health.status === 'ok') {
      if (!healthMatchesManagedState({ health, state: readDaemonState(home), home })) {
        console.error(daemonIdentityError({ url: browserUrl, home, health, state: readDaemonState(home) }));
        process.exit(1);
      }
      return { url: browserUrl, bindUrl: daemonBindUrl, reused: false };
    }
    await sleep(250);
  }

  console.error('DeepScientist daemon failed to become healthy.');
  const logTail = tailLog(logPath);
  if (logTail) {
    console.error(logTail);
  }
  process.exit(1);
}

function openBrowser(url) {
  const spawnDetached = (command, args) => {
    try {
      const child = spawn(command, args, { detached: true, stdio: 'ignore' });
      child.unref();
      return true;
    } catch {
      return false;
    }
  };

  if (process.platform === 'darwin') {
    const opener = resolveExecutableOnPath('open');
    return opener ? spawnDetached(opener, [url]) : false;
  }
  if (process.platform === 'win32') {
    return spawnDetached('cmd', ['/c', 'start', '', url]);
  }

  const commands = [
    { command: 'xdg-open', args: [url] },
    { command: 'gio', args: ['open', url] },
    { command: 'sensible-browser', args: [url] },
    { command: 'gnome-open', args: [url] },
    { command: 'kde-open', args: [url] },
    { command: 'kde-open5', args: [url] },
  ];
  for (const candidate of commands) {
    const resolved = resolveExecutableOnPath(candidate.command);
    if (!resolved) {
      continue;
    }
    if (spawnDetached(resolved, candidate.args)) {
      return true;
    }
  }
  return false;
}

function handleCodexPreflightFailure(error) {
  if (!error || error.code !== 'DS_CODEX_PREFLIGHT') {
    return false;
  }
  console.error('');
  console.error('DeepScientist could not start because Codex is not ready yet.');
  console.error(`Report: ${error.reportPath}`);
  if (Array.isArray(error.probe?.errors)) {
    for (const item of error.probe.errors) {
      console.error(`  - ${item}`);
    }
  }
  openBrowser(error.reportUrl);
  process.exit(1);
  return true;
}

function launchTui(url, questId, home, runtimePython) {
  const entry = ensureNodeBundle('src/tui', 'dist/index.js');
  const args = [entry, '--base-url', url];
  if (questId) {
    args.push('--quest-id', questId);
  }
  const child = spawn(process.execPath, args, {
    cwd: repoRoot,
    stdio: 'inherit',
    env: {
      ...process.env,
      DEEPSCIENTIST_TUI_HOME: home,
      DEEPSCIENTIST_TUI_PYTHON: runtimePython,
      DEEPSCIENTIST_RUNTIME_PYTHON: runtimePython,
    },
  });
  child.on('exit', (code) => {
    process.exit(code ?? 0);
  });
}

async function updateMain(rawArgs) {
  const options = parseUpdateArgs(rawArgs);
  if (!options) {
    printUpdateHelp();
    process.exit(1);
  }
  if (options.help) {
    printUpdateHelp();
    process.exit(0);
  }

  const home = options.home || resolveHome(rawArgs);
  ensureDir(home);

  if (options.background && options.yes && !options.worker) {
    const payload = await startBackgroundUpdateWorker(home, {
      host: options.host,
      port: options.port,
    });
    if (options.json) {
      console.log(JSON.stringify(payload, null, 2));
    } else {
      console.log(payload.message);
    }
    process.exit(payload.ok ? 0 : 1);
  }

  const status = checkForUpdates(home, { force: options.forceCheck || options.check || options.yes || options.worker });

  if (options.remindLater) {
    const payload = markUpdateDeferred(home, status.latest_version);
    if (options.json) {
      console.log(JSON.stringify(payload, null, 2));
    } else {
      console.log(`DeepScientist will remind you later about ${payload.latest_version || 'the next release'}.`);
    }
    process.exit(0);
  }

  if (options.skipVersion) {
    const payload = markUpdateSkipped(home, status.latest_version);
    if (options.json) {
      console.log(JSON.stringify(payload, null, 2));
    } else {
      console.log(`DeepScientist will stop prompting for ${payload.last_skipped_version || payload.latest_version || 'this release'}.`);
    }
    process.exit(0);
  }

  if (options.worker) {
    const payload = await performSelfUpdate(home, {
      host: options.host,
      port: options.port,
      restartDaemon: options.restartDaemon,
    });
    if (options.json) {
      console.log(JSON.stringify(payload, null, 2));
    } else {
      console.log(payload.message);
    }
    process.exit(payload.ok ? 0 : 1);
  }

  if (options.yes) {
    const payload = await performSelfUpdate(home, {
      host: options.host,
      port: options.port,
      restartDaemon: options.restartDaemon,
    });
    if (options.json) {
      console.log(JSON.stringify(payload, null, 2));
    } else {
      console.log(payload.message);
    }
    process.exit(payload.ok ? 0 : 1);
  }

  if (options.check || options.json) {
    if (options.json) {
      console.log(JSON.stringify(status, null, 2));
    } else {
      printUpdateStatus(status);
    }
    process.exit(0);
  }

  if (!status.update_available) {
    printUpdateStatus(status, { compact: true });
    process.exit(0);
  }

  if (!process.stdin.isTTY || !process.stdout.isTTY) {
    printUpdateStatus(status, { compact: true });
    process.exit(0);
  }

  const action = await promptUpdateAction(status);
  if (action === 'later') {
    markUpdateDeferred(home, status.latest_version);
    console.log('Update reminder deferred.');
    process.exit(0);
  }
  if (action === 'skip') {
    markUpdateSkipped(home, status.latest_version);
    console.log(`Skipped ${status.latest_version}.`);
    process.exit(0);
  }
  if (!status.can_self_update) {
    console.log(`Manual update command: ${status.manual_update_command}`);
    if (status.reason) {
      console.log(status.reason);
    }
    process.exit(0);
  }
  const payload = await performSelfUpdate(home, {
    host: options.host,
    port: options.port,
    restartDaemon: options.restartDaemon,
  });
  console.log(payload.message);
  process.exit(payload.ok ? 0 : 1);
}

async function migrateMain(rawArgs) {
  const options = parseMigrateArgs(rawArgs);
  if (!options) {
    printMigrateHelp();
    process.exit(1);
  }
  if (options.help) {
    printMigrateHelp();
    process.exit(0);
  }

  const sourceHome = realpathOrSelf(options.home || resolveHome(rawArgs));
  const targetHome = path.resolve(options.target);
  if (!fs.existsSync(sourceHome)) {
    console.error(`DeepScientist source path does not exist: ${sourceHome}`);
    process.exit(1);
  }
  if (isPathEqual(sourceHome, targetHome)) {
    console.error('DeepScientist source and target paths are identical. Choose a different migration target.');
    process.exit(1);
  }
  if (isPathInside(targetHome, sourceHome) || isPathInside(sourceHome, targetHome)) {
    console.error('DeepScientist migration requires two separate sibling paths. Do not nest one path inside the other.');
    process.exit(1);
  }
  if (fs.existsSync(targetHome)) {
    console.error(`DeepScientist target path already exists: ${targetHome}`);
    process.exit(1);
  }

  printMigrationSummary({ sourceHome, targetHome, restart: options.restart });
  if (!options.yes) {
    const confirmed = await promptMigrationConfirmation({ sourceHome, targetHome });
    if (!confirmed) {
      console.log('DeepScientist migration cancelled.');
      process.exit(1);
    }
  }

  const state = readDaemonState(sourceHome);
  const configured = readConfiguredUiAddressFromFile(sourceHome);
  const url = state?.url || browserUiUrl(configured.host, configured.port);
  const health = await fetchHealth(url);
  if (state || healthMatchesHome({ health, home: sourceHome })) {
    await stopDaemon(sourceHome);
  } else if (health && health.status === 'ok') {
    console.log(`Skipping daemon stop because ${url} belongs to another DeepScientist home.`);
  }

  const pythonRuntime = ensurePythonRuntime(sourceHome);
  const runtimePython = pythonRuntime.runtimePython;
  const result = runPythonCli(
    runtimePython,
    ['--home', sourceHome, 'migrate', targetHome],
    { capture: true, allowFailure: true }
  );
  let payload = null;
  try {
    payload = JSON.parse(String(result.stdout || '{}'));
  } catch {
    payload = null;
  }
  if (result.status !== 0 || !payload || payload.ok !== true) {
    if (result.stdout) {
      process.stdout.write(result.stdout);
      if (!String(result.stdout).endsWith('\n')) {
        process.stdout.write('\n');
      }
    }
    if (result.stderr) {
      process.stderr.write(result.stderr);
      if (!String(result.stderr).endsWith('\n')) {
        process.stderr.write('\n');
      }
    }
    console.error('DeepScientist migration failed.');
    process.exit(result.status ?? 1);
  }

  repairMigratedInstallWrappers(targetHome);
  const rewrittenWrappers = rewriteLauncherWrappersIfPointingAtSource({ sourceHome, targetHome });

  const sourceContainsCurrentInstall = isPathEqual(repoRoot, path.join(sourceHome, 'cli')) || isPathInside(repoRoot, sourceHome);
  if (sourceContainsCurrentInstall) {
    scheduleDeferredSourceCleanup({ sourceHome, targetHome });
  } else {
    fs.rmSync(sourceHome, { recursive: true, force: true });
  }

  let restartMessage = 'Restart skipped.';
  if (options.restart) {
    const migratedLauncher = path.join(targetHome, 'cli', 'bin', 'ds.js');
    if (!fs.existsSync(migratedLauncher)) {
      restartMessage = `Migration succeeded, but restart was skipped because the migrated launcher is missing: ${migratedLauncher}`;
    } else {
      const child = spawn(
        process.execPath,
        [migratedLauncher, '--home', targetHome, '--daemon-only', '--no-browser', '--skip-update-check'],
        {
          cwd: path.join(targetHome, 'cli'),
          detached: true,
          stdio: 'ignore',
          env: process.env,
        }
      );
      child.unref();
      restartMessage = 'Managed daemon restart scheduled from the migrated home.';
    }
  }

  console.log('');
  console.log('DeepScientist migration completed.');
  console.log(`New home: ${targetHome}`);
  if (payload.summary) {
    console.log(payload.summary);
  }
  if (rewrittenWrappers.length > 0) {
    console.log(`Updated wrappers: ${rewrittenWrappers.join(', ')}`);
  }
  console.log(restartMessage);
  if (sourceContainsCurrentInstall) {
    console.log(`Old path cleanup has been scheduled: ${sourceHome}`);
  } else {
    console.log(`Old path removed: ${sourceHome}`);
  }
  console.log(`Use \`ds --home ${targetHome}\` if you want to override the default explicitly.`);
  process.exit(0);
}

async function launcherMain(rawArgs) {
  const options = parseLauncherArgs(rawArgs);
  if (!options) {
    return false;
  }
  if (options.help) {
    printLauncherHelp();
    process.exit(0);
  }

  const home = options.home || resolveHome(rawArgs);
  ensureDir(home);

  if (options.stop) {
    await stopDaemon(home);
    process.exit(0);
  }

  if (options.status) {
    const state = readDaemonState(home);
    const configured = readConfiguredUiAddressFromFile(home, options.host, options.port);
    const url = state?.url || browserUiUrl(configured.host, configured.port);
    const health = await fetchHealth(url);
    const healthy = Boolean(health && health.status === 'ok');
    const identityMatch = state ? healthMatchesManagedState({ health, state, home }) : false;
    console.log(
      JSON.stringify(
        {
          healthy,
          identity_match: identityMatch,
          managed: Boolean(state),
          home,
          url,
          daemon: state,
          health,
        },
        null,
        2
      )
    );
    process.exit(healthy && (!state || identityMatch) ? 0 : 1);
  }

  const pythonRuntime = ensurePythonRuntime(home);
  const runtimePython = pythonRuntime.runtimePython;
  ensureInitialized(home, runtimePython);
  if (await maybeHandleStartupUpdate(home, rawArgs, options)) {
    return true;
  }
  maybePrintOptionalLatexNotice(home);

  const configuredUi = await readConfiguredUiAddress(home, runtimePython, options.host, options.port);
  const host = configuredUi.host;
  const port = configuredUi.port;
  const mode = normalizeMode(options.mode ?? 'web');
  const shouldOpenBrowser = options.daemonOnly
    ? false
    : options.openBrowser === null
      ? configuredUi.autoOpenBrowser !== false && mode !== 'tui'
      : options.openBrowser;
  if (options.restart) {
    await stopDaemon(home);
  }

  step(4, 4, 'Starting local daemon and UI surfaces');
  let started;
  try {
    started = await startDaemon(home, runtimePython, host, port);
  } catch (error) {
    if (handleCodexPreflightFailure(error)) return true;
    throw error;
  }
  const browserOpened = shouldOpenBrowser ? openBrowser(started.url) : false;
  printLaunchCard({
    url: started.url,
    bindUrl: started.bindUrl,
    mode,
    autoOpenRequested: shouldOpenBrowser,
    browserOpened,
    daemonOnly: options.daemonOnly,
    home,
    pythonSelection: pythonRuntime.runtimeProbe,
  });

  if (options.daemonOnly) {
    process.exit(0);
  }
  if (mode === 'web') {
    process.exit(0);
  }
  launchTui(started.url, options.questId, home, runtimePython);
  return true;
}

async function main() {
  const args = process.argv.slice(2);
  const positional = findFirstPositionalArg(args);
  if (positional && positional.value === 'update') {
    await updateMain(args);
    return;
  }
  if (positional && positional.value === 'migrate') {
    await migrateMain(args);
    return;
  }
  if (args.length === 0 || args[0] === 'ui' || (!positional && args[0]?.startsWith('--'))) {
    await launcherMain(args);
    return;
  }
  if (args[0] === '--help' || args[0] === '-h') {
    printLauncherHelp();
    return;
  }
  if (positional && pythonCommands.has(positional.value)) {
    const home = resolveHome(args);
    const pythonRuntime = ensurePythonRuntime(home);
    const runtimePython = pythonRuntime.runtimePython;
    if (positional.value === 'run' || positional.value === 'daemon') {
      maybePrintOptionalLatexNotice(home);
    }
    if (positional.value === 'run' || positional.value === 'daemon') {
      const bootstrapState = readCodexBootstrapState(home, runtimePython);
      if (!bootstrapState.codex_ready) {
        try {
          const probe = probeCodexBootstrap(home, runtimePython);
          if (!probe || probe.ok !== true) {
            throw createCodexPreflightError(home, probe);
          }
        } catch (error) {
          if (handleCodexPreflightFailure(error)) return;
          throw error;
        }
      }
    }
    const result = runPythonCli(runtimePython, normalizePythonCliArgs(args, home), { allowFailure: true });
    process.exit(result.status ?? 0);
    return;
  }
  await launcherMain(args);
}

module.exports = {
  __internal: {
    minimumPythonRequest,
    createPythonRuntimePlan,
    buildUvRuntimeEnv,
    runtimePythonEnvPath,
    runtimePythonPath,
    runtimeUvBinaryPath,
    legacyVenvRootPath,
    resolveUvBinary,
    resolveHome,
    parseMigrateArgs,
    useEditableProjectInstall,
    compareVersions,
    detectInstallMode,
    buildUpdateStatus,
  },
};

if (require.main === module) {
  main().catch((error) => {
    console.error(error instanceof Error ? error.message : String(error));
    process.exit(1);
  });
}
