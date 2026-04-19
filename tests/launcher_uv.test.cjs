const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const { __internal } = require('../bin/ds.js');

test('createPythonRuntimePlan prefers a valid active conda interpreter', () => {
  const plan = __internal.createPythonRuntimePlan({
    condaProbes: [
      {
        ok: true,
        executable: '/opt/conda/envs/ds311/bin/python',
        realExecutable: '/opt/conda/envs/ds311/bin/python',
        version: '3.11.9',
        major: 3,
        minor: 11,
        patch: 9,
        source: 'conda',
        sourceLabel: 'conda:ds311',
      },
    ],
    pathProbes: [
      {
        ok: true,
        executable: '/usr/bin/python3',
        realExecutable: '/usr/bin/python3',
        version: '3.12.2',
        major: 3,
        minor: 12,
        patch: 2,
        source: 'path',
        sourceLabel: 'path',
      },
    ],
    minimumVersionRequest: '3.11',
  });

  assert.equal(plan.runtimeKind, 'system');
  assert.equal(plan.source, 'conda');
  assert.equal(plan.selectedProbe.executable, '/opt/conda/envs/ds311/bin/python');
});

test('createPythonRuntimePlan falls back to uv-managed python when active conda is too old', () => {
  const plan = __internal.createPythonRuntimePlan({
    condaProbes: [
      {
        ok: true,
        executable: '/opt/conda/envs/legacy/bin/python',
        realExecutable: '/opt/conda/envs/legacy/bin/python',
        version: '3.10.14',
        major: 3,
        minor: 10,
        patch: 14,
        source: 'conda',
        sourceLabel: 'conda:legacy',
      },
    ],
    pathProbes: [
      {
        ok: true,
        executable: '/usr/bin/python3',
        realExecutable: '/usr/bin/python3',
        version: '3.12.2',
        major: 3,
        minor: 12,
        patch: 2,
        source: 'path',
        sourceLabel: 'path',
      },
    ],
    minimumVersionRequest: '3.11',
  });

  assert.equal(plan.runtimeKind, 'managed');
  assert.equal(plan.source, 'conda');
  assert.equal(plan.rejectedProbe.version, '3.10.14');
  assert.equal(plan.minimumVersionRequest, '3.11');
});

test('buildUvRuntimeEnv pins uv state inside the DeepScientist runtime tree', () => {
  const home = path.join(path.sep, 'tmp', 'DeepScientistHome');
  const env = __internal.buildUvRuntimeEnv(home, {
    EXTRA_MARKER: '1',
    PYTHONPATH: '/tmp/pythonpath',
    PYTHONHOME: '/tmp/pythonhome',
    VIRTUAL_ENV: '/tmp/venv',
    __PYVENV_LAUNCHER__: '/tmp/launcher',
    CONDA_PREFIX: '/opt/conda',
    CONDA_DEFAULT_ENV: 'base',
    CONDA_SHLVL: '1',
    CONDA_PREFIX_1: '/opt/conda',
    CONDA_PROMPT_MODIFIER: '(base) ',
    CONDA_EXE: '/opt/conda/bin/conda',
    CONDA_PYTHON_EXE: '/opt/conda/bin/python',
  });

  assert.equal(env.EXTRA_MARKER, '1');
  assert.equal(env.UV_PROJECT_ENVIRONMENT, path.join(home, 'runtime', 'python-env'));
  assert.equal(env.UV_CACHE_DIR, path.join(home, 'runtime', 'uv-cache'));
  assert.equal(env.UV_PYTHON_INSTALL_DIR, path.join(home, 'runtime', 'python'));
  assert.equal(env.PYTHONPATH, undefined);
  assert.equal(env.PYTHONHOME, undefined);
  assert.equal(env.VIRTUAL_ENV, undefined);
  assert.equal(env.__PYVENV_LAUNCHER__, undefined);
  assert.equal(env.CONDA_PREFIX, undefined);
  assert.equal(env.CONDA_DEFAULT_ENV, undefined);
  assert.equal(env.CONDA_SHLVL, undefined);
  assert.equal(env.CONDA_PREFIX_1, undefined);
  assert.equal(env.CONDA_PROMPT_MODIFIER, undefined);
  assert.equal(env.CONDA_EXE, undefined);
  assert.equal(env.CONDA_PYTHON_EXE, undefined);
});

test('buildUvSyncFailureGuidance points npm installs away from uv lock by default', () => {
  const guidance = __internal.buildUvSyncFailureGuidance({
    installMode: 'npm-package',
    env: {},
  });

  assert.match(guidance.join('\n'), /already includes a locked `uv\.lock`/);
  assert.doesNotMatch(guidance.join('\n'), /run `uv lock`/);
});

test('buildUvSyncFailureGuidance suggests uv lock for source checkouts', () => {
  const guidance = __internal.buildUvSyncFailureGuidance({
    installMode: 'source-checkout',
    env: {},
  });

  assert.match(guidance.join('\n'), /run `uv lock`/);
});

test('buildUvSyncFailureGuidance surfaces Python and package-index env pollution', () => {
  const guidance = __internal.buildUvSyncFailureGuidance({
    installMode: 'npm-package',
    env: {
      CONDA_PREFIX: '/opt/conda',
      PYTHONPATH: '/tmp/pythonpath',
      PIP_INDEX_URL: 'https://mirror.example/simple',
      HTTPS_PROXY: 'http://127.0.0.1:8080',
    },
  });

  const text = guidance.join('\n');
  assert.match(text, /active Python environment was detected/i);
  assert.match(text, /Custom package index settings were detected/i);
  assert.match(text, /Proxy or certificate overrides were detected/i);
});

test('runtimePythonPath resolves to the managed uv environment interpreter', () => {
  const home = path.join(path.sep, 'tmp', 'DeepScientistHome');
  const interpreter = __internal.runtimePythonPath(home);

  assert.ok(interpreter.includes(path.join('runtime', 'python-env')));
  assert.ok(
    interpreter.endsWith(path.join('bin', 'python'))
      || interpreter.endsWith(path.join('Scripts', 'python.exe'))
  );
});

test('compareVersions follows semantic numeric ordering', () => {
  assert.equal(__internal.compareVersions('1.5.2', '1.5.2'), 0);
  assert.equal(__internal.compareVersions('1.5.3', '1.5.2'), 1);
  assert.equal(__internal.compareVersions('1.6.0', '1.12.0'), -1);
});

test('detectInstallMode distinguishes npm packages from source checkouts', () => {
  assert.equal(
    __internal.detectInstallMode(path.join(path.sep, 'usr', 'lib', 'node_modules', '@researai', 'deepscientist')),
    'npm-package'
  );
  assert.equal(
    __internal.detectInstallMode(path.join(path.sep, 'ssdwork', 'deepscientist', 'DeepScientist')),
    'source-checkout'
  );
});

test('updateManualCommand always points users to the npm upgrade command', () => {
  assert.equal(
    __internal.updateManualCommand('npm-package'),
    'npm install -g @researai/deepscientist@latest'
  );
  assert.equal(
    __internal.updateManualCommand('source-checkout'),
    'npm install -g @researai/deepscientist@latest'
  );
});

test('buildUpdateStatus only auto-prompts once per target version', () => {
  const status = __internal.buildUpdateStatus('/tmp/ds-update-state', {
    current_version: '1.5.4',
    latest_version: '1.5.5',
    last_prompted_version: '1.5.5',
    busy: false,
  });

  assert.equal(status.update_available, true);
  assert.equal(status.prompt_recommended, false);

  const nextStatus = __internal.buildUpdateStatus('/tmp/ds-update-state', {
    current_version: '1.5.4',
    latest_version: '1.5.6',
    last_prompted_version: '1.5.5',
    busy: false,
  });

  assert.equal(nextStatus.update_available, true);
  assert.equal(nextStatus.prompt_recommended, true);
});

test('buildUpdateStatus suppresses stale busy state when the target is not newer', () => {
  const status = __internal.buildUpdateStatus('/tmp/ds-update-state', {
    current_version: '1.5.7',
    latest_version: '1.5.7',
    target_version: '1.5.3',
    busy: true,
  });

  assert.equal(status.update_available, false);
  assert.equal(status.busy, false);
  assert.equal(status.target_version, null);
});

test('parseYesNoAnswer accepts y/yes and n/no with a default fallback', () => {
  assert.equal(__internal.parseYesNoAnswer('y', false), true);
  assert.equal(__internal.parseYesNoAnswer('YES', false), true);
  assert.equal(__internal.parseYesNoAnswer('n', true), false);
  assert.equal(__internal.parseYesNoAnswer('No', true), false);
  assert.equal(__internal.parseYesNoAnswer('', false), false);
  assert.equal(__internal.parseYesNoAnswer('maybe', true), true);
});

test('normalizeLauncherRelaunchArgs rewrites home flags and appends --skip-update-check', () => {
  const args = __internal.normalizeLauncherRelaunchArgs(
    ['--here', '--port', '20999', '--home', '/tmp/old-home', '--both'],
    '/tmp/new-home'
  );

  assert.deepEqual(args, ['--home', '/tmp/new-home', '--port', '20999', '--both', '--skip-update-check']);
});

test('officialRepositoryLine points to the public GitHub repository', () => {
  assert.equal(
    __internal.stripAnsi(__internal.officialRepositoryLine()),
    'Official open-source repository: https://github.com/ResearAI/DeepScientist'
  );
});

test('resolveUvBinary prefers the DeepScientist-local uv install over PATH', () => {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'ds-uv-home-'));
  const localUv = __internal.runtimeUvBinaryPath(home);
  fs.mkdirSync(path.dirname(localUv), { recursive: true });
  fs.writeFileSync(localUv, '#!/usr/bin/env bash\nexit 0\n', { encoding: 'utf8', mode: 0o755 });

  const pathBin = fs.mkdtempSync(path.join(os.tmpdir(), 'ds-uv-path-'));
  const pathUv = path.join(pathBin, process.platform === 'win32' ? 'uv.cmd' : 'uv');
  fs.writeFileSync(pathUv, process.platform === 'win32' ? '@echo off\r\nexit /b 0\r\n' : '#!/usr/bin/env bash\nexit 0\n', {
    encoding: 'utf8',
    mode: 0o755,
  });

  const originalPath = process.env.PATH;
  delete process.env.DEEPSCIENTIST_UV;
  delete process.env.UV_BIN;
  process.env.PATH = pathBin;
  try {
    const resolved = __internal.resolveUvBinary(home);
    assert.equal(resolved.path, localUv);
    assert.equal(resolved.source, 'local');
  } finally {
    if (typeof originalPath === 'string') {
      process.env.PATH = originalPath;
    } else {
      delete process.env.PATH;
    }
    fs.rmSync(home, { recursive: true, force: true });
    fs.rmSync(pathBin, { recursive: true, force: true });
  }
});

test('parseMigrateArgs accepts target, --yes, and --restart', () => {
  const parsed = __internal.parseMigrateArgs(['migrate', '/tmp/ds-target', '--yes', '--restart']);
  assert.equal(parsed.target, path.resolve('/tmp/ds-target'));
  assert.equal(parsed.yes, true);
  assert.equal(parsed.restart, true);
});

test('resolveHome uses ./DeepScientist under the current working directory when --here is present', () => {
  const originalCwd = process.cwd();
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ds-here-'));
  process.chdir(tempDir);
  try {
    assert.equal(__internal.resolveHome(['--here']), path.join(tempDir, 'DeepScientist'));
  } finally {
    process.chdir(originalCwd);
    fs.rmSync(tempDir, { recursive: true, force: true });
  }
});

test('resolveManagementHome prefers ./DeepScientist when the current directory has managed daemon state', () => {
  const originalCwd = process.cwd();
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ds-manage-here-'));
  const hereHome = path.join(tempDir, 'DeepScientist');
  fs.mkdirSync(path.join(hereHome, 'runtime'), { recursive: true });
  fs.writeFileSync(
    path.join(hereHome, 'runtime', 'daemon.json'),
    `${JSON.stringify({ daemon_id: 'daemon-here', pid: 12345, home: hereHome }, null, 2)}\n`,
    'utf8'
  );
  process.chdir(tempDir);
  try {
    assert.equal(__internal.resolveManagementHome(['--stop'], { stop: true }), hereHome);
  } finally {
    process.chdir(originalCwd);
    fs.rmSync(tempDir, { recursive: true, force: true });
  }
});

test('resolveManagementHome falls back to the only indexed managed home when no explicit selector is present', () => {
  const tempHome = fs.mkdtempSync(path.join(os.tmpdir(), 'ds-manage-index-'));
  const tempUserHome = fs.mkdtempSync(path.join(os.tmpdir(), 'ds-manage-userhome-'));
  const indexRoot = path.join(os.homedir(), '.deepscientist');
  const indexPath = path.join(indexRoot, 'install-index.json');
  const backupPath = `${indexPath}.bak-test`;
  const hadIndex = fs.existsSync(indexPath);
  const originalHome = process.env.HOME;
  const originalUserProfile = process.env.USERPROFILE;
  if (hadIndex) {
    fs.copyFileSync(indexPath, backupPath);
  }
  process.env.HOME = tempUserHome;
  process.env.USERPROFILE = tempUserHome;
  const redirectedIndexRoot = path.join(tempUserHome, '.deepscientist');
  const redirectedIndexPath = path.join(redirectedIndexRoot, 'install-index.json');
  fs.mkdirSync(path.join(tempHome, 'runtime'), { recursive: true });
  fs.writeFileSync(
    path.join(tempHome, 'runtime', 'daemon.json'),
    `${JSON.stringify({ daemon_id: 'daemon-index', pid: 23456, home: tempHome }, null, 2)}\n`,
    'utf8'
  );
  fs.mkdirSync(redirectedIndexRoot, { recursive: true });
  fs.writeFileSync(
    redirectedIndexPath,
    `${JSON.stringify({ installs: [{ home: tempHome, package_root: '/tmp/repo', launcher_path: '/tmp/repo/bin/ds.js' }] }, null, 2)}\n`,
    'utf8'
  );
  try {
    assert.equal(__internal.resolveManagementHome(['--stop'], { stop: true }), tempHome);
  } finally {
    if (typeof originalHome === 'string') process.env.HOME = originalHome;
    else delete process.env.HOME;
    if (typeof originalUserProfile === 'string') process.env.USERPROFILE = originalUserProfile;
    else delete process.env.USERPROFILE;
    if (hadIndex) {
      fs.copyFileSync(backupPath, indexPath);
      fs.rmSync(backupPath, { force: true });
    } else {
      fs.rmSync(indexPath, { force: true });
    }
    fs.rmSync(tempHome, { recursive: true, force: true });
    fs.rmSync(tempUserHome, { recursive: true, force: true });
  }
});

test('parseLauncherArgs accepts --proxy without treating its URL as a positional command', () => {
  const parsed = __internal.parseLauncherArgs([
    '--port',
    '8890',
    '--here',
    '--proxy',
    'http://127.0.0.1:58887',
  ]);

  assert.equal(parsed.port, 8890);
  assert.equal(parsed.proxy, 'http://127.0.0.1:58887');
});

test('parseLauncherArgs accepts --auth false for password-free local launches', () => {
  const parsed = __internal.parseLauncherArgs([
    '--auth',
    'false',
    '--port',
    '8890',
  ]);

  assert.equal(parsed.port, 8890);
  assert.equal(parsed.auth, false);
});

test('launcher defaults browser auth to false when --auth is omitted', () => {
  const parsed = __internal.parseLauncherArgs(['--port', '8890']);

  assert.equal(parsed.port, 8890);
  assert.equal(parsed.auth, null);
  assert.equal(parsed.auth === null ? false : parsed.auth !== false, false);
});

test('normalizeLegacyHostFlagArgs rewrites --ip to --host and emits a warning', () => {
  const normalized = __internal.normalizeLegacyHostFlagArgs([
    '--ip',
    '0.0.0.0',
    '--port',
    '8890',
  ]);

  assert.deepEqual(normalized.args, ['--host', '0.0.0.0', '--port', '8890']);
  assert.equal(normalized.warnings.length, 1);
  assert.match(normalized.warnings[0], /--host/);
  assert.match(normalized.warnings[0], /127\.0\.0\.1/);
});

test('parseLauncherArgs rejects unknown launcher flags instead of falling through silently', () => {
  const parsed = __internal.parseLauncherArgs(['--bogus']);

  assert.equal(parsed.help, false);
  assert.equal(parsed.error, 'Unknown launcher flag: --bogus');
});

test('parseLauncherArgs rejects invalid launcher option values clearly', () => {
  assert.equal(
    __internal.parseLauncherArgs(['--port', 'abc']).error,
    'Invalid value for --port: abc. Expected an integer between 1 and 65535.'
  );
  assert.equal(
    __internal.parseLauncherArgs(['--mode', 'desktop']).error,
    'Invalid value for --mode: desktop. Expected one of: web, tui, both.'
  );
  assert.equal(
    __internal.parseLauncherArgs(['--auth', 'maybe']).error,
    'Invalid value for --auth: maybe. Use true or false.'
  );
});

test('browser auth helpers generate 16-character tokens and append them to URLs', () => {
  const token = __internal.generateBrowserAuthToken();
  assert.equal(token.length, 16);
  assert.match(token, /^[a-f0-9]{16}$/);
  assert.equal(
    __internal.appendBrowserAuthToken('http://127.0.0.1:20999/projects/q-001', token),
    `http://127.0.0.1:20999/projects/q-001?token=${token}`
  );
});

test('parseLauncherArgs accepts --runner for selecting a non-Codex backend', () => {
  const parsed = __internal.parseLauncherArgs(['--runner', 'claude', '--port', '20999']);

  assert.equal(parsed.error, null);
  assert.equal(parsed.runner, 'claude');
});

test('parseLauncherArgs accepts --codex-profile for provider-backed Codex setups', () => {
  const parsed = __internal.parseLauncherArgs([
    '--port',
    '8890',
    '--codex-profile',
    'm27',
  ]);

  assert.equal(parsed.port, 8890);
  assert.equal(parsed.codexProfile, 'm27');
});

test('parseLauncherArgs accepts --codex for a one-off Codex binary override', () => {
  const parsed = __internal.parseLauncherArgs([
    '--codex',
    '/tmp/codex057-wrapper',
    '--port',
    '8890',
  ]);

  assert.equal(parsed.port, 8890);
  assert.equal(parsed.codexBinary, '/tmp/codex057-wrapper');
});

test('repairLegacyPathWrappers rewrites old install wrappers to the current npm launcher', () => {
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ds-wrapper-repair-'));
  const launcherPath = path.join(tempDir, 'global-ds.js');
  const wrapperDir = path.join(tempDir, 'bin');
  const wrapperPath = path.join(wrapperDir, 'ds');
  const home = path.join(path.sep, 'tmp', 'DeepScientistHome');

  fs.mkdirSync(wrapperDir, { recursive: true });
  fs.writeFileSync(launcherPath, '#!/usr/bin/env node\n', { encoding: 'utf8', mode: 0o755 });
  fs.writeFileSync(
    wrapperPath,
    [
      '#!/usr/bin/env bash',
      'set -euo pipefail',
      'if [ -z "${DEEPSCIENTIST_HOME:-}" ]; then',
      `  export DEEPSCIENTIST_HOME="${home}"`,
      'fi',
      `exec "${path.join(home, 'cli', 'bin', 'ds')}" "$@"`,
      '',
    ].join('\n'),
    { encoding: 'utf8', mode: 0o755 }
  );

  const originalPath = process.env.PATH;
  process.env.PATH = wrapperDir;
  try {
    const rewritten = __internal.repairLegacyPathWrappers({
      home,
      launcherPath,
      force: true,
    });
    assert.deepEqual(rewritten, [wrapperPath]);
    const content = fs.readFileSync(wrapperPath, 'utf8');
    assert.match(content, new RegExp(home.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
    assert.match(content, new RegExp(launcherPath.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
    assert.doesNotMatch(content, /\/cli\/bin\/ds/);
  } finally {
    if (typeof originalPath === 'string') {
      process.env.PATH = originalPath;
    } else {
      delete process.env.PATH;
    }
    fs.rmSync(tempDir, { recursive: true, force: true });
  }
});

test('buildDaemonStatusPayload includes launcher and daemon state paths for diagnostics', () => {
  const home = path.join(path.sep, 'tmp', 'DeepScientistHome');
  const launcherPath = path.join(path.sep, 'tmp', 'bin', 'ds.js');
  const state = {
    daemon_id: 'daemon-123',
    home,
    auth_enabled: true,
    auth_token: 'abcd1234',
  };
  const health = {
    status: 'ok',
    home,
    daemon_id: 'daemon-123',
  };

  const payload = __internal.buildDaemonStatusPayload({
    home,
    url: 'http://127.0.0.1:20999',
    state,
    health,
    launcherPath,
  });

  assert.equal(payload.healthy, true);
  assert.equal(payload.identity_match, true);
  assert.equal(payload.managed, true);
  assert.equal(payload.home, home);
  assert.equal(payload.url, 'http://127.0.0.1:20999');
  assert.equal(payload.daemon_state_path, path.join(home, 'runtime', 'daemon.json'));
  assert.equal(payload.launcher_path, launcherPath);
  assert.equal(payload.daemon, state);
  assert.equal(payload.health, health);
});

test('buildCodeOnlyUninstallPlan removes runtime code but preserves local data', () => {
  const home = path.join(path.sep, 'tmp', 'DeepScientistHome');
  const installDir = path.join(home, 'cli');
  const wrapperPath = path.join(path.sep, 'tmp', 'bin', 'ds');

  const plan = __internal.buildCodeOnlyUninstallPlan({
    home,
    installDir,
    wrapperPaths: [wrapperPath],
  });

  assert.deepEqual(plan.wrapper_paths, [wrapperPath]);
  assert.deepEqual(
    plan.remove_paths,
    [
      path.join(home, 'cli'),
      path.join(home, 'runtime', 'bundle'),
      path.join(home, 'runtime', 'daemon.json'),
      path.join(home, 'runtime', 'python'),
      path.join(home, 'runtime', 'python-env'),
      path.join(home, 'runtime', 'tools'),
    ]
  );
  assert.deepEqual(
    plan.preserve_paths,
    [
      path.join(home, 'cache'),
      path.join(home, 'config'),
      path.join(home, 'logs'),
      path.join(home, 'memory'),
      path.join(home, 'plugins'),
      path.join(home, 'quests'),
    ]
  );
});

test('runGlobalNpmUninstall respects npm_config_prefix for npm-package installs', () => {
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ds-uninstall-prefix-'));
  const binDir = path.join(tempDir, 'bin');
  fs.mkdirSync(binDir, { recursive: true });
  const npmStub = path.join(binDir, process.platform === 'win32' ? 'npm.cmd' : 'npm');
  const capturePath = path.join(tempDir, 'capture.json');
  if (process.platform === 'win32') {
    fs.writeFileSync(
      npmStub,
      `@echo off\r\nnode -e "require('node:fs').writeFileSync(process.argv[1], JSON.stringify(process.argv.slice(2)))" "${capturePath}" %*\r\nexit /b 0\r\n`,
      { encoding: 'utf8', mode: 0o755 }
    );
  } else {
    fs.writeFileSync(
      npmStub,
      [
        '#!/usr/bin/env bash',
        'set -euo pipefail',
        `node -e 'require(\"node:fs\").writeFileSync(process.argv[1], JSON.stringify(process.argv.slice(2)))' "${capturePath}" "$@"`,
        '',
      ].join('\n'),
      { encoding: 'utf8', mode: 0o755 }
    );
  }
  const originalPath = process.env.PATH;
  const originalPrefix = process.env.npm_config_prefix;
  process.env.PATH = `${binDir}${path.delimiter}${originalPath || ''}`;
  process.env.npm_config_prefix = '/tmp/custom-prefix';
  try {
    const result = __internal.runGlobalNpmUninstall();
    assert.equal(result.ok, true);
    const args = JSON.parse(fs.readFileSync(capturePath, 'utf8'));
    assert.deepEqual(args, ['uninstall', '-g', '@researai/deepscientist', '--prefix', '/tmp/custom-prefix']);
  } finally {
    if (typeof originalPath === 'string') process.env.PATH = originalPath;
    else delete process.env.PATH;
    if (typeof originalPrefix === 'string') process.env.npm_config_prefix = originalPrefix;
    else delete process.env.npm_config_prefix;
    fs.rmSync(tempDir, { recursive: true, force: true });
  }
});
