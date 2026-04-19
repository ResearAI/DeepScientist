#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

E2E_UI_TEST_SCRIPT="test:e2e:workspace-tooltip" \
  bash "$ROOT_DIR/scripts/run_copilot_workspace_e2e.sh"
