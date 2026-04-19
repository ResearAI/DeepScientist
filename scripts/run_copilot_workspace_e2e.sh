#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="${E2E_RUNTIME_DIR:-$(mktemp -d "${TMPDIR:-/tmp}/ds-copilot-workspace-e2e.XXXXXX")}"
HOME_DIR="${E2E_HOME_DIR:-$RUNTIME_DIR/home}"
FIXTURE_JSON="$RUNTIME_DIR/fixture.json"
BIND_HOST="${E2E_BIND_HOST:-${E2E_HOST:-0.0.0.0}}"
CONNECT_HOST="${E2E_CONNECT_HOST:-${E2E_HOST:-127.0.0.1}}"
PORT="${E2E_PORT:-32997}"
BASE_URL="http://${CONNECT_HOST}:${PORT}"
DAEMON_LOG="$RUNTIME_DIR/daemon.log"
UI_TEST_SCRIPT="${E2E_UI_TEST_SCRIPT:-test:e2e:copilot-workspace}"
PLAYWRIGHT_PROJECT="${E2E_PLAYWRIGHT_PROJECT:-chromium}"
PLAYWRIGHT_ARGS="${E2E_PLAYWRIGHT_ARGS:-}"

export PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"

cleanup() {
  local exit_code=$?
  if [[ -n "${DAEMON_PID:-}" ]]; then
    kill "$DAEMON_PID" >/dev/null 2>&1 || true
    wait "$DAEMON_PID" >/dev/null 2>&1 || true
  fi
  if [[ "${E2E_KEEP_RUNTIME:-0}" != "1" ]]; then
    rm -rf "$RUNTIME_DIR"
  else
    echo "E2E runtime preserved at: $RUNTIME_DIR"
  fi
  return "$exit_code"
}
trap cleanup EXIT

python "$ROOT_DIR/scripts/setup_copilot_workspace_e2e_fixture.py" \
  --home "$HOME_DIR" \
  --output "$FIXTURE_JSON"

npm --prefix "$ROOT_DIR/src/ui" run build

python -m deepscientist.cli --home "$HOME_DIR" daemon --host "$BIND_HOST" --port "$PORT" --auth false >"$DAEMON_LOG" 2>&1 &
DAEMON_PID=$!

python - "$BASE_URL" <<'PY'
import sys
import time
from urllib.request import urlopen

base_url = sys.argv[1]
deadline = time.time() + 120
last_error = None
while time.time() < deadline:
    try:
        with urlopen(base_url, timeout=2) as response:  # noqa: S310
            if response.status == 200:
                raise SystemExit(0)
    except Exception as exc:
        last_error = exc
        time.sleep(1)
print(f"Daemon did not become ready at {base_url}: {last_error}", file=sys.stderr)
raise SystemExit(1)
PY

E2E_BASE_URL="$BASE_URL" \
E2E_FIXTURE_JSON="$FIXTURE_JSON" \
npm --prefix "$ROOT_DIR/src/ui" run "$UI_TEST_SCRIPT" -- --reporter=list --project="$PLAYWRIGHT_PROJECT" $PLAYWRIGHT_ARGS
