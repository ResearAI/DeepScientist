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
  'distill-quest',
]);
const UPDATE_PACKAGE_NAME = String(packageJson.name || '@researai/deepscientist').trim() || '@researai/deepscientist';
const UPDATE_CHECK_TTL_MS = 12 * 60 * 60 * 1000;

const optionsWithValues = new Set(['--home', '--host', '--port', '--quest-id', '--mode', '--proxy', '--codex-profile', '--codex', '--auth', '--runner']);

function buildCodexOverrideEnv({ yolo = true, profile = null, binary = null, runner = null } = {}) {
  const normalizedProfile = typeof profile === 'string' ? profile.trim() : '';
  const normalizedBinary = typeof binary === 'string' ? binary.trim() : '';
  const normalizedRunner = typeof runner === 'string' ? runner.trim().toLowerCase() : '';
  const overrides = {};
  if (normalizedRunner) {
    overrides.DEEPSCIENTIST_DEFAULT_RUNNER = normalizedRunner;
  }
  if (normalizedBinary) {
    overrides.DEEPSCIENTIST_CODEX_BINARY = normalizedBinary;
  }
  overrides.DEEPSCIENTIST_CODEX_YOLO = yolo ? '1' : '0';
  if (!yolo) {
    if (normalizedProfile) {
      overrides.DEEPSCIENTIST_CODEX_PROFILE = normalizedProfile;
      overrides.DEEPSCIENTIST_CODEX_MODEL = 'inherit';
    }
    return overrides;
  }
  if (normalizedProfile) {
    overrides.DEEPSCIENTIST_CODEX_PROFILE = normalizedProfile;
    overrides.DEEPSCIENTIST_CODEX_MODEL = 'inherit';
  }
  return overrides;
}

function readOptionValue(argv, optionName) {
  for (let index = 0; index < argv.length; index += 1) {
    if (argv[index] === optionName && argv[index + 1]) {
      return argv[index + 1];
    }
  }
  return null;
}

function parseBooleanFlagValue(rawValue) {
  const normalized = String(rawValue || '').trim().toLowerCase();
  if (!normalized) return null;
  if (['1', 'true', 'yes', 'on', 'y'].includes(normalized)) return true;
  if (['0', 'false', 'no', 'off', 'n'].includes(normalized)) return false;
  return null;
}

function parseCodexCliVersion(text) {
  const match = String(text || '').match(/codex-cli\s+(\d+)\.(\d+)\.(\d+)/i);
  if (!match) {
    return null;
  }
  return [Number(match[1]), Number(match[2]), Number(match[3])];
}

function formatCodexCliVersion(version) {
  if (!Array.isArray(version) || version.length !== 3) {
    return '';
  }
  return version.join('.');
}

function compareCodexCliVersion(left, right) {
  const leftParts = Array.isArray(left) ? left : [0, 0, 0];
  const rightParts = Array.isArray(right) ? right : [0, 0, 0];
  for (let index = 0; index < 3; index += 1) {
    const delta = Number(leftParts[index] || 0) - Number(rightParts[index] || 0);
    if (delta !== 0) {
      return delta;
    }
  }
  return 0;
}

function parseYoloArg(args, index, currentValue = true) {
  const arg = args[index];
  if (arg === '--yolo') {
    const parsed = parseBooleanFlagValue(args[index + 1]);
    if (parsed === null) {
      return { matched: true, value: true, consumed: 1 };
    }
    return { matched: true, value: parsed, consumed: 2 };
  }
  if (typeof arg === 'string' && arg.startsWith('--yolo=')) {
    const parsed = parseBooleanFlagValue(arg.slice('--yolo='.length));
    return { matched: true, value: parsed === null ? true : parsed, consumed: 1 };
  }
  return { matched: false, value: currentValue, consumed: 0 };
}

function resolveYoloFlag(args, defaultValue = true) {
  let value = defaultValue;
  for (let index = 0; index < args.length; index += 1) {
    const parsed = parseYoloArg(args, index, value);
    if (!parsed.matched) continue;
    value = parsed.value;
    index += Math.max(0, parsed.consumed - 1);
  }
  return value;
}

function printLauncherHelp() {
  console.log(`DeepScientist launcher

Usage:
  ds
  ds update
  ds update --check
  ds update --yes
  ds uninstall
  ds migrate /data/DeepScientist
  ds --here
  ds --yolo --port 20999 --here
  ds --here doctor
  ds --tui
  ds --both
  ds --host 0.0.0.0 --port 21000
  ds --host 0.0.0.0 --port 21000 --proxy http://127.0.0.1:58887
  ds --stop
  ds --restart
  ds --status
  ds doctor
  ds --runner claude
  ds latex status
  ds --home ~/DeepScientist --port 20999

Launcher flags:
  --host <host>         Bind host for the local web daemon
  --port <port>         Bind port for the local web daemon
  --auth [true|false]   Require a 16-character local browser password. Default is false
  --tui                 Start the terminal workspace only
  --both                Start web + terminal workspace together
  --no-browser          Do not auto-open the browser
  --daemon-only         Start the managed daemon and exit
  --status              Print managed daemon health as JSON
  --stop                Stop the managed daemon
  --restart             Restart the managed daemon
  --home <path>         Use a custom DeepScientist home
  --here                Create/use ./DeepScientist under the current working directory as home
  --proxy <url>         Use an outbound HTTP/WS proxy for npm and Python runtime traffic
  --yolo [true|false]   Control Codex YOLO mode. Default is true; pass false to restore on-request + workspace-write
  --runner <name>      Select builtin runner for this launch: codex, claude, or opencode
  --codex-profile <id>  Run DeepScientist with a specific Codex profile, for example \`m27\`
  --codex <path>        Run DeepScientist with a specific Codex executable path for this launch
  --quest-id <id>       Open the TUI on one quest directly

Update:
  ds update             Check the npm package version and offer update actions
  ds update --check     Print structured update status
  ds update --yes       Install the latest npm release immediately

Migration:
  ds migrate <target>   Move the DeepScientist home/install root to a new absolute path
  ds migrate <target> --yes --restart

Uninstall:
  ds uninstall          Remove code/runtime only and preserve local data

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

function normalizeProxyUrl(rawValue) {
  const value = String(rawValue || '').trim();
  return value || null;
}

function normalizeLegacyHostFlagArgs(argv) {
  const args = [];
  let warned = false;
  let legacyValue = null;

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === '--ip') {
      warned = true;
      legacyValue = argv[index + 1] || legacyValue;
      args.push('--host');
      if (argv[index + 1]) {
        args.push(argv[index + 1]);
        index += 1;
      }
      continue;
    }
    if (typeof arg === 'string' && arg.startsWith('--ip=')) {
      warned = true;
      legacyValue = arg.slice('--ip='.length) || legacyValue;
      args.push('--host', arg.slice('--ip='.length));
      continue;
    }
    args.push(arg);
  }

  if (!warned) {
    return { args, warnings: [] };
  }

  const normalizedValue = String(legacyValue || '').trim();
  const bindHint =
    normalizedValue && ['0.0.0.0', '::', '[::]'].includes(normalizedValue)
      ? ' Note: bind-all addresses such as 0.0.0.0 are valid for `--host`, but local browser access still uses 127.0.0.1.'
      : '';
  return {
    args,
    warnings: [`Launcher note: \`--ip\` is deprecated. Use \`--host\` instead.${bindHint}`],
  };
}

function applyLauncherProxy(proxyUrl) {
  const normalized = normalizeProxyUrl(proxyUrl);
  if (!normalized) {
    return null;
  }
  for (const key of ['HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy']) {
    process.env[key] = normalized;
  }
  for (const key of ['NO_PROXY', 'no_proxy']) {
    const current = String(process.env[key] || '').trim();
    const values = current
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean);
    for (const host of ['127.0.0.1', 'localhost', '::1', '0.0.0.0']) {
      if (!values.includes(host)) {
        values.push(host);
      }
    }
    process.env[key] = values.join(',');
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

function hasActiveBusyUpdate(state, currentVersion) {
  if (!state || !state.busy) {
    return false;
  }
  const targetVersion = normalizeVersion(state.target_version || state.latest_version || '');
  if (!targetVersion) {
    return false;
  }
  return compareVersions(targetVersion, currentVersion) > 0;
}

function detectInstallMode(rootPath = repoRoot) {
  const normalized = String(rootPath || '');
  return normalized.includes(`${path.sep}node_modules${path.sep}`) ? 'npm-package' : 'source-checkout';
}

function updateManualCommand(installMode) {
  return `npm install -g ${UPDATE_PACKAGE_NAME}@latest`;
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
      reason: 'Self-update is disabled for this installation. Use the npm command below to install the latest release build.',
    };
  }
  if (!launcherPath || !fs.existsSync(launcherPath)) {
    return {
      canCheck: true,
      canSelfUpdate: false,
      reason: 'Self-update is disabled because the launcher entrypoint could not be resolved. Use the npm command below instead.',
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
  const result = spawnSync(npmBinary, ['view', UPDATE_PACKAGE_NAME, 'version', '--json'], syncSpawnOptions({
    encoding: 'utf8',
    env: process.env,
    timeout: timeoutMs,
  }));
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
  const targetVersion = normalizeVersion(state.target_version || '');
  const busy = hasActiveBusyUpdate(state, currentVersion);
  const promptedVersion = normalizeVersion(state.last_prompted_version || '');
  const updateAvailable = Boolean(latestVersion) && compareVersions(latestVersion, currentVersion) > 0;
  const skippedVersion = normalizeVersion(state.last_skipped_version || '');
  const promptedCurrentTarget = Boolean(updateAvailable && promptedVersion && promptedVersion === latestVersion);
  const skippedCurrentTarget = Boolean(updateAvailable && skippedVersion && skippedVersion === latestVersion);
  const promptRecommended =
    Boolean(updateAvailable)
    && !busy
    && !promptedCurrentTarget
    && !skippedCurrentTarget
    ;

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
    busy,
    last_checked_at: state.last_checked_at || null,
    last_check_error: state.last_check_error || null,
    last_prompted_at: state.last_prompted_at || null,
    last_prompted_version: promptedVersion || null,
    last_deferred_at: state.last_deferred_at || null,
    last_skipped_version: skippedVersion || null,
    last_update_started_at: state.last_update_started_at || null,
    last_update_finished_at: state.last_update_finished_at || null,
    last_update_result: state.last_update_result || null,
    target_version: busy ? targetVersion || latestVersion || null : null,
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
  const existingBusyIsStale = Boolean(existing.busy) && !hasActiveBusyUpdate(existing, currentVersion);

  if (!force && existing.current_version === currentVersion && !isExpired(existing.last_checked_at, UPDATE_CHECK_TTL_MS)) {
    if (existingBusyIsStale) {
      const repaired = mergeUpdateState(home, {
        busy: false,
        target_version: null,
      });
      return buildUpdateStatus(home, repaired);
    }
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
  if (Boolean(patched.busy) && !hasActiveBusyUpdate(patched, currentVersion)) {
    const repaired = mergeUpdateState(home, {
      busy: false,
      target_version: null,
    });
    return buildUpdateStatus(home, repaired);
  }
  return buildUpdateStatus(home, patched);
}

function markUpdateDeferred(home, version) {
  const normalizedVersion = normalizeVersion(version || readUpdateState(home).latest_version || '');
  const patched = mergeUpdateState(home, {
    last_prompted_at: new Date().toISOString(),
    last_deferred_at: new Date().toISOString(),
    last_prompted_version: normalizedVersion || null,
    latest_version: normalizedVersion || null,
  });
  return buildUpdateStatus(home, patched);
}

function markUpdateSkipped(home, version) {
  const normalized = normalizeVersion(version);
  const patched = mergeUpdateState(home, {
    last_prompted_at: new Date().toISOString(),
    last_prompted_version: normalized || null,
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
  if (args.includes('--here')) {
    return path.join(process.cwd(), 'DeepScientist');
  }
  if (process.env.DEEPSCIENTIST_HOME) {
    return path.resolve(process.env.DEEPSCIENTIST_HOME);
  }
  if (process.env.DS_HOME) {
    return path.resolve(process.env.DS_HOME);
  }
  return path.join(os.homedir(), 'DeepScientist');
}

function hasManagedDaemonState(home) {
  const state = readDaemonState(home);
  return Boolean(
    state
    && typeof state === 'object'
    && (
      state.daemon_id
      || state.pid
      || state.url
      || state.launch_url
      || state.home
    )
  );
}

function resolveManagementHome(rawArgs, options = {}) {
  if (
    options.home
    || rawArgs.includes('--here')
    || process.env.DEEPSCIENTIST_HOME
    || process.env.DS_HOME
  ) {
    return options.home || resolveHome(rawArgs);
  }

  const cwdHome = normalizeHomePath(path.join(process.cwd(), 'DeepScientist'));
  if (hasManagedDaemonState(cwdHome)) {
    return cwdHome;
  }

  const defaultHome = normalizeHomePath(resolveHome(rawArgs));
  if (hasManagedDaemonState(defaultHome)) {
    return defaultHome;
  }

  const installs = readInstallIndex()
    .installs
    .map((item) => normalizeInstallRecord(item))
    .filter(Boolean);
  const indexedHomes = [...new Set(installs.map((item) => item.home).filter(Boolean))];
  const managedHomes = indexedHomes.filter((home) => hasManagedDaemonState(home));
  if (managedHomes.length === 1) {
    return managedHomes[0];
  }

  return defaultHome;
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

function generateBrowserAuthToken() {
  return crypto.randomBytes(8).toString('hex');
}

function appendBrowserAuthToken(url, authToken) {
  const normalized = typeof authToken === 'string' ? authToken.trim() : '';
  if (!normalized) {
    return url;
  }
  const target = new URL(url);
  target.searchParams.set('token', normalized);
  return target.toString();
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

function shouldCompileRuntimeBytecode() {
  return parseBooleanSetting(process.env.DEEPSCIENTIST_RUNTIME_COMPILE_BYTECODE, false);
}

function readRequiredOptionValue(args, index, optionName) {
  const value = args[index + 1];
  if (!value || String(value).startsWith('--')) {
    return {
      ok: false,
      error: `Missing value for ${optionName}.`,
    };
  }
  return {
    ok: true,
    value,
  };
}

function parseStrictBooleanOption(rawValue, optionName) {
  const parsed = parseBooleanFlagValue(rawValue);
  if (parsed === null) {
    return {
      ok: false,
      error: `Invalid value for ${optionName}: ${rawValue}. Use true or false.`,
    };
  }
  return {
    ok: true,
    value: parsed,
  };
}

function parseStrictPortOption(rawValue, optionName) {
  const port = Number(rawValue);
  if (!Number.isInteger(port) || port <= 0 || port > 65535) {
    return {
      ok: false,
      error: `Invalid value for ${optionName}: ${rawValue}. Expected an integer between 1 and 65535.`,
    };
  }
  return {
    ok: true,
    value: port,
  };
}

function parseStrictModeOption(rawValue, optionName) {
  const normalized = String(rawValue || '').trim().toLowerCase();
  if (!['web', 'tui', 'both'].includes(normalized)) {
    return {
      ok: false,
      error: `Invalid value for ${optionName}: ${rawValue}. Expected one of: web, tui, both.`,
    };
  }
  return {
    ok: true,
    value: normalized,
  };
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

function readCodexProviderMetadata(configDir, profile) {
  const normalizedProfile = String(profile || '').trim();
  const expandedDir = expandUserPath(configDir || path.join(os.homedir(), '.codex'));
  const configPath = path.join(expandedDir, 'config.toml');
  if (!normalizedProfile || !fs.existsSync(configPath)) {
    return {
      provider: null,
      model: null,
      envKey: null,
      baseUrl: null,
      wireApi: null,
      requiresOpenAiAuth: null,
    };
  }
  const text = fs.readFileSync(configPath, 'utf8');
  const profileBlock = text.match(new RegExp(`\\[profiles\\.${normalizedProfile.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\$&')}\\]([\\s\\S]*?)(?:\\n\\[|$)`));
  const provider = profileBlock?.[1]?.match(/^\s*model_provider\s*=\s*["']([^"']+)["']/m)?.[1]?.trim() || text.match(/^\s*model_provider\s*=\s*["']([^"']+)["']/m)?.[1]?.trim() || null;
  const model = profileBlock?.[1]?.match(/^\s*model\s*=\s*["']([^"']+)["']/m)?.[1]?.trim() || text.match(/^\s*model\s*=\s*["']([^"']+)["']/m)?.[1]?.trim() || null;
  if (!provider) {
    return {
      provider: null,
      model,
      envKey: null,
      baseUrl: null,
      wireApi: null,
      requiresOpenAiAuth: null,
    };
  }
  const providerBlock = text.match(new RegExp(`\\[model_providers\\.${provider.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\$&')}\\]([\\s\\S]*?)(?:\\n\\[|$)`));
  const providerText = providerBlock?.[1] || '';
  const envKey = providerText.match(/^\s*env_key\s*=\s*["']([^"']+)["']/m)?.[1]?.trim() || null;
  const baseUrl = providerText.match(/^\s*base_url\s*=\s*["']([^"']+)["']/m)?.[1]?.trim() || null;
  const wireApi = providerText.match(/^\s*wire_api\s*=\s*["']([^"']+)["']/m)?.[1]?.trim() || null;
  const requiresOpenAiAuthRaw = providerText.match(/^\s*requires_openai_auth\s*=\s*(true|false)\s*$/m)?.[1] || null;
  const requiresOpenAiAuth = requiresOpenAiAuthRaw === null ? null : requiresOpenAiAuthRaw === 'true';
  return {
    provider,
    model,
    envKey,
    baseUrl,
    wireApi,
    requiresOpenAiAuth,
  };
}

function installedCodexCliVersion(binaryPath) {
  const resolved = resolveExecutableOnPath(binaryPath || 'codex') || binaryPath || 'codex';
  try {
    const result = spawnSync(resolved, ['--version'], syncSpawnOptions({ encoding: 'utf8' }));
    if (result.status !== 0) {
      return null;
    }
    return parseCodexCliVersion(`${result.stdout || ''}\n${result.stderr || ''}`);
  } catch {
    return null;
  }
}

const OFFICIAL_REPOSITORY_URL = 'https://github.com/ResearAI/DeepScientist';

function officialRepositoryLine() {
  return `Official open-source repository: ${hyperlink(OFFICIAL_REPOSITORY_URL, OFFICIAL_REPOSITORY_URL)}`;
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
      syncSpawnOptions({ encoding: 'utf8' })
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

function renderLaunchHints({ home, url, bindUrl, pythonSelection, yolo, authEnabled, authToken }) {
  const runtimeRows = [
    ['Version', packageJson.version],
    ['Home', truncateMiddle(home)],
    ['Browser URL', url],
    ['Bind URL', bindUrl],
    ['Python', truncateMiddle(pythonVersionText(pythonSelection))],
    ['Codex mode', yolo ? 'YOLO (never + danger-full-access)' : 'Default (on-request + workspace-write)'],
  ];
  if (authEnabled && authToken) {
    runtimeRows.splice(4, 0, ['Auth token', authToken]);
  }
  if (pythonSelection && pythonSelection.sourceLabel) {
    runtimeRows.push(['Python source', pythonSelection.sourceLabel]);
  }
  console.log(colorize('\u001B[1;38;5;39m', 'Runtime'));
  renderKeyValueRows(runtimeRows);
  console.log('');

  console.log(colorize('\u001B[1;38;5;39m', 'Quick Flags'));
  renderKeyValueRows([
    ['ds --yolo --port 20999 --here', 'Start in ./DeepScientist under the current directory with YOLO Codex access'],
    ['ds --port 21000', 'Change the web port'],
    ['ds --host 0.0.0.0 --port 21000', 'Bind on all interfaces'],
    ['ds --auth true', 'Enable the local browser password for this launch'],
    ['ds --here', 'Use ./DeepScientist under the current directory as home'],
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
  yolo,
  authEnabled,
  authToken,
}) {
  const width = Math.max(72, Math.min(process.stdout.columns || 100, 108));
  const divider = colorize('\u001B[38;5;245m', '─'.repeat(Math.max(36, width - 6)));
  const title = colorize('\u001B[1;38;5;39m', 'ResearAI');
  const subtitleLines = [
    colorize('\u001B[38;5;110m', 'DeepScientist is not just a fully open-source autonomous scientific discovery system.'),
    colorize('\u001B[38;5;110m', 'It is also a research map that keeps growing from every round.'),
  ];
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
  for (const line of subtitleLines) {
    console.log(centerText(line, width));
  }
  console.log('');
  console.log(centerText(divider, width));
  console.log(centerText(colorize('\u001B[1m', workspaceMode), width));
  console.log(centerText(urlLabel, width));
  console.log(centerText(divider, width));
  if (authEnabled && authToken) {
    console.log('');
    console.log(centerText(colorize('\u001B[1;38;5;214m', authToken), width));
    console.log('');
  }
  console.log(centerText(browserLine, width));
  console.log(centerText(nextStep, width));
  console.log(centerText('Run ds --stop to stop the managed daemon.', width));
  console.log(centerText('Need to move this installation later? Use ds migrate /new/path.', width));
  console.log(centerText(officialRepositoryLine(), width));
  console.log('');
  renderLaunchHints({ home, url, bindUrl, pythonSelection, yolo, authEnabled, authToken });
}

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function writeRunnerPreflightReport(home, runnerName, probe) {
  const reportDir = path.join(home, 'runtime', 'preflight');
  ensureDir(reportDir);
  const reportPath = path.join(reportDir, `${String(runnerName || 'runner').trim().toLowerCase() || 'runner'}-preflight.html`);
  const warnings = Array.isArray(probe?.warnings) ? probe.warnings : [];
  const errors = Array.isArray(probe?.errors) ? probe.errors : [];
  const guidance = Array.isArray(probe?.guidance) ? probe.guidance : [];
  const details = probe && typeof probe.details === 'object' ? probe.details : {};
  const profile = typeof details.profile === 'string' ? details.profile.trim() : '';
  const intro = profile
    ? `DeepScientist blocked startup because the Codex hello probe did not pass for profile \`${profile}\`. Verify that \`codex --profile ${profile}\` works on this machine and that the profile's provider-specific API key, Base URL, and model configuration are already set up.`
    : 'DeepScientist blocked startup because the Codex hello probe did not pass. In most installs, `npm install -g @researai/deepscientist` also installs the bundled Codex dependency. If `codex` is still missing, repair it with `npm install -g @openai/codex`. Then run `codex login` (or just `codex`), finish authentication, run `ds doctor`, and launch `ds` again.';
  const introZh = profile
    ? `DeepScientist 启动前进行了 Codex 可用性检查，但 profile \`${profile}\` 的 hello 探测没有通过。请先确认 \`codex --profile ${profile}\` 在当前机器上可以正常启动，并确保该 profile 依赖的 provider API Key、Base URL 和模型配置都已经在 Codex 中配置好。`
    : 'DeepScientist 启动前进行了 Codex 可用性检查，但 hello 探测没有通过。正常情况下，`npm install -g @researai/deepscientist` 也会一并安装 bundled Codex 依赖；如果此后 `codex` 仍不可用，请再执行 `npm install -g @openai/codex` 修复。然后运行 `codex login`（或直接运行 `codex`）完成认证，再执行 `ds doctor`，最后重新启动 `ds`。';
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
    <title>DeepScientist runner check failed</title>
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
        <h1>DeepScientist could not start the selected runner</h1>
        <p class="meta">${escapeHtml(intro)}</p>
        <p class="meta">${escapeHtml(introZh)}</p>

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
            <dt>Profile</dt>
            <dd>${escapeHtml(details.profile || '')}</dd>
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


function readConfiguredDefaultRunner(home, fallback = 'codex') {
  const configPath = path.join(home, 'config', 'config.yaml');
  if (!fs.existsSync(configPath)) {
    return fallback;
  }
  try {
    const text = fs.readFileSync(configPath, 'utf8');
    const match = text.match(new RegExp("^\\s*default_runner:\\s*[\"']?([^\"'\\n]+)[\"']?\\s*$", "m"));
    const value = match ? String(match[1] || '').trim().toLowerCase() : '';
    return value || fallback;
  } catch {
    return fallback;
  }
}

function readRunnerBootstrapState(home, runtimePython, runnerName, envOverrides = {}) {
  const snippet = [
    'import json, pathlib, sys',
    'from deepscientist.config import ConfigManager',
    'home = pathlib.Path(sys.argv[1])',
    'runner = str(sys.argv[2])',
    'manager = ConfigManager(home)',
    'print(json.dumps(manager.runner_bootstrap_state(runner), ensure_ascii=False))',
  ].join('\n');
  const result = runSync(runtimePython, ['-c', snippet, home, runnerName], {
    capture: true,
    allowFailure: true,
    env: {
      ...process.env,
      ...envOverrides,
    },
  });
  if (result.status !== 0) {
    return { runner: runnerName, ready: false, last_checked_at: null, last_result: {} };
  }
  try {
    return JSON.parse(result.stdout || '{}');
  } catch {
    return { runner: runnerName, ready: false, last_checked_at: null, last_result: {} };
  }
}

function probeRunnerBootstrap(home, runtimePython, runnerName, envOverrides = {}) {
  const snippet = [
    'import json, pathlib, sys',
    'from deepscientist.config import ConfigManager',
    'home = pathlib.Path(sys.argv[1])',
    'runner = str(sys.argv[2])',
    'manager = ConfigManager(home)',
    'print(json.dumps(manager.probe_runner_bootstrap(runner, persist=True), ensure_ascii=False))',
  ].join('\n');
  const result = runSync(runtimePython, ['-c', snippet, home, runnerName], {
    capture: true,
    allowFailure: true,
    env: {
      ...process.env,
      ...envOverrides,
    },
  });
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
    summary: `${runnerName} startup probe crashed before a structured result was returned.`,
    warnings: [],
    errors: [result.stderr || 'Unable to parse the startup probe result.'],
    details: {
      runner: runnerName,
      exit_code: result.status ?? null,
      stdout_excerpt: result.stdout || '',
      stderr_excerpt: result.stderr || '',
    },
    guidance: [
      `Run \`${runnerName}\` manually and complete any required setup.`,
      'Then start DeepScientist again.',
    ],
  };
}

function readEnabledRunnerNames(home, runtimePython, envOverrides = {}) {
  const snippet = [
    'import json, pathlib, sys',
    'from deepscientist.config import ConfigManager',
    'home = pathlib.Path(sys.argv[1])',
    'manager = ConfigManager(home)',
    'payload = manager.load_runners_config()',
    'print(json.dumps(sorted(name for name, cfg in payload.items() if isinstance(cfg, dict) and bool(cfg.get("enabled", False))), ensure_ascii=False))',
  ].join('\n');
  const result = runSync(runtimePython, ['-c', snippet, home], {
    capture: true,
    allowFailure: true,
    env: {
      ...process.env,
      ...envOverrides,
    },
  });
  if (result.status !== 0) {
    return [];
  }
  try {
    const parsed = JSON.parse(result.stdout || '[]');
    return Array.isArray(parsed) ? parsed.map((item) => String(item || '').trim().toLowerCase()).filter(Boolean) : [];
  } catch {
    return [];
  }
}

function readRunnerReadyState(home, runtimePython, runnerName, envOverrides = {}) {
  if (String(runnerName || '').trim().toLowerCase() === 'codex') {
    const state = readCodexBootstrapState(home, runtimePython, envOverrides);
    return { ready: Boolean(state.codex_ready), state };
  }
  const state = readRunnerBootstrapState(home, runtimePython, runnerName, envOverrides);
  return { ready: Boolean(state.ready), state };
}

function probeRunnerReady(home, runtimePython, runnerName, envOverrides = {}) {
  if (String(runnerName || '').trim().toLowerCase() === 'codex') {
    return probeCodexBootstrap(home, runtimePython, envOverrides);
  }
  return probeRunnerBootstrap(home, runtimePython, runnerName, envOverrides);
}

function resolveStartupRunner(home, runtimePython, preferredRunner, envOverrides = {}) {
  const normalizedPreferred = String(preferredRunner || 'codex').trim().toLowerCase() || 'codex';
  const enabled = readEnabledRunnerNames(home, runtimePython, envOverrides);
  const ordered = [
    normalizedPreferred,
    ...enabled.filter((name) => name !== normalizedPreferred),
  ];
  const seen = new Set();
  const candidates = ordered.filter((name) => {
    if (!name || seen.has(name)) return false;
    seen.add(name);
    return true;
  });

  let preferredProbe = null;
  for (const runnerName of candidates) {
    const bootstrap = readRunnerReadyState(home, runtimePython, runnerName, envOverrides);
    if (bootstrap.ready) {
      return { ok: true, runnerName, preferredRunner: normalizedPreferred, fallback: runnerName !== normalizedPreferred, probe: null };
    }
    const probe = probeRunnerReady(home, runtimePython, runnerName, envOverrides);
    if (runnerName === normalizedPreferred) {
      preferredProbe = probe;
    }
    if (probe && probe.ok === true) {
      return { ok: true, runnerName, preferredRunner: normalizedPreferred, fallback: runnerName !== normalizedPreferred, probe };
    }
  }
  return { ok: false, runnerName: normalizedPreferred, preferredRunner: normalizedPreferred, fallback: false, probe: preferredProbe };
}

function readCodexBootstrapState(home, runtimePython, envOverrides = {}) {
  const snippet = [
    'import json, pathlib, sys',
    'from deepscientist.config import ConfigManager',
    'home = pathlib.Path(sys.argv[1])',
    'manager = ConfigManager(home)',
    'print(json.dumps(manager.codex_bootstrap_state(), ensure_ascii=False))',
  ].join('\n');
  const result = runSync(runtimePython, ['-c', snippet, home], {
    capture: true,
    allowFailure: true,
    env: {
      ...process.env,
      ...envOverrides,
    },
  });
  if (result.status !== 0) {
    return { codex_ready: false, codex_last_checked_at: null, codex_last_result: {} };
  }
  try {
    return JSON.parse(result.stdout || '{}');
  } catch {
    return { codex_ready: false, codex_last_checked_at: null, codex_last_result: {} };
  }
}

function probeCodexBootstrap(home, runtimePython, envOverrides = {}) {
  const snippet = [
    'import json, pathlib, sys',
    'from deepscientist.config import ConfigManager',
    'home = pathlib.Path(sys.argv[1])',
    'manager = ConfigManager(home)',
    'print(json.dumps(manager.probe_codex_bootstrap(persist=True), ensure_ascii=False))',
  ].join('\n');
  const result = runSync(runtimePython, ['-c', snippet, home], {
    capture: true,
    allowFailure: true,
    env: {
      ...process.env,
      ...envOverrides,
    },
  });
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

function createRunnerPreflightError(home, runnerName, probe) {
  const report = writeRunnerPreflightReport(home, runnerName, probe);
  const normalizedRunner = String(runnerName || 'codex').trim().toLowerCase() || 'codex';
  const error = new Error(probe?.summary || `${normalizedRunner} startup probe failed.`);
  error.code = 'DS_RUNNER_PREFLIGHT';
  error.runnerName = normalizedRunner;
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
  let proxy = null;
  let stop = false;
  let restart = false;
  let openBrowser = null;
  let questId = null;
  let status = false;
  let daemonOnly = false;
  let skipUpdateCheck = false;
  let yolo = true;
  let auth = null;
  let codexProfile = null;
  let codexBinary = null;
  let runner = null;

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
    else if (arg === '--here') continue;
    else {
      const parsedYolo = parseYoloArg(args, index, yolo);
      if (parsedYolo.matched) {
        yolo = parsedYolo.value;
        index += Math.max(0, parsedYolo.consumed - 1);
      } else if (arg === '--auth') {
        const next = readRequiredOptionValue(args, index, '--auth');
        if (!next.ok) return { help: false, error: next.error };
        const parsed = parseStrictBooleanOption(next.value, '--auth');
        if (!parsed.ok) return { help: false, error: parsed.error };
        auth = parsed.value;
        index += 1;
      } else if (typeof arg === 'string' && arg.startsWith('--auth=')) {
        const parsed = parseStrictBooleanOption(arg.slice('--auth='.length), '--auth');
        if (!parsed.ok) return { help: false, error: parsed.error };
        auth = parsed.value;
      } else if (arg === '--codex-profile') {
        const next = readRequiredOptionValue(args, index, '--codex-profile');
        if (!next.ok) return { help: false, error: next.error };
        codexProfile = next.value;
        index += 1;
      } else if (arg === '--codex') {
        const next = readRequiredOptionValue(args, index, '--codex');
        if (!next.ok) return { help: false, error: next.error };
        codexBinary = next.value;
        index += 1;
      } else if (arg === '--runner') {
        const next = readRequiredOptionValue(args, index, '--runner');
        if (!next.ok) return { help: false, error: next.error };
        runner = next.value;
        index += 1;
      } else if (arg === '--host') {
        const next = readRequiredOptionValue(args, index, '--host');
        if (!next.ok) return { help: false, error: next.error };
        host = next.value;
        index += 1;
      } else if (arg === '--port') {
        const next = readRequiredOptionValue(args, index, '--port');
        if (!next.ok) return { help: false, error: next.error };
        const parsed = parseStrictPortOption(next.value, '--port');
        if (!parsed.ok) return { help: false, error: parsed.error };
        port = parsed.value;
        index += 1;
      } else if (arg === '--home') {
        const next = readRequiredOptionValue(args, index, '--home');
        if (!next.ok) return { help: false, error: next.error };
        home = path.resolve(next.value);
        index += 1;
      } else if (arg === '--proxy') {
        const next = readRequiredOptionValue(args, index, '--proxy');
        if (!next.ok) return { help: false, error: next.error };
        proxy = next.value;
        index += 1;
      } else if (arg === '--quest-id') {
        const next = readRequiredOptionValue(args, index, '--quest-id');
        if (!next.ok) return { help: false, error: next.error };
        questId = next.value;
        index += 1;
      } else if (arg === '--mode') {
        const next = readRequiredOptionValue(args, index, '--mode');
        if (!next.ok) return { help: false, error: next.error };
        const parsed = parseStrictModeOption(next.value, '--mode');
        if (!parsed.ok) return { help: false, error: parsed.error };
        mode = parsed.value;
        index += 1;
      }
      else if (arg === '--help' || arg === '-h') return { help: true };
      else if (arg.startsWith('--')) return { help: false, error: `Unknown launcher flag: ${arg}` };
      else return { help: false, error: `Unexpected launcher argument: ${arg}` };
    }
  }

  return {
    help: false,
    mode,
    host,
    port,
    home,
    proxy,
    stop,
    restart,
    status,
    openBrowser,
    questId,
    daemonOnly,
    skipUpdateCheck,
    yolo,
    auth,
    codexProfile,
    codexBinary,
    runner,
    error: null,
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

Without \`--yes\`, \`ds update\` will ask for a \`Y/N\` confirmation on interactive terminals.
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

function printUninstallHelp() {
  console.log(`DeepScientist uninstall

Usage:
  ds uninstall
  ds uninstall --home /absolute/home/path
  ds uninstall --yes

Behavior:
  - removes DeepScientist code, launcher wrappers, and local runtime code
  - preserves local data such as quests, memory, config, logs, plugins, and cache
  - if this command is run from the globally installed npm package, it also removes the npm package itself

Flags:
  --yes              Skip the interactive confirmation prompt
  --home <path>      Override the target DeepScientist home/root
  --origin <value>   Internal use for npm uninstall integration
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
  let proxy = null;
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
    else if (arg === '--home') {
      const next = readRequiredOptionValue(args, index, '--home');
      if (!next.ok) return { help: false, error: next.error };
      home = path.resolve(next.value);
      index += 1;
    } else if (arg === '--host') {
      const next = readRequiredOptionValue(args, index, '--host');
      if (!next.ok) return { help: false, error: next.error };
      host = next.value;
      index += 1;
    } else if (arg === '--port') {
      const next = readRequiredOptionValue(args, index, '--port');
      if (!next.ok) return { help: false, error: next.error };
      const parsed = parseStrictPortOption(next.value, '--port');
      if (!parsed.ok) return { help: false, error: parsed.error };
      port = parsed.value;
      index += 1;
    } else if (arg === '--proxy') {
      const next = readRequiredOptionValue(args, index, '--proxy');
      if (!next.ok) return { help: false, error: next.error };
      proxy = next.value;
      index += 1;
    }
    else if (arg === '--help' || arg === '-h') return { help: true };
    else if (arg.startsWith('--')) return { help: false, error: `Unknown update flag: ${arg}` };
    else return { help: false, error: `Unexpected update argument: ${arg}` };
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
    proxy,
    restartDaemon,
    skipUpdateCheck,
    error: null,
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
    else if (arg === '--home') {
      const next = readRequiredOptionValue(args, index, '--home');
      if (!next.ok) return { help: false, error: next.error };
      home = path.resolve(expandUserPath(next.value));
      index += 1;
    }
    else if (arg === '--help' || arg === '-h') return { help: true };
    else if (arg.startsWith('--')) return { help: false, error: `Unknown migrate flag: ${arg}` };
    else if (!target) target = path.resolve(expandUserPath(arg));
    else return { help: false, error: `Unexpected migrate argument: ${arg}` };
  }

  if (!target) {
    return {
      help: false,
      error: 'Missing migration target path.',
    };
  }

  return {
    help: false,
    home,
    target,
    yes,
    restart,
    error: null,
  };
}

function parseUninstallArgs(argv) {
  const args = [...argv];
  if (args[0] === 'uninstall') {
    args.shift();
  }
  let home = null;
  let yes = false;
  let origin = null;

  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    if (arg === '--yes') yes = true;
    else if (arg === '--home') {
      const next = readRequiredOptionValue(args, index, '--home');
      if (!next.ok) return { help: false, error: next.error };
      home = path.resolve(expandUserPath(next.value));
      index += 1;
    } else if (arg === '--origin') {
      const next = readRequiredOptionValue(args, index, '--origin');
      if (!next.ok) return { help: false, error: next.error };
      origin = String(next.value || '').trim().toLowerCase() || null;
      index += 1;
    }
    else if (arg === '--help' || arg === '-h') return { help: true };
    else if (arg.startsWith('--')) return { help: false, error: `Unknown uninstall flag: ${arg}` };
    else return { help: false, error: `Unexpected uninstall argument: ${arg}` };
  }

  return {
    help: false,
    home,
    yes,
    origin,
    error: null,
  };
}

function findFirstPositionalArg(args) {
  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    const parsedYolo = parseYoloArg(args, index);
    if (parsedYolo.matched) {
      index += Math.max(0, parsedYolo.consumed - 1);
      continue;
    }
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
    'WRAPPER_PATH="${BASH_SOURCE[0]}"',
    'WRAPPER_DIR="$(cd "$(dirname "$WRAPPER_PATH")" && pwd)"',
    `PREFERRED_COMMAND="${commandName}"`,
    'LOOKUP_PATH=""',
    'OLD_IFS="$IFS"',
    'IFS=:',
    'for ENTRY in $PATH; do',
    '  if [ -z "$ENTRY" ]; then',
    '    continue',
    '  fi',
    '  ENTRY_REAL="$ENTRY"',
    '  if ENTRY_CANONICAL="$(cd "$ENTRY" 2>/dev/null && pwd)"; then',
    '    ENTRY_REAL="$ENTRY_CANONICAL"',
    '  fi',
    '  if [ "$ENTRY_REAL" = "$WRAPPER_DIR" ]; then',
    '    continue',
    '  fi',
    '  if [ -z "$LOOKUP_PATH" ]; then',
    '    LOOKUP_PATH="$ENTRY"',
    '  else',
    '    LOOKUP_PATH="$LOOKUP_PATH:$ENTRY"',
    '  fi',
    'done',
    'IFS="$OLD_IFS"',
    'if [ -n "$LOOKUP_PATH" ]; then',
    '  if RESOLVED_LAUNCHER="$(PATH="$LOOKUP_PATH" command -v "$PREFERRED_COMMAND" 2>/dev/null)"; then',
    '    if [ -n "$RESOLVED_LAUNCHER" ] && [ "$RESOLVED_LAUNCHER" != "$WRAPPER_PATH" ]; then',
    '      if [ -z "${DEEPSCIENTIST_HOME:-}" ]; then',
    `        export DEEPSCIENTIST_HOME="${home}"`,
    '      fi',
    '      exec "$RESOLVED_LAUNCHER" "$@"',
    '    fi',
    '  fi',
    'fi',
    'if [ -z "${DEEPSCIENTIST_HOME:-}" ]; then',
    `  export DEEPSCIENTIST_HOME="${home}"`,
    'fi',
    `exec "${path.join(installDir, 'bin', commandName)}" "$@"`,
    '',
  ].join('\n');
}

function buildLauncherWrapperScript({ launcherPath, home }) {
  return [
    '#!/usr/bin/env bash',
    'set -euo pipefail',
    'if [ -z "${DEEPSCIENTIST_HOME:-}" ]; then',
    `  export DEEPSCIENTIST_HOME="${home}"`,
    'fi',
    `exec "${launcherPath}" "$@"`,
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

function parseLegacyWrapperCandidate(candidatePath) {
  let stat = null;
  try {
    stat = fs.lstatSync(candidatePath);
  } catch {
    return null;
  }

  if (stat.isSymbolicLink()) {
    let resolved = null;
    try {
      resolved = fs.realpathSync(candidatePath);
    } catch {
      return null;
    }
    if (!/[\\/]cli[\\/]bin[\\/](?:ds|ds-cli|research|resear)(?:\.cmd)?$/.test(resolved)) {
      return null;
    }
    return {
      source: 'symlink',
      execPath: resolved,
      home: path.dirname(path.dirname(path.dirname(resolved))),
    };
  }

  if (!stat.isFile()) {
    return null;
  }

  let text = '';
  try {
    text = fs.readFileSync(candidatePath, 'utf8');
  } catch {
    return null;
  }

  const execMatch = text.match(/exec "([^"\n]+[\\/]bin[\\/](?:ds|ds-cli|research|resear))" "\$@"/);
  if (!execMatch) {
    return null;
  }
  const execPath = execMatch[1];
  if (!/[\\/]cli[\\/]bin[\\/](?:ds|ds-cli|research|resear)$/.test(execPath)) {
    return null;
  }
  const homeMatch = text.match(/export DEEPSCIENTIST_HOME="([^"\n]+)"/);
  return {
    source: 'script',
    execPath,
    home: homeMatch ? homeMatch[1] : path.dirname(path.dirname(path.dirname(execPath))),
  };
}

function repairLegacyPathWrappers({ home, launcherPath, force = false }) {
  if (process.platform === 'win32') {
    return [];
  }
  if (!launcherPath || !fs.existsSync(launcherPath)) {
    return [];
  }
  if (!force && detectInstallMode(repoRoot) !== 'npm-package') {
    return [];
  }

  const rewritten = [];
  const seen = new Set();
  for (const commandName of launcherWrapperCommands) {
    for (const candidate of candidateWrapperPathsForCommand(commandName)) {
      if (seen.has(candidate)) {
        continue;
      }
      seen.add(candidate);
      const legacy = parseLegacyWrapperCandidate(candidate);
      if (!legacy) {
        continue;
      }
      writeExecutableScript(
        candidate,
        buildLauncherWrapperScript({
          launcherPath,
          home: legacy.home || home,
        })
      );
      rewritten.push(candidate);
    }
  }
  return rewritten;
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
  const child = spawn(
    process.execPath,
    ['-e', helperScript, String(process.pid), sourceHome, logPath],
    detachedSpawnOptions({
      stdio: 'ignore',
      env: process.env,
    })
  );
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
  const result = spawnSync(binary, ['-c', snippet], syncSpawnOptions({
    encoding: 'utf8',
    env: process.env,
  }));
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
    windowsHide: process.platform === 'win32',
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

function detachedSpawnOptions(options = {}) {
  return {
    ...options,
    detached: true,
    windowsHide: process.platform === 'win32',
  };
}

function syncSpawnOptions(options = {}) {
  return {
    ...options,
    windowsHide: process.platform === 'win32',
  };
}

function verifyPythonRuntime(runtimePython) {
  const result = runSync(
    runtimePython,
    ['-c', 'import deepscientist.cli; import cryptography; import _cffi_backend; print("ok")'],
    { capture: true, allowFailure: true }
  );
  if (result.status !== 0 && result.stderr) {
    process.stderr.write(result.stderr);
  }
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
  const result = spawnSync(process.execPath, ['-e', downloader, url, destinationPath, '45000'], syncSpawnOptions({
    cwd: repoRoot,
    stdio: 'inherit',
    env: process.env,
  }));
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

  const installResult = spawnSync(shellBinary, shellArgs, syncSpawnOptions({
    cwd: repoRoot,
    stdio: 'inherit',
    env: installEnv,
  }));
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
  const env = {
    ...process.env,
    UV_CACHE_DIR: runtimeUvCachePath(home),
    UV_PROJECT_ENVIRONMENT: runtimePythonEnvPath(home),
    UV_PYTHON_INSTALL_DIR: runtimeUvPythonInstallPath(home),
    ...extraEnv,
  };
  for (const key of ['PYTHONPATH', 'PYTHONHOME', 'VIRTUAL_ENV', '__PYVENV_LAUNCHER__']) {
    delete env[key];
  }
  for (const key of Object.keys(env)) {
    if (key === 'CONDA_EXE' || key === 'CONDA_PYTHON_EXE' || key === '_CE_CONDA' || key === '_CE_M') {
      delete env[key];
      continue;
    }
    if (key === 'MAMBA_EXE' || key === 'MAMBA_ROOT_PREFIX') {
      delete env[key];
      continue;
    }
    if (key === 'CONDA_PREFIX' || key === 'CONDA_DEFAULT_ENV' || key === 'CONDA_PROMPT_MODIFIER' || key === 'CONDA_SHLVL') {
      delete env[key];
      continue;
    }
    if (/^CONDA_PREFIX_\d+$/.test(key)) {
      delete env[key];
    }
  }
  return env;
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

function buildUvSyncFailureGuidance({ installMode = detectInstallMode(repoRoot), env = process.env } = {}) {
  const guidance = [];
  if (installMode === 'source-checkout') {
    guidance.push('If you changed Python dependencies in a source checkout, run `uv lock` and try again.');
  } else {
    guidance.push('This npm install already includes a locked `uv.lock`, so this is usually a local Python or network environment issue rather than a missing lockfile.');
    guidance.push('Re-run `ds` in a clean shell first. If you have an active conda or virtualenv, try deactivating it before starting DeepScientist.');
  }

  const hasPythonEnv =
    Boolean(String(env.VIRTUAL_ENV || '').trim())
    || Boolean(String(env.CONDA_PREFIX || '').trim())
    || Boolean(String(env.PYTHONPATH || '').trim())
    || Boolean(String(env.PYTHONHOME || '').trim());
  if (hasPythonEnv) {
    guidance.push('An active Python environment was detected. `VIRTUAL_ENV`, `CONDA_PREFIX`, `PYTHONPATH`, or `PYTHONHOME` can interfere with uv runtime bootstrap.');
  }

  const hasCustomIndex =
    Object.keys(env).some((key) => /^PIP_/i.test(key))
    || Boolean(String(env.UV_INDEX_URL || '').trim())
    || Boolean(String(env.UV_EXTRA_INDEX_URL || '').trim());
  if (hasCustomIndex) {
    guidance.push('Custom package index settings were detected. Check `PIP_*`, `UV_INDEX_URL`, or `UV_EXTRA_INDEX_URL` if uv could not download packages.');
  }

  const hasProxyOrCert =
    ['HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy', 'SSL_CERT_FILE', 'REQUESTS_CA_BUNDLE']
      .some((key) => Boolean(String(env[key] || '').trim()));
  if (hasProxyOrCert) {
    guidance.push('Proxy or certificate overrides were detected. If uv reported TLS, certificate, or download errors above, verify those settings and try again.');
  }

  guidance.push('Look at the uv error printed above this message. That original uv output is the real failure reason.');
  return guidance;
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

function resolveBackgroundPythonExecutable(runtimePython) {
  const normalized = String(runtimePython || '').trim();
  if (process.platform !== 'win32' || !normalized) {
    return normalized;
  }
  const runtimePath = path.resolve(normalized);
  const runtimeDir = path.dirname(runtimePath);
  const pythonwCandidate = path.join(runtimeDir, 'pythonw.exe');
  if (fs.existsSync(pythonwCandidate)) {
    return pythonwCandidate;
  }
  return runtimePath;
}

function syncUvProjectEnvironment(home, uvBinary, pythonTarget, editable) {
  const args = ['sync', '--frozen', '--no-dev', '--python', pythonTarget];
  if (shouldCompileRuntimeBytecode()) {
    args.splice(3, 0, '--compile-bytecode');
  }
  if (!editable) {
    // Force-refresh the local project package so same-version source installs
    // don't reuse a stale cached wheel during runtime rebuilds.
    args.push('--no-editable', '--reinstall-package', 'deepscientist');
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
  for (const line of buildUvSyncFailureGuidance()) {
    console.error(line);
  }
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
    if (arg === '--here') {
      continue;
    }
    if (arg === '--yolo') {
      const parsed = parseBooleanFlagValue(args[index + 1]);
      if (parsed !== null) {
        index += 1;
      }
      continue;
    }
    if (typeof arg === 'string' && arg.startsWith('--yolo=')) {
      continue;
    }
    if (arg === '--codex-profile') {
      index += 1;
      continue;
    }
    if (arg === '--codex') {
      index += 1;
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

function installIndexPath() {
  return path.join(os.homedir(), '.deepscientist', 'install-index.json');
}

function readInstallIndex() {
  const indexPath = installIndexPath();
  if (!fs.existsSync(indexPath)) {
    return { installs: [] };
  }
  try {
    const payload = JSON.parse(fs.readFileSync(indexPath, 'utf8'));
    const installs = Array.isArray(payload?.installs) ? payload.installs.filter((item) => item && typeof item === 'object') : [];
    return { installs };
  } catch {
    return { installs: [] };
  }
}

function writeInstallIndex(payload) {
  const normalized = {
    installs: Array.isArray(payload?.installs) ? payload.installs : [],
  };
  const targetPath = installIndexPath();
  ensureDir(path.dirname(targetPath));
  fs.writeFileSync(targetPath, `${JSON.stringify(normalized, null, 2)}\n`, 'utf8');
}

function normalizeInstallRecord(record) {
  const normalizedHome = normalizeHomePath(record?.home || '');
  if (!normalizedHome) {
    return null;
  }
  const installMode = String(record?.install_mode || '').trim() || null;
  const installDir = record?.install_dir ? normalizeHomePath(record.install_dir) : null;
  const packageRoot = record?.package_root ? normalizeHomePath(record.package_root) : null;
  const launcherPath = record?.launcher_path ? path.resolve(String(record.launcher_path)) : null;
  const wrapperPaths = Array.isArray(record?.wrapper_paths)
    ? [...new Set(record.wrapper_paths.map((item) => String(item || '').trim()).filter(Boolean).map((item) => path.resolve(item)))]
    : [];
  const createdAt = String(record?.created_at || '').trim() || new Date().toISOString();
  return {
    home: normalizedHome,
    install_mode: installMode,
    install_dir: installDir,
    package_root: packageRoot,
    launcher_path: launcherPath,
    wrapper_paths: wrapperPaths,
    created_at: createdAt,
    updated_at: new Date().toISOString(),
  };
}

function installRecordMatches(left, right) {
  return left.home === right.home
    && (left.install_dir || null) === (right.install_dir || null)
    && (left.package_root || null) === (right.package_root || null)
    && (left.install_mode || null) === (right.install_mode || null);
}

function upsertInstallRecord(record) {
  const normalized = normalizeInstallRecord(record);
  if (!normalized) {
    return null;
  }
  const index = readInstallIndex();
  const installs = index.installs
    .map((item) => normalizeInstallRecord(item))
    .filter(Boolean);
  const nextInstalls = installs.filter((item) => !installRecordMatches(item, normalized));
  nextInstalls.push(normalized);
  nextInstalls.sort((left, right) => String(left.updated_at || '').localeCompare(String(right.updated_at || '')));
  writeInstallIndex({ installs: nextInstalls });
  return normalized;
}

function removeInstallRecords(predicate) {
  const index = readInstallIndex();
  const installs = index.installs
    .map((item) => normalizeInstallRecord(item))
    .filter(Boolean);
  const nextInstalls = installs.filter((item) => !predicate(item));
  writeInstallIndex({ installs: nextInstalls });
  return nextInstalls;
}

function parseManagedWrapperCandidate(candidatePath) {
  let stat = null;
  try {
    stat = fs.lstatSync(candidatePath);
  } catch {
    return null;
  }

  if (!stat.isFile() && !stat.isSymbolicLink()) {
    return null;
  }

  let text = '';
  try {
    text = fs.readFileSync(candidatePath, 'utf8');
  } catch {
    return null;
  }

  const homeMatch = text.match(/export DEEPSCIENTIST_HOME="([^"\n]+)"/);
  const execMatch = text.match(/exec "([^"\n]+)" "\$@"/);
  return {
    path: path.resolve(candidatePath),
    home: homeMatch ? normalizeHomePath(homeMatch[1]) : null,
    execPath: execMatch ? path.resolve(execMatch[1]) : null,
  };
}

function collectManagedWrapperPaths({ home, installDir = null, explicitWrapperPaths = [] }) {
  const normalizedHome = normalizeHomePath(home);
  const normalizedInstallDir = installDir ? normalizeHomePath(installDir) : null;
  const candidates = new Set(explicitWrapperPaths.map((item) => path.resolve(String(item))));
  for (const commandName of launcherWrapperCommands) {
    for (const candidate of candidateWrapperPathsForCommand(commandName)) {
      candidates.add(candidate);
    }
  }
  const matched = [];
  for (const candidate of candidates) {
    const parsed = parseManagedWrapperCandidate(candidate);
    if (!parsed) {
      continue;
    }
    if (parsed.home && parsed.home === normalizedHome) {
      matched.push(parsed.path);
      continue;
    }
    if (normalizedInstallDir && parsed.execPath && parsed.execPath.startsWith(path.join(normalizedInstallDir, 'bin'))) {
      matched.push(parsed.path);
    }
  }
  return [...new Set(matched)].sort();
}

function buildCodeOnlyUninstallPlan({ home, installDir = null, wrapperPaths = [] }) {
  const normalizedHome = normalizeHomePath(home);
  const normalizedInstallDir = installDir ? normalizeHomePath(installDir) : null;
  const removePaths = [
    path.join(normalizedHome, 'runtime', 'python-env'),
    path.join(normalizedHome, 'runtime', 'python'),
    path.join(normalizedHome, 'runtime', 'tools'),
    path.join(normalizedHome, 'runtime', 'bundle'),
    path.join(normalizedHome, 'runtime', 'daemon.json'),
  ];
  if (normalizedInstallDir && normalizedInstallDir !== normalizeHomePath(repoRoot)) {
    removePaths.push(normalizedInstallDir);
  }
  return {
    remove_paths: [...new Set(removePaths.map((item) => path.resolve(item)))].sort(),
    preserve_paths: [
      path.join(normalizedHome, 'quests'),
      path.join(normalizedHome, 'memory'),
      path.join(normalizedHome, 'config'),
      path.join(normalizedHome, 'logs'),
      path.join(normalizedHome, 'plugins'),
      path.join(normalizedHome, 'cache'),
    ].sort(),
    wrapper_paths: [...new Set(wrapperPaths.map((item) => path.resolve(item)))].sort(),
  };
}

function removePathEntry(targetPath) {
  if (!targetPath || !fs.existsSync(targetPath)) {
    return false;
  }
  const stat = fs.lstatSync(targetPath);
  if (stat.isDirectory() && !stat.isSymbolicLink()) {
    fs.rmSync(targetPath, { recursive: true, force: true });
    return true;
  }
  fs.rmSync(targetPath, { force: true });
  return true;
}

function currentInstallRecord(home) {
  const installMode = detectInstallMode(repoRoot);
  return normalizeInstallRecord({
    home,
    install_mode: installMode,
    install_dir: installMode === 'source-checkout' ? null : null,
    package_root: normalizeHomePath(repoRoot),
    launcher_path: resolveLauncherPath() || path.join(repoRoot, 'bin', 'ds.js'),
    wrapper_paths: [],
  });
}

function registerCurrentInstall(home) {
  const record = currentInstallRecord(home);
  if (!record) {
    return null;
  }
  return upsertInstallRecord(record);
}

function dedupeUninstallRecords(records) {
  const seen = new Set();
  const deduped = [];
  for (const record of records) {
    const normalized = normalizeInstallRecord(record);
    if (!normalized) {
      continue;
    }
    const key = JSON.stringify([
      normalized.home,
      normalized.install_mode || null,
      normalized.install_dir || null,
      normalized.package_root || null,
    ]);
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    deduped.push(normalized);
  }
  return deduped;
}

function resolveUninstallRecords({ home, origin }) {
  const normalizedHome = normalizeHomePath(home);
  const currentPackageRoot = normalizeHomePath(repoRoot);
  const index = readInstallIndex();
  const installs = index.installs.map((item) => normalizeInstallRecord(item)).filter(Boolean);
  if (origin === 'npm') {
    const matching = installs.filter((item) => item.package_root === currentPackageRoot);
    if (matching.length > 0) {
      return dedupeUninstallRecords(matching);
    }
    return dedupeUninstallRecords([currentInstallRecord(normalizedHome)]);
  }
  const matching = installs.filter((item) => item.home === normalizedHome);
  if (matching.length > 0) {
    return dedupeUninstallRecords(matching);
  }
  const inferredInstallDir = fs.existsSync(path.join(normalizedHome, 'cli')) ? path.join(normalizedHome, 'cli') : null;
  return dedupeUninstallRecords([
    {
      ...currentInstallRecord(normalizedHome),
      install_dir: inferredInstallDir,
    },
  ]);
}

function aggregateCodeOnlyUninstallPlan(records) {
  const removePaths = new Set();
  const preservePaths = new Set();
  const wrapperPaths = new Set();
  for (const record of records) {
    const installDir = record.install_dir || (fs.existsSync(path.join(record.home, 'cli')) ? path.join(record.home, 'cli') : null);
    const matchedWrappers = collectManagedWrapperPaths({
      home: record.home,
      installDir,
      explicitWrapperPaths: record.wrapper_paths || [],
    });
    const plan = buildCodeOnlyUninstallPlan({
      home: record.home,
      installDir,
      wrapperPaths: matchedWrappers,
    });
    for (const targetPath of plan.remove_paths) removePaths.add(targetPath);
    for (const targetPath of plan.preserve_paths) preservePaths.add(targetPath);
    for (const targetPath of plan.wrapper_paths) wrapperPaths.add(targetPath);
  }
  return {
    remove_paths: [...removePaths].sort(),
    preserve_paths: [...preservePaths].sort(),
    wrapper_paths: [...wrapperPaths].sort(),
  };
}

async function promptUninstallConfirmation({ records, plan }) {
  if (!process.stdin.isTTY || !process.stdout.isTTY) {
    throw new Error('DeepScientist uninstall needs a TTY for confirmation. Re-run with `--yes` to continue non-interactively.');
  }
  console.log('');
  console.log('DeepScientist uninstall');
  console.log('');
  console.log('This removes code and runtime directories, but preserves local data.');
  console.log('');
  for (const record of records) {
    console.log(`Home: ${record.home}`);
  }
  console.log('');
  console.log('Code/runtime paths to remove:');
  for (const targetPath of plan.remove_paths) {
    console.log(`- ${targetPath}`);
  }
  console.log('');
  console.log('Preserved data paths:');
  for (const targetPath of plan.preserve_paths) {
    console.log(`- ${targetPath}`);
  }
  const answer = await new Promise((resolve) => {
    const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
    rl.question('Type UNINSTALL to continue: ', (value) => {
      rl.close();
      resolve(String(value || '').trim());
    });
  });
  return answer === 'UNINSTALL';
}

function runGlobalNpmUninstall() {
  const configuredPrefix = String(process.env.npm_config_prefix || process.env.NPM_CONFIG_PREFIX || '').trim();
  let uninstallPrefix = configuredPrefix || null;
  if (!uninstallPrefix && detectInstallMode(repoRoot) === 'npm-package') {
    let cursor = path.resolve(repoRoot);
    while (cursor && cursor !== path.dirname(cursor)) {
      if (path.basename(cursor) === 'node_modules') {
        const container = path.dirname(cursor);
        uninstallPrefix =
          path.basename(container) === 'lib'
            ? path.dirname(container)
            : container;
        break;
      }
      cursor = path.dirname(cursor);
    }
  }
  const npmBinary =
    resolveExecutableOnPath(process.platform === 'win32' ? 'npm.cmd' : 'npm')
    || resolveExecutableOnPath('npm');
  if (!npmBinary) {
    return {
      ok: false,
      message: 'Global npm package removal was skipped because `npm` is not available on PATH.',
    };
  }
  const result = spawnSync(
    npmBinary,
    ['uninstall', '-g', UPDATE_PACKAGE_NAME, ...(uninstallPrefix ? ['--prefix', uninstallPrefix] : [])],
    syncSpawnOptions({
      stdio: 'inherit',
      env: process.env,
    })
  );
  if (result.error) {
    return {
      ok: false,
      message: result.error.message,
    };
  }
  return {
    ok: result.status === 0,
    message: result.status === 0 ? null : `npm uninstall exited with status ${result.status ?? 1}.`,
  };
}

function buildDaemonStatusPayload({ home, url, state, health, launcherPath = null }) {
  const healthy = Boolean(health && health.status === 'ok');
  const identityMatch = state ? healthMatchesManagedState({ health, state, home }) : false;
  return {
    healthy,
    identity_match: identityMatch,
    managed: Boolean(state),
    home,
    url,
    daemon_state_path: daemonStatePath(home),
    launcher_path: launcherPath || resolveLauncherPath() || null,
    daemon: state,
    health,
  };
}

function daemonSupervisorLogPath(home) {
  return path.join(home, 'logs', 'daemon-supervisor.log');
}

function appendDaemonSupervisorLog(home, message) {
  try {
    const logPath = daemonSupervisorLogPath(home);
    ensureDir(path.dirname(logPath));
    fs.appendFileSync(logPath, `[${new Date().toISOString()}] ${String(message || '').trim()}\n`, 'utf8');
  } catch {}
}

function observeManagedDaemonChild(home, child, daemonId) {
  if (!child || typeof child.once !== 'function') {
    return;
  }
  const normalizedDaemonId = String(daemonId || '').trim() || 'unknown';
  child.once('exit', (code, signal) => {
    appendDaemonSupervisorLog(
      home,
      `daemon ${normalizedDaemonId} exited with code=${code === null ? 'null' : code} signal=${signal || 'null'}`
    );
  });
  child.once('error', (error) => {
    appendDaemonSupervisorLog(
      home,
      `daemon ${normalizedDaemonId} child process error: ${error instanceof Error ? error.message : String(error)}`
    );
  });
}

function encodeSupervisorEnvPayload(envOverrides) {
  const payload = envOverrides && typeof envOverrides === 'object' && !Array.isArray(envOverrides) ? envOverrides : {};
  return Buffer.from(JSON.stringify(payload), 'utf8').toString('base64');
}

function decodeSupervisorEnvPayload(rawValue) {
  const normalized = String(rawValue || '').trim();
  if (!normalized) {
    return {};
  }
  try {
    const parsed = JSON.parse(Buffer.from(normalized, 'base64').toString('utf8'));
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {};
  } catch {
    return {};
  }
}

function spawnManagedDaemonProcess({
  home,
  runtimePython,
  host,
  port,
  proxy = null,
  envOverrides = {},
  daemonId = null,
  authEnabled = false,
  authToken = null,
}) {
  const browserUrl = browserUiUrl(host, port);
  const daemonBindUrl = bindUiUrl(host, port);
  const resolvedAuthEnabled = authEnabled !== false;
  const resolvedAuthToken = resolvedAuthEnabled
    ? (typeof authToken === 'string' && authToken.trim() ? authToken.trim() : generateBrowserAuthToken())
    : null;
  const launchUrl = browserUrl;
  const bindLaunchUrl = daemonBindUrl;
  const logPath = path.join(home, 'logs', 'daemon.log');
  ensureDir(path.dirname(logPath));
  const out = fs.openSync(logPath, 'a');
  const resolvedDaemonId = String(daemonId || crypto.randomUUID()).trim();
  const launcherPath = path.join(repoRoot, 'bin', 'ds.js');
  const backgroundPython = resolveBackgroundPythonExecutable(runtimePython);
  const child = spawn(
    backgroundPython,
    [
      '-m',
      'deepscientist.cli',
      '--home',
      home,
      ...(normalizeProxyUrl(proxy) ? ['--proxy', normalizeProxyUrl(proxy)] : []),
      'daemon',
      '--host',
      host,
      '--port',
      String(port),
      '--auth',
      resolvedAuthEnabled ? 'true' : 'false',
      ...(resolvedAuthEnabled && resolvedAuthToken ? ['--auth-token', resolvedAuthToken] : []),
    ],
    detachedSpawnOptions({
      cwd: repoRoot,
      stdio: ['ignore', out, out],
      env: {
        ...process.env,
        ...envOverrides,
        DEEPSCIENTIST_REPO_ROOT: repoRoot,
        DEEPSCIENTIST_NODE_BINARY: process.execPath,
        DEEPSCIENTIST_LAUNCHER_PATH: launcherPath,
        DS_DAEMON_ID: resolvedDaemonId,
        DS_DAEMON_MANAGED_BY: 'ds-launcher',
        DS_UI_AUTH_ENABLED: resolvedAuthEnabled ? '1' : '0',
        ...(resolvedAuthEnabled && resolvedAuthToken ? { DS_UI_AUTH_TOKEN: resolvedAuthToken } : {}),
      },
    })
  );
  child.unref();
  const statePayload = {
    pid: child.pid,
    host,
    port,
    url: browserUrl,
    bind_url: daemonBindUrl,
    launch_url: launchUrl,
    bind_launch_url: bindLaunchUrl,
    log_path: logPath,
    started_at: new Date().toISOString(),
    home: normalizeHomePath(home),
    daemon_id: resolvedDaemonId,
    auth_enabled: resolvedAuthEnabled,
    auth_token: resolvedAuthToken,
  };
  writeDaemonState(home, statePayload);
  return {
    child,
    statePayload,
    browserUrl,
    bindUrl: daemonBindUrl,
    launchUrl,
    bindLaunchUrl,
    logPath,
  };
}

function spawnDaemonSupervisor({ home, runtimePython, host, port, proxy = null, envOverrides = {}, daemonId }) {
  const launcherPath = resolveLauncherPath() || path.join(repoRoot, 'bin', 'ds.js');
  const args = [
    launcherPath,
    '--daemon-supervisor',
    '--home',
    home,
    '--runtime-python',
    runtimePython,
    '--host',
    host,
    '--port',
    String(port),
    '--daemon-id',
    String(daemonId || '').trim(),
  ];
  const normalizedProxy = normalizeProxyUrl(proxy);
  if (normalizedProxy) {
    args.push('--proxy', normalizedProxy);
  }
  const envPayload = encodeSupervisorEnvPayload(envOverrides);
  if (envPayload) {
    args.push('--env-json', envPayload);
  }
  const child = spawn(process.execPath, args, detachedSpawnOptions({
    cwd: repoRoot,
    stdio: 'ignore',
    env: {
      ...process.env,
      DEEPSCIENTIST_REPO_ROOT: repoRoot,
      DEEPSCIENTIST_NODE_BINARY: process.execPath,
      DEEPSCIENTIST_LAUNCHER_PATH: launcherPath,
    },
  }));
  child.unref();
  return child.pid || null;
}

function parseDaemonSupervisorArgs(argv) {
  const args = [...argv];
  let home = null;
  let runtimePython = null;
  let host = '0.0.0.0';
  let port = 20999;
  let proxy = null;
  let daemonId = null;
  let envJson = '';

  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    if (arg === '--home') {
      const next = readRequiredOptionValue(args, index, '--home');
      if (!next.ok) return { help: false, error: next.error };
      home = path.resolve(next.value);
      index += 1;
    } else if (arg === '--runtime-python') {
      const next = readRequiredOptionValue(args, index, '--runtime-python');
      if (!next.ok) return { help: false, error: next.error };
      runtimePython = next.value;
      index += 1;
    } else if (arg === '--host') {
      const next = readRequiredOptionValue(args, index, '--host');
      if (!next.ok) return { help: false, error: next.error };
      host = next.value;
      index += 1;
    } else if (arg === '--port') {
      const next = readRequiredOptionValue(args, index, '--port');
      if (!next.ok) return { help: false, error: next.error };
      const parsed = parseStrictPortOption(next.value, '--port');
      if (!parsed.ok) return { help: false, error: parsed.error };
      port = parsed.value;
      index += 1;
    } else if (arg === '--proxy') {
      const next = readRequiredOptionValue(args, index, '--proxy');
      if (!next.ok) return { help: false, error: next.error };
      proxy = next.value;
      index += 1;
    } else if (arg === '--daemon-id') {
      const next = readRequiredOptionValue(args, index, '--daemon-id');
      if (!next.ok) return { help: false, error: next.error };
      daemonId = next.value;
      index += 1;
    } else if (arg === '--env-json') {
      const next = readRequiredOptionValue(args, index, '--env-json');
      if (!next.ok) return { help: false, error: next.error };
      envJson = next.value;
      index += 1;
    }
    else if (arg === '--help' || arg === '-h') return { help: true };
    else if (arg.startsWith('--')) return { help: false, error: `Unknown daemon supervisor flag: ${arg}` };
    else return { help: false, error: `Unexpected daemon supervisor argument: ${arg}` };
  }

  if (!home || !runtimePython || !daemonId || !Number.isFinite(port) || port <= 0) {
    return {
      help: false,
      error: 'Daemon supervisor requires --home, --runtime-python, --daemon-id, and a valid --port.',
    };
  }

  return {
    help: false,
    home,
    runtimePython,
    host,
    port,
    proxy,
    daemonId,
    envOverrides: decodeSupervisorEnvPayload(envJson),
    error: null,
  };
}

async function daemonSupervisorMain(rawArgs) {
  const options = parseDaemonSupervisorArgs(rawArgs);
  if (options.help) {
    process.exit(0);
  }
  if (options.error) {
    console.error(options.error);
    process.exit(1);
  }

  const home = options.home;
  let trackedDaemonId = String(options.daemonId || '').trim();
  let restartBackoffMs = 1000;
  appendDaemonSupervisorLog(home, `supervisor started for daemon ${trackedDaemonId}`);

  while (true) {
    const state = readDaemonState(home);
    if (!state) {
      appendDaemonSupervisorLog(home, 'daemon state removed; supervisor exiting');
      return;
    }
    if (state.shutdown_requested_at) {
      appendDaemonSupervisorLog(home, 'managed shutdown requested; supervisor exiting');
      return;
    }
    const stateHome = normalizeHomePath(state.home || home);
    if (stateHome !== normalizeHomePath(home)) {
      appendDaemonSupervisorLog(home, `daemon state home changed to ${stateHome}; supervisor exiting`);
      return;
    }
    const stateDaemonId = String(state.daemon_id || '').trim();
    if (trackedDaemonId && stateDaemonId && stateDaemonId !== trackedDaemonId) {
      appendDaemonSupervisorLog(home, `daemon id changed to ${stateDaemonId}; supervisor exiting`);
      return;
    }
    const authToken = typeof state.auth_token === 'string' ? state.auth_token.trim() : '';
    const health = await fetchHealth(state.url || browserUiUrl(options.host, options.port), authToken);
    if (health && health.status === 'ok' && healthMatchesManagedState({ health, state, home })) {
      restartBackoffMs = 1000;
      await sleep(2500);
      continue;
    }
    if (state.pid && isPidAlive(state.pid)) {
      await sleep(2500);
      continue;
    }

    appendDaemonSupervisorLog(
      home,
      `daemon ${stateDaemonId || trackedDaemonId || 'unknown'} is not healthy; attempting restart`
    );
    try {
      const restarted = spawnManagedDaemonProcess({
        home,
        runtimePython: options.runtimePython,
        host: options.host,
        port: options.port,
        proxy: options.proxy,
        envOverrides: options.envOverrides,
        authEnabled: state.auth_enabled !== false,
        authToken,
      });
      trackedDaemonId = String(restarted.statePayload.daemon_id || '').trim();
      observeManagedDaemonChild(home, restarted.child, trackedDaemonId);
      appendDaemonSupervisorLog(
        home,
        `restarted daemon ${trackedDaemonId} with pid ${restarted.statePayload.pid}`
      );
      restartBackoffMs = 1000;
      await sleep(2500);
    } catch (error) {
      appendDaemonSupervisorLog(
        home,
        `restart failed: ${error instanceof Error ? error.message : String(error)}`
      );
      await sleep(restartBackoffMs);
      restartBackoffMs = Math.min(restartBackoffMs * 2, 30000);
    }
  }
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function isHealthy(url, authToken = null) {
  const payload = await fetchHealth(url, authToken);
  return Boolean(payload && payload.status === 'ok');
}

async function fetchHealth(url, authToken = null) {
  try {
    const headers = {};
    const normalizedAuthToken = typeof authToken === 'string' ? authToken.trim() : '';
    if (normalizedAuthToken) {
      headers.Authorization = `Bearer ${normalizedAuthToken}`;
    }
    const response = await fetch(`${url}/api/health`, { headers });
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

async function requestDaemonShutdown(url, daemonId, authToken = null) {
  try {
    const headers = {
      'Content-Type': 'application/json',
    };
    const normalizedAuthToken = typeof authToken === 'string' ? authToken.trim() : '';
    if (normalizedAuthToken) {
      headers.Authorization = `Bearer ${normalizedAuthToken}`;
    }
    const response = await fetch(`${url}/api/admin/shutdown`, {
      method: 'POST',
      headers,
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

async function requestDaemonAuthRotate(url, authToken = null) {
  try {
    const headers = {
      'Content-Type': 'application/json',
    };
    const normalizedAuthToken = typeof authToken === 'string' ? authToken.trim() : '';
    if (normalizedAuthToken) {
      headers.Authorization = `Bearer ${normalizedAuthToken}`;
    }
    const response = await fetch(`${url}/api/auth/rotate`, {
      method: 'POST',
      headers,
      body: '{}',
    });
    if (!response.ok) {
      return null;
    }
    const payload = await response.json().catch(() => ({}));
    const token = typeof payload?.token === 'string' ? payload.token.trim() : '';
    return token || null;
  } catch {
    return null;
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
    const result = spawnSync('taskkill', taskkillArgs, syncSpawnOptions({ stdio: 'ignore' }));
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

async function waitForDaemonStop({ url, pid, authToken = null, attempts = 20, delayMs = 200 }) {
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    const healthy = url ? await isHealthy(url, authToken) : false;
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
  const authToken = typeof state?.auth_token === 'string' ? state.auth_token.trim() : '';
  const healthBefore = await fetchHealth(url, authToken);
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

  if (state) {
    writeDaemonState(home, {
      ...state,
      shutdown_requested_at: new Date().toISOString(),
    });
  }

  let stopped = false;

  if (healthyBefore) {
    await requestDaemonShutdown(url, shutdownDaemonId || null, authToken);
    stopped = await waitForDaemonStop({ url, pid, authToken, attempts: 20, delayMs: 200 });
  }

  if (!stopped && pid && isPidAlive(pid)) {
    killManagedProcess(pid, 'SIGTERM');
    stopped = await waitForDaemonStop({ url, pid, authToken, attempts: 30, delayMs: 200 });
  }

  if (!stopped && pid && isPidAlive(pid)) {
    killManagedProcess(pid, 'SIGKILL');
    stopped = await waitForDaemonStop({ url, pid, authToken, attempts: 20, delayMs: 150 });
  }

  const stillHealthy = await isHealthy(url, authToken);
  if (!stopped && (stillHealthy || (pid && isPidAlive(pid)))) {
    console.error('DeepScientist daemon is still running after shutdown attempts.');
    process.exit(1);
  }

  removeDaemonState(home);
  console.log('DeepScientist daemon stopped.');
}

async function uninstallMain(rawArgs) {
  const options = parseUninstallArgs(rawArgs);
  if (options.help) {
    printUninstallHelp();
    process.exit(0);
  }
  if (options.error) {
    console.error(options.error);
    console.error('Run `ds uninstall --help` for usage.');
    process.exit(1);
  }

  const home = normalizeHomePath(options.home || resolveHome(rawArgs));
  const records = resolveUninstallRecords({ home, origin: options.origin });
  const plan = aggregateCodeOnlyUninstallPlan(records);

  if (!options.yes && options.origin !== 'npm') {
    const confirmed = await promptUninstallConfirmation({ records, plan });
    if (!confirmed) {
      console.log('DeepScientist uninstall cancelled.');
      process.exit(1);
    }
  }

  for (const record of records) {
    try {
      await stopDaemon(record.home);
    } catch (error) {
      console.warn(`DeepScientist could not fully stop the daemon for ${record.home}: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  const removed = [];
  for (const targetPath of plan.remove_paths) {
    if (removePathEntry(targetPath)) {
      removed.push(targetPath);
    }
  }
  for (const targetPath of plan.wrapper_paths) {
    if (removePathEntry(targetPath)) {
      removed.push(targetPath);
    }
  }

  removeInstallRecords((record) => records.some((candidate) => installRecordMatches(candidate, record)));

  let npmRemovalMessage = null;
  if (options.origin !== 'npm' && detectInstallMode(repoRoot) === 'npm-package') {
    const npmRemoval = runGlobalNpmUninstall();
    if (!npmRemoval.ok) {
      npmRemovalMessage = npmRemoval.message;
    }
  }

  console.log('');
  console.log('DeepScientist code uninstall completed.');
  if (removed.length > 0) {
    console.log('');
    console.log('Removed:');
    for (const targetPath of removed) {
      console.log(`- ${targetPath}`);
    }
  }
  console.log('');
  console.log('Preserved local data:');
  for (const targetPath of plan.preserve_paths) {
    console.log(`- ${targetPath}`);
  }
  console.log('');
  for (const record of records) {
    console.log(`If you also want to delete local data manually: rm -rf ${record.home}`);
  }
  if (npmRemovalMessage) {
    console.log('');
    console.warn(`Global npm package removal did not complete automatically: ${npmRemovalMessage}`);
    console.warn(`Run: npm uninstall -g ${UPDATE_PACKAGE_NAME}`);
  }
  process.exit(0);
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
  const result = spawnSync(npmBinary, args, syncSpawnOptions({
    encoding: 'utf8',
    env: process.env,
    timeout: 15 * 60 * 1000,
  }));
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

function printUpdateStatus(status, { compact = false } = {}) {
  if (compact) {
    if (status.update_available) {
      console.log(`DeepScientist update available: ${status.current_version} -> ${status.latest_version}`);
      console.log(`Update with: ${status.manual_update_command}`);
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
    ['Last checked', status.last_checked_at || 'never'],
  ]);
  if (status.last_check_error) {
    console.log('');
    console.log(`Version check error: ${status.last_check_error}`);
  }
  if (status.update_available || status.manual_update_command) {
    console.log('');
    console.log(`Update command: ${status.manual_update_command}`);
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

function parseYesNoAnswer(answer, defaultValue = false) {
  const normalized = String(answer || '').trim().toLowerCase();
  if (!normalized) {
    return defaultValue;
  }
  if (normalized === 'y' || normalized === 'yes') {
    return true;
  }
  if (normalized === 'n' || normalized === 'no') {
    return false;
  }
  return defaultValue;
}

async function promptYesNo(question, { defaultValue = false } = {}) {
  if (!process.stdin.isTTY || !process.stdout.isTTY) {
    return defaultValue;
  }
  return new Promise((resolve) => {
    const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
    rl.question(question, (answer) => {
      rl.close();
      resolve(parseYesNoAnswer(answer, defaultValue));
    });
  });
}

function spawnDetachedNode(args, options = {}) {
  const out = options.logPath ? fs.openSync(options.logPath, 'a') : 'ignore';
  const child = spawn(process.execPath, args, detachedSpawnOptions({
    cwd: options.cwd || repoRoot,
    stdio: ['ignore', out, out],
    env: options.env || process.env,
  }));
  child.unref();
  return child;
}

async function performSelfUpdate(home, options = {}) {
  const status = checkForUpdates(home, { force: true });
  if (!status.update_available) {
    const message = `DeepScientist is already on the latest version (${status.current_version}).`;
    mergeUpdateState(home, {
      current_version: status.current_version,
      latest_version: status.latest_version,
      busy: false,
      target_version: null,
      last_update_finished_at: new Date().toISOString(),
      last_update_result: {
        ok: true,
        target_version: null,
        message,
      },
    });
    return {
      ok: true,
      updated: false,
      status,
      message,
    };
  }
  if (!status.can_self_update) {
    const message = status.reason || `Manual update required: ${status.manual_update_command}`;
    mergeUpdateState(home, {
      current_version: status.current_version,
      latest_version: status.latest_version,
      busy: false,
      target_version: null,
      last_update_finished_at: new Date().toISOString(),
      last_update_result: {
        ok: false,
        target_version: status.latest_version || null,
        message,
      },
    });
    return {
      ok: false,
      updated: false,
      status,
      message,
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

  const npmBinary = resolveNpmBinary();
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

  repairLegacyPathWrappers({
    home,
    launcherPath: resolveLauncherPath(),
  });

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
    const restartArgs = [
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
    ];
    if (daemonState && daemonState.auth_enabled === false) {
      restartArgs.push('--auth', 'false');
    }
    spawnDetachedNode(
      restartArgs,
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

function normalizeLauncherRelaunchArgs(rawArgs, home) {
  const normalized = [];
  for (let index = 0; index < rawArgs.length; index += 1) {
    const arg = rawArgs[index];
    if (arg === '--home') {
      index += 1;
      continue;
    }
    if (arg === '--here' || arg === '--skip-update-check') {
      continue;
    }
    normalized.push(arg);
  }
  return ['--home', home, ...normalized, '--skip-update-check'];
}

function relaunchLauncherAfterUpdate(rawArgs, home) {
  const launcherPath = resolveLauncherPath();
  if (!launcherPath) {
    return {
      ok: false,
      exitCode: 1,
      message: 'DeepScientist was updated, but the new launcher path could not be resolved for relaunch.',
    };
  }
  const result = spawnSync(process.execPath, [launcherPath, ...normalizeLauncherRelaunchArgs(rawArgs, home)], syncSpawnOptions({
    cwd: repoRoot,
    stdio: 'inherit',
    env: process.env,
  }));
  if (result.error) {
    return {
      ok: false,
      exitCode: 1,
      message: result.error.message,
    };
  }
  return {
    ok: true,
    exitCode: result.status ?? 0,
    message: null,
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

  printUpdateStatus(status, { compact: true });
  if (!status.can_self_update || !process.stdin.isTTY || !process.stdout.isTTY) {
    markUpdateDeferred(home, status.latest_version);
    return false;
  }

  const confirmed = await promptYesNo(`Install DeepScientist ${status.latest_version} now? [y/N]: `, {
    defaultValue: false,
  });
  if (!confirmed) {
    markUpdateDeferred(home, status.latest_version);
    console.log(`DeepScientist will remind you later about ${status.latest_version || 'the next release'}.`);
    return false;
  }

  console.log('Updating DeepScientist now...');
  const payload = await performSelfUpdate(home, {
    host: options.host,
    port: options.port,
    restartDaemon: false,
  });
  console.log(payload.message);
  if (payload.log_path) {
    console.log(`Update log: ${payload.log_path}`);
  }
  if (!payload.ok) {
    console.log('DeepScientist will continue launching with the current session.');
    return false;
  }

  console.log('Relaunching DeepScientist...');
  const relaunch = relaunchLauncherAfterUpdate(rawArgs, home);
  if (!relaunch.ok) {
    console.error(relaunch.message);
    process.exit(relaunch.exitCode || 1);
  }
  process.exit(relaunch.exitCode || 0);
  return true;
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
  if (!status.update_available) {
    return {
      ok: true,
      started: false,
      message: `DeepScientist is already on the latest version (${status.current_version}).`,
      status,
    };
  }
  if (!status.can_self_update) {
    return {
      ok: false,
      started: false,
      message: status.reason || `Manual update required: ${status.manual_update_command}`,
      status,
    };
  }
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

async function maybeHandleMiniMaxCodexVersion(home, runtimePython, options = {}) {
  const configuredRunners = (() => {
    try {
      const result = runPythonCli(runtimePython, ['--home', home, 'config', 'show', 'runners'], {
        capture: true,
        allowFailure: true,
      });
      return String(result.stdout || '');
    } catch {
      return '';
    }
  })();
  const profileFromConfig =
    configuredRunners.match(/^\s*profile:\s*["']?([^"'\n]+)["']?\s*$/m)?.[1]?.trim() || '';
  const binaryFromConfig =
    configuredRunners.match(/^\s*binary:\s*["']?([^"'\n]+)["']?\s*$/m)?.[1]?.trim() || 'codex';
  const configDirFromConfig =
    configuredRunners.match(/^\s*config_dir:\s*["']?([^"'\n]+)["']?\s*$/m)?.[1]?.trim() || '~/.codex';

  const effectiveProfile = String(options.codexProfile || profileFromConfig || '').trim();
  if (!effectiveProfile) {
    return false;
  }
  const metadata = readCodexProviderMetadata(configDirFromConfig, effectiveProfile);
  if (String(metadata.provider || '').trim().toLowerCase() !== 'minimax') {
    return false;
  }
  const version = installedCodexCliVersion(options.codexBinary || binaryFromConfig || 'codex');
  const expected = [0, 57, 0];
  if (!version || compareCodexCliVersion(version, expected) === 0) {
    return false;
  }
  if (!process.stdin.isTTY || !process.stdout.isTTY) {
    console.log(
      `MiniMax profile \`${effectiveProfile}\` is configured, but installed Codex CLI is ${formatCodexCliVersion(version)}. MiniMax currently requires Codex CLI 0.57.0 for the documented path.`
    );
    console.log('Install it manually with `npm install -g @openai/codex@0.57.0` before continuing.');
    return false;
  }

  console.log('');
  console.log(colorize('\u001B[1;38;5;214m', 'MiniMax compatibility check'));
  console.log(
    `DeepScientist detected MiniMax profile \`${effectiveProfile}\`, but installed Codex CLI is ${formatCodexCliVersion(version)}.`
  );
  console.log('MiniMax currently requires Codex CLI 0.57.0 for the documented DeepScientist path.');
  const confirmed = await promptYesNo('Reinstall Codex CLI to 0.57.0 now? [y/N]: ', {
    defaultValue: false,
  });
  if (!confirmed) {
    return false;
  }
  const npmBinary = resolveNpmBinary();
  if (!npmBinary) {
    console.error('`npm` is unavailable; cannot reinstall Codex CLI automatically.');
    process.exit(1);
  }
  const result = spawnSync(
    npmBinary,
    ['install', '-g', '@openai/codex@0.57.0'],
    syncSpawnOptions({ stdio: 'inherit' })
  );
  if (result.status !== 0) {
    console.error('Failed to reinstall Codex CLI 0.57.0 automatically.');
    process.exit(result.status ?? 1);
  }
  return true;
}

async function readConfiguredUiAddress(home, runtimePython, fallbackHost, fallbackPort) {
  try {
    const result = runPythonCli(runtimePython, ['--home', home, 'config', 'show', 'config'], { capture: true, allowFailure: true });
    const text = result.stdout || '';
    const hostMatch = text.match(/^\s*host:\s*["']?([^"'\n]+)["']?\s*$/m);
    const portMatch = text.match(/^\s*port:\s*(\d+)\s*$/m);
    const authMatch = text.match(/^\s*auth_enabled:\s*([^\n]+)\s*$/m);
    const modeMatch = text.match(/^\s*default_mode:\s*["']?([^"'\n]+)["']?\s*$/m);
    const autoOpenMatch = text.match(/^\s*auto_open_browser:\s*([^\n]+)\s*$/m);
    return {
      host: fallbackHost || (hostMatch ? hostMatch[1].trim() : '0.0.0.0'),
      port: fallbackPort || (portMatch ? Number(portMatch[1]) : 20999),
      authEnabled: parseBooleanSetting(authMatch ? authMatch[1].trim() : false, false),
      defaultMode: normalizeMode(modeMatch ? modeMatch[1].trim() : 'web'),
      autoOpenBrowser: parseBooleanSetting(autoOpenMatch ? autoOpenMatch[1].trim() : true, true),
    };
  } catch {
    return {
      host: fallbackHost || '0.0.0.0',
      port: fallbackPort || 20999,
      authEnabled: false,
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
      authEnabled: false,
      defaultMode: 'web',
      autoOpenBrowser: true,
    };
  }
  try {
    const text = fs.readFileSync(configPath, 'utf8');
    const hostMatch = text.match(/^\s*host:\s*["']?([^"'\n]+)["']?\s*$/m);
    const portMatch = text.match(/^\s*port:\s*(\d+)\s*$/m);
    const authMatch = text.match(/^\s*auth_enabled:\s*([^\n]+)\s*$/m);
    const modeMatch = text.match(/^\s*default_mode:\s*["']?([^"'\n]+)["']?\s*$/m);
    const autoOpenMatch = text.match(/^\s*auto_open_browser:\s*([^\n]+)\s*$/m);
    return {
      host: fallbackHost || (hostMatch ? hostMatch[1].trim() : '0.0.0.0'),
      port: fallbackPort || (portMatch ? Number(portMatch[1]) : 20999),
      authEnabled: parseBooleanSetting(authMatch ? authMatch[1].trim() : false, false),
      defaultMode: normalizeMode(modeMatch ? modeMatch[1].trim() : 'web'),
      autoOpenBrowser: parseBooleanSetting(autoOpenMatch ? autoOpenMatch[1].trim() : true, true),
    };
  } catch {
    return {
      host: fallbackHost || '0.0.0.0',
      port: fallbackPort || 20999,
      authEnabled: false,
      defaultMode: 'web',
      autoOpenBrowser: true,
    };
  }
}

async function startDaemon(home, runtimePython, host, port, proxy = null, envOverrides = {}, authEnabled = false, runnerName = null) {
  const browserUrl = browserUiUrl(host, port);
  const daemonBindUrl = bindUiUrl(host, port);
  const state = readDaemonState(home);
  const desiredAuthToken = authEnabled ? generateBrowserAuthToken() : null;
  const launchUrl = browserUrl;
  const bindLaunchUrl = daemonBindUrl;
  const existingHealth = await fetchHealth(browserUrl, typeof state?.auth_token === 'string' ? state.auth_token.trim() : '');
  if (existingHealth && existingHealth.status === 'ok') {
    if (state && healthMatchesManagedState({ health: existingHealth, state, home })) {
      const stateAuthEnabled = state.auth_enabled !== false;
      const stateAuthToken = typeof state.auth_token === 'string' ? state.auth_token.trim() : '';
      let resolvedAuthToken = stateAuthToken || null;
      if (stateAuthEnabled) {
        const rotatedAuthToken = await requestDaemonAuthRotate(browserUrl, stateAuthToken);
        if (!rotatedAuthToken) {
          console.error('Managed daemon is healthy, but the browser auth token could not be rotated.');
          console.error('Restart the daemon with `ds --restart` if this keeps happening.');
          process.exit(1);
        }
        resolvedAuthToken = rotatedAuthToken;
        writeDaemonState(home, {
          ...state,
          auth_enabled: true,
          auth_token: rotatedAuthToken,
          url: browserUrl,
          bind_url: daemonBindUrl,
          launch_url: launchUrl,
          bind_launch_url: bindLaunchUrl,
        });
      }
      return {
        url: browserUrl,
        bindUrl: daemonBindUrl,
        reused: true,
        authEnabled: stateAuthEnabled,
        authToken: resolvedAuthToken,
      };
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

  const requestedRunner = String(runnerName || readConfiguredDefaultRunner(home, "codex")).trim().toLowerCase() || "codex";
  const startupRunner = resolveStartupRunner(home, runtimePython, requestedRunner, envOverrides);
  if (!startupRunner.ok) {
    throw createRunnerPreflightError(home, requestedRunner, startupRunner.probe);
  }
  const effectiveRunner = startupRunner.runnerName;
  const effectiveEnvOverrides = {
    ...envOverrides,
    ...(effectiveRunner !== requestedRunner ? { DEEPSCIENTIST_DEFAULT_RUNNER: effectiveRunner } : {}),
  };
  if (startupRunner.fallback) {
    console.log(`WARNING: ${requestedRunner} is not ready yet. Starting DeepScientist with fallback runner \`${effectiveRunner}\` for this session.`);
  }

  ensureNodeBundle('src/ui', 'dist/index.html');
  const startedProcess = spawnManagedDaemonProcess({
    home,
    runtimePython,
    host,
    port,
    proxy,
    envOverrides: effectiveEnvOverrides,
    authEnabled,
    authToken: desiredAuthToken,
  });
  const logPath = startedProcess.logPath;

  for (let attempt = 0; attempt < 60; attempt += 1) {
    const health = await fetchHealth(browserUrl, desiredAuthToken);
    if (health && health.status === 'ok') {
      const liveState = readDaemonState(home);
      if (!healthMatchesManagedState({ health, state: liveState, home })) {
        console.error(daemonIdentityError({ url: browserUrl, home, health, state: liveState }));
        process.exit(1);
      }
      const supervisorPid = spawnDaemonSupervisor({
        home,
        runtimePython,
        host,
        port,
        proxy,
        envOverrides,
        daemonId: String((liveState || {}).daemon_id || ''),
      });
      if (supervisorPid) {
        appendDaemonSupervisorLog(home, `supervisor started with pid ${supervisorPid}`);
      }
      return {
        url: launchUrl,
        bindUrl: bindLaunchUrl,
        reused: false,
        authEnabled,
        authToken: desiredAuthToken,
      };
    }
    await sleep(250);
  }

  console.error('DeepScientist daemon failed to become healthy.');
  console.error(`Expected local URL: ${launchUrl}`);
  console.error(`Daemon bind URL: ${bindLaunchUrl}`);
  if (authEnabled && desiredAuthToken) {
    console.error(`Auth token: ${desiredAuthToken}`);
  }
  if (['0.0.0.0', '::', '[::]'].includes(String(host || '').trim())) {
    console.error(`Hint: ${String(host || '').trim() || '0.0.0.0'} is a bind address. Local browser and health probes use ${browserUrl}.`);
  }
  const logTail = tailLog(logPath);
  if (logTail) {
    console.error(logTail);
  }
  process.exit(1);
}

function openBrowser(url) {
  const spawnDetached = (command, args) => {
    try {
      const child = spawn(command, args, detachedSpawnOptions({ stdio: 'ignore' }));
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

function handleRunnerPreflightFailure(error) {
  if (!error || error.code !== 'DS_RUNNER_PREFLIGHT') {
    return false;
  }
  const errorLabel = colorize('\u001B[1;38;5;196m', 'ERROR');
  const warningLabel = colorize('\u001B[1;38;5;214m', 'WARNING');
  console.error('');
  const runnerLabel = String(error.runnerName || 'codex').trim() || 'runner';
  console.error(`${errorLabel} DeepScientist could not start because ${runnerLabel} is not ready yet.`);
  console.error(`Report: ${error.reportPath}`);
  if (Array.isArray(error.probe?.errors)) {
    for (const item of error.probe.errors) {
      console.error(`${errorLabel} ${item}`);
    }
  }
  if (Array.isArray(error.probe?.warnings)) {
    for (const item of error.probe.warnings) {
      console.error(`${warningLabel} ${item}`);
    }
  }
  console.error(`${warningLabel} Recommended fix:`);
  const guidance = Array.isArray(error.probe?.guidance) && error.probe.guidance.length > 0
    ? error.probe.guidance
    : [
        'In most installs, `npm install -g @researai/deepscientist` also installs the bundled Codex dependency.',
        'If `codex` is still missing, run `npm install -g @openai/codex`.',
        'Run `codex login` (or just `codex`) and finish authentication.',
        'Run `ds doctor` and confirm the Codex check passes.',
        'Run `ds` again.',
      ];
  guidance.forEach((item, index) => {
    console.error(`${warningLabel} ${index + 1}. ${item}`);
  });
  openBrowser(error.reportUrl);
  process.exit(1);
  return true;
}

function launchTui(url, questId, home, runtimePython, authToken = null) {
  const entry = ensureNodeBundle('src/tui', 'dist/index.js');
  const args = [entry, '--base-url', url];
  if (questId) {
    args.push('--quest-id', questId);
  }
  if (typeof authToken === 'string' && authToken.trim()) {
    args.push('--auth-token', authToken.trim());
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
  if (options.help) {
    printUpdateHelp();
    process.exit(0);
  }
  if (options.error) {
    console.error(options.error);
    console.error('Run `ds update --help` for update usage.');
    process.exit(1);
  }

  const home = options.home || resolveHome(rawArgs);
  applyLauncherProxy(options.proxy);
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
  printUpdateStatus(status, { compact: true });
  if (!status.can_self_update) {
    process.exit(0);
  }

  const confirmed = await promptYesNo(`Install DeepScientist ${status.latest_version} now? [y/N]: `, {
    defaultValue: false,
  });
  if (!confirmed) {
    const payload = markUpdateDeferred(home, status.latest_version);
    console.log(`DeepScientist will remind you later about ${payload.latest_version || 'the next release'}.`);
    process.exit(0);
  }

  const payload = await performSelfUpdate(home, {
    host: options.host,
    port: options.port,
    restartDaemon: options.restartDaemon,
  });
  console.log(payload.message);
  if (payload.log_path) {
    console.log(`Update log: ${payload.log_path}`);
  }
  process.exit(payload.ok ? 0 : 1);
}

async function migrateMain(rawArgs) {
  const options = parseMigrateArgs(rawArgs);
  if (options.help) {
    printMigrateHelp();
    process.exit(0);
  }
  if (options.error) {
    console.error(options.error);
    console.error('Run `ds migrate --help` for migration usage.');
    process.exit(1);
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
        detachedSpawnOptions({
          cwd: path.join(targetHome, 'cli'),
          stdio: 'ignore',
          env: process.env,
        })
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
  if (options.help) {
    printLauncherHelp();
    process.exit(0);
  }
  if (options.error) {
    console.error(options.error);
    console.error('Run `ds --help` for launcher usage.');
    process.exit(1);
  }

  const home = (options.stop || options.status || options.restart)
    ? resolveManagementHome(rawArgs, options)
    : (options.home || resolveHome(rawArgs));
  applyLauncherProxy(options.proxy);
  ensureDir(home);
  registerCurrentInstall(home);
  const forceWrapperRepair =
    detectInstallMode(repoRoot) !== 'npm-package'
    && Boolean(options.home || process.env.DEEPSCIENTIST_HOME);
  repairLegacyPathWrappers({
    home,
    launcherPath: resolveLauncherPath(),
    force: forceWrapperRepair,
  });

  if (options.stop) {
    await stopDaemon(home);
    process.exit(0);
  }

  if (options.status) {
    const state = readDaemonState(home);
    const configured = readConfiguredUiAddressFromFile(home, options.host, options.port);
    const url = state?.launch_url || state?.url || browserUiUrl(configured.host, configured.port);
    const authToken = typeof state?.auth_token === 'string' ? state.auth_token.trim() : '';
    const probeUrl = state?.url || browserUiUrl(configured.host, configured.port);
    const health = await fetchHealth(probeUrl, authToken);
    const statusPayload = buildDaemonStatusPayload({
      home,
      url,
      state,
      health,
      launcherPath: resolveLauncherPath(),
    });
    console.log(
      JSON.stringify(statusPayload, null, 2)
    );
    process.exit(statusPayload.healthy && (!state || statusPayload.identity_match) ? 0 : 1);
  }

  const pythonRuntime = ensurePythonRuntime(home);
  const runtimePython = pythonRuntime.runtimePython;
  const codexOverrideEnv = buildCodexOverrideEnv({
    yolo: options.yolo,
    profile: options.codexProfile,
    binary: options.codexBinary,
    runner: options.runner,
  });
  ensureInitialized(home, runtimePython);
  if (!options.runner || String(options.runner).trim().toLowerCase() === "codex") {
    await maybeHandleMiniMaxCodexVersion(home, runtimePython, options);
  }
  if (await maybeHandleStartupUpdate(home, rawArgs, options)) {
    return true;
  }
  maybePrintOptionalLatexNotice(home);

  const configuredUi = await readConfiguredUiAddress(home, runtimePython, options.host, options.port);
  const host = configuredUi.host;
  const port = configuredUi.port;
  const authEnabled = options.auth === null ? false : options.auth !== false;
  const mode = normalizeMode(options.mode ?? 'web');
  const shouldOpenBrowser = options.daemonOnly
    ? false
    : options.openBrowser === null
      ? configuredUi.autoOpenBrowser !== false && mode !== 'tui'
      : options.openBrowser;
  const existingState = readDaemonState(home);
  const existingAuthEnabled = existingState ? existingState.auth_enabled !== false : null;
  const existingAuthToken = typeof existingState?.auth_token === 'string' ? existingState.auth_token.trim() : '';
  const authStateMismatch = existingState && (
    existingAuthEnabled !== authEnabled || (authEnabled && !existingAuthToken)
  );
  if (options.restart || authStateMismatch) {
    await stopDaemon(home);
  }

  step(4, 4, 'Starting local daemon and UI surfaces');
  let started;
  try {
    const selectedRunner = String(options.runner || readConfiguredDefaultRunner(home, "codex")).trim().toLowerCase() || "codex";
    started = await startDaemon(home, runtimePython, host, port, options.proxy, codexOverrideEnv, authEnabled, selectedRunner);
  } catch (error) {
    if (handleRunnerPreflightFailure(error)) return true;
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
    yolo: options.yolo,
    authEnabled: started.authEnabled,
    authToken: started.authToken,
  });

  if (options.daemonOnly) {
    process.exit(0);
  }
  if (mode === 'web') {
    process.exit(0);
  }
  launchTui(browserUiUrl(host, port), options.questId, home, runtimePython, started.authToken);
  return true;
}

async function main() {
  const normalizedArgState = normalizeLegacyHostFlagArgs(process.argv.slice(2));
  const args = normalizedArgState.args;
  for (const warning of normalizedArgState.warnings) {
    console.warn(warning);
  }
  if (args[0] === '--daemon-supervisor') {
    await daemonSupervisorMain(args.slice(1));
    return;
  }
  const positional = findFirstPositionalArg(args);
  if (positional && positional.value === 'update') {
    await updateMain(args);
    return;
  }
  if (positional && positional.value === 'migrate') {
    await migrateMain(args);
    return;
  }
  if (positional && positional.value === 'uninstall') {
    await uninstallMain(args);
    return;
  }
  if (
    args.length === 0
    || args[0] === 'ui'
    || (args[0]?.startsWith('--') && (!positional || !pythonCommands.has(positional.value)))
  ) {
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
    const codexOverrideEnv = buildCodexOverrideEnv({
      yolo: resolveYoloFlag(args, true),
      profile: readOptionValue(args, '--codex-profile'),
      binary: readOptionValue(args, '--codex'),
      runner: readOptionValue(args, '--runner'),
    });
    if (positional.value === 'run' || positional.value === 'daemon') {
      maybePrintOptionalLatexNotice(home);
    }
    if (positional.value === 'run' || positional.value === 'daemon') {
      const selectedRunner = String(readOptionValue(args, '--runner') || readConfiguredDefaultRunner(home, "codex")).trim().toLowerCase() || "codex";
      const bootstrapState = selectedRunner === "codex"
        ? readCodexBootstrapState(home, runtimePython, codexOverrideEnv)
        : readRunnerBootstrapState(home, runtimePython, selectedRunner, codexOverrideEnv);
      const runnerReady = selectedRunner === "codex" ? Boolean(bootstrapState.codex_ready) : Boolean(bootstrapState.ready);
      if (!runnerReady) {
        try {
          const probe = selectedRunner === "codex"
            ? probeCodexBootstrap(home, runtimePython, codexOverrideEnv)
            : probeRunnerBootstrap(home, runtimePython, selectedRunner, codexOverrideEnv);
          if (!probe || probe.ok !== true) {
            throw createRunnerPreflightError(home, selectedRunner, probe);
          }
        } catch (error) {
          if (handleRunnerPreflightFailure(error)) return;
          throw error;
        }
      }
    }
    const result = runPythonCli(runtimePython, normalizePythonCliArgs(args, home), {
      allowFailure: true,
      env: codexOverrideEnv,
    });
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
    resolveManagementHome,
    parseLauncherArgs,
    generateBrowserAuthToken,
    appendBrowserAuthToken,
    normalizeProxyUrl,
    buildCodeOnlyUninstallPlan,
    parseMigrateArgs,
    parseLegacyWrapperCandidate,
    repairLegacyPathWrappers,
    useEditableProjectInstall,
    compareVersions,
    detectInstallMode,
    buildUvSyncFailureGuidance,
    updateManualCommand,
    buildUpdateStatus,
    buildDaemonStatusPayload,
    parseYesNoAnswer,
    normalizeLauncherRelaunchArgs,
    officialRepositoryLine,
    stripAnsi,
    normalizeLegacyHostFlagArgs,
    runGlobalNpmUninstall,
  },
};

if (require.main === module) {
  main().catch((error) => {
    console.error(error instanceof Error ? error.message : String(error));
    process.exit(1);
  });
}
