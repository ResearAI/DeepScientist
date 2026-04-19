#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

E2E_UI_TEST_SCRIPT="test:e2e:settings-control" \
  bash "$ROOT_DIR/scripts/run_admin_e2e.sh"
