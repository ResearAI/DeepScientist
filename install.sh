#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="$SCRIPT_DIR"
DEFAULT_BASE_DIR="${DEEPSCIENTIST_BASE_DIR:-${DEEPSCIENTIST_HOME:-$HOME/DeepScientist}}"
ENV_INSTALL_DIR="${DEEPSCIENTIST_INSTALL_DIR:-}"
ENV_BIN_DIR="${DEEPSCIENTIST_BIN_DIR:-}"
ENV_WITH_TINYTEX="${DEEPSCIENTIST_WITH_TINYTEX:-}"
BASE_DIR="$DEFAULT_BASE_DIR"
INSTALL_DIR=""
BIN_DIR="${ENV_BIN_DIR:-$HOME/.local/bin}"
WITH_TINYTEX=0
DIR_SET=0
INSTALL_DIR_SET=0
BIN_DIR_SET=0

usage() {
  cat <<'EOF'
DeepScientist installer

Usage:
  bash install.sh [--dir BASE_DIR] [--install-dir INSTALL_DIR] [--bin-dir BIN_DIR] [--with-tinytex]

Options:
  --dir PATH          Base install directory. Code is installed into PATH/cli.
  --install-dir PATH  Exact install directory for the bundled CLI tree.
  --bin-dir PATH      Directory for launcher wrappers.
  --with-tinytex      Also install a lightweight TinyTeX pdflatex runtime after DeepScientist is installed.
  -h, --help          Show this help message.

Defaults:
  Base install dir: ~/DeepScientist
  Install dir:      ~/DeepScientist/cli
  Bin dir:          ~/.local/bin

Notes:
  - This installer deploys the current working tree into a separate install directory.
  - Runtime data lives under ~/DeepScientist by default.
  - `DEEPSCIENTIST_BASE_DIR`, `DEEPSCIENTIST_INSTALL_DIR`, `DEEPSCIENTIST_BIN_DIR`,
    and `DEEPSCIENTIST_WITH_TINYTEX`
    can be used from `npm run install:local` as well.
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --dir)
      if [ -z "${2:-}" ]; then
        echo "--dir requires a path" >&2
        exit 1
      fi
      BASE_DIR="$2"
      DIR_SET=1
      shift 2
      ;;
    --install-dir)
      if [ -z "${2:-}" ]; then
        echo "--install-dir requires a path" >&2
        exit 1
      fi
      INSTALL_DIR="$2"
      INSTALL_DIR_SET=1
      shift 2
      ;;
    --bin-dir)
      if [ -z "${2:-}" ]; then
        echo "--bin-dir requires a path" >&2
        exit 1
      fi
      BIN_DIR="$2"
      BIN_DIR_SET=1
      shift 2
      ;;
    --with-tinytex)
      WITH_TINYTEX=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [ "$WITH_TINYTEX" -eq 0 ]; then
  case "$(printf '%s' "$ENV_WITH_TINYTEX" | tr '[:upper:]' '[:lower:]')" in
    1|true|yes|on)
      WITH_TINYTEX=1
      ;;
  esac
fi

if [ "$DIR_SET" -eq 1 ] && [ "$INSTALL_DIR_SET" -eq 1 ]; then
  echo "--dir and --install-dir cannot be used together" >&2
  exit 1
fi

if [ "$INSTALL_DIR_SET" -eq 1 ]; then
  BASE_DIR="$(dirname "$INSTALL_DIR")"
elif [ "$DIR_SET" -eq 1 ]; then
  INSTALL_DIR="$BASE_DIR/cli"
elif [ -n "$ENV_INSTALL_DIR" ]; then
  INSTALL_DIR="$ENV_INSTALL_DIR"
  BASE_DIR="$(dirname "$INSTALL_DIR")"
else
  INSTALL_DIR="$BASE_DIR/cli"
fi

if [ "$DIR_SET" -eq 1 ] && [ "$BIN_DIR_SET" -eq 0 ] && [ -z "$ENV_BIN_DIR" ]; then
  BIN_DIR="$BASE_DIR/bin"
fi

print_step() {
  printf '[install] %s\n' "$1"
}

has_optional_latex_compiler() {
  local compiler
  for compiler in pdflatex xelatex lualatex; do
    if command -v "$compiler" >/dev/null 2>&1; then
      return 0
    fi
  done
  return 1
}

print_optional_latex_notice() {
  if has_optional_latex_compiler; then
    local detected=""
    if command -v pdflatex >/dev/null 2>&1; then
      detected="pdflatex"
    elif command -v xelatex >/dev/null 2>&1; then
      detected="xelatex"
    else
      detected="lualatex"
    fi
    printf 'Optional LaTeX runtime: detected `%s` on PATH.\n' "$detected"
    return
  fi

  printf '\n'
  printf 'Optional LaTeX runtime: not detected.\n'
  printf 'DeepScientist still installs and runs normally.\n'
  printf 'You only need LaTeX if you want to compile paper PDFs locally from the web workspace.\n'
  printf 'Recommended lightweight option:\n'
  printf '  %s latex install-runtime\n' "$BIN_DIR/ds"
  printf '\n'
  printf 'System package alternatives:\n'

  if command -v apt-get >/dev/null 2>&1; then
    printf '  Debian/Ubuntu:\n'
    printf '  sudo apt-get update && sudo apt-get install -y texlive-latex-base texlive-latex-recommended texlive-fonts-recommended texlive-bibtex-extra\n'
  elif command -v dnf >/dev/null 2>&1; then
    printf '  Fedora/RHEL:\n'
    printf '  sudo dnf install -y texlive-scheme-basic texlive-collection-latex texlive-bibtex\n'
  elif command -v yum >/dev/null 2>&1; then
    printf '  CentOS/RHEL:\n'
    printf '  sudo yum install -y texlive-scheme-basic texlive-collection-latex texlive-bibtex\n'
  elif command -v pacman >/dev/null 2>&1; then
    printf '  Arch Linux:\n'
    printf '  sudo pacman -S --needed texlive-basic texlive-latex\n'
  elif command -v brew >/dev/null 2>&1; then
    printf '  macOS with Homebrew:\n'
    printf '  brew install --cask mactex-no-gui\n'
  else
    printf '  Install a TeX distribution that provides `pdflatex` and `bibtex`.\n'
  fi
}

resolve_path() {
  if command -v python3 >/dev/null 2>&1; then
    python3 - "$1" <<'PY'
import os
import sys
print(os.path.realpath(sys.argv[1]))
PY
    return
  fi
  if command -v python >/dev/null 2>&1; then
    python - "$1" <<'PY'
import os
import sys
print(os.path.realpath(sys.argv[1]))
PY
    return
  fi
  if command -v realpath >/dev/null 2>&1; then
    realpath "$1" 2>/dev/null || echo "$1"
    return
  fi
  echo "$1"
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

safe_remove_dir() {
  local target="$1"
  if [ -z "$target" ] || [ "$target" = "/" ] || [ "$target" = "$HOME" ]; then
    echo "Refusing to remove directory: $target" >&2
    exit 1
  fi
  rm -rf "$target"
}

stop_existing_install() {
  if [ -x "$INSTALL_DIR/bin/ds" ]; then
    "$INSTALL_DIR/bin/ds" --stop >/dev/null 2>&1 || true
    return
  fi
  if [ -f "$INSTALL_DIR/bin/ds.js" ]; then
    node "$INSTALL_DIR/bin/ds.js" --stop >/dev/null 2>&1 || true
  fi
}

copy_source_tree() {
  local target="$1"
  mkdir -p "$target"
  if command -v tar >/dev/null 2>&1; then
    tar -C "$SOURCE_ROOT" -cf - \
      --exclude='./.git' \
      --exclude='./.pytest_cache' \
      --exclude='./node_modules' \
      --exclude='./ui' \
      --exclude='./src/ui/node_modules' \
      --exclude='./src/ui/lib/node_modules' \
      --exclude='./src/tui/node_modules' \
      --exclude='./src/deepscientist.egg-info' \
      . | tar -C "$target" -xf -
  else
    cp -R "$SOURCE_ROOT"/. "$target"/
  fi
}

prune_tree() {
  local target="$1"
  rm -rf \
    "$target/.git" \
    "$target/.pytest_cache" \
    "$target/node_modules" \
    "$target/ui" \
    "$target/src/ui/node_modules" \
    "$target/src/ui/lib/node_modules" \
    "$target/src/tui/node_modules" \
    "$target/src/deepscientist.egg-info"
  find "$target" -type d -name '__pycache__' -prune -exec rm -rf {} +
  find "$target" -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete
}

build_ui() {
  if should_use_prebuilt_bundle "$1/src/ui" "$1/src/ui/dist" "index.html" "${DEEPSCIENTIST_FORCE_UI_BUILD:-}"; then
    print_step "Using up-to-date web UI bundle from source tree"
    return
  fi
  print_step "Building web UI in install tree"
  npm --prefix "$1/src/ui" install --include=dev --no-audit --no-fund
  npm --prefix "$1/src/ui" run build
  rm -rf "$1/src/ui/node_modules" "$1/src/ui/lib/node_modules"
}

install_root_runtime() {
  print_step "Installing root runtime dependencies in install tree"
  npm --prefix "$1" install --omit=dev --no-audit --no-fund
}

build_tui() {
  local tui_entry=""
  if [ -f "$1/src/tui/dist/index.js" ]; then
    tui_entry="index.js"
  elif [ -f "$1/src/tui/dist/index.cjs" ]; then
    tui_entry="index.cjs"
  elif [ -d "$1/src/tui/dist/components" ]; then
    tui_entry="components"
  fi
  if [ -n "$tui_entry" ] && should_use_prebuilt_bundle "$1/src/tui" "$1/src/tui/dist" "$tui_entry" "${DEEPSCIENTIST_FORCE_TUI_BUILD:-}"; then
    print_step "Using up-to-date TUI bundle from source tree"
    return
  fi
  print_step "Building TUI in install tree"
  npm --prefix "$1/src/tui" install --include=dev --no-audit --no-fund
  npm --prefix "$1/src/tui" run build
  npm --prefix "$1/src/tui" prune --omit=dev --no-audit --no-fund
}

truthy_env() {
  case "$(printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]')" in
    1|true|yes|on)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

should_use_prebuilt_bundle() {
  local source_root="$1"
  local dist_root="$2"
  local dist_entry="$3"
  local force_value="${4:-}"

  if truthy_env "$force_value"; then
    return 1
  fi

  if [ ! -e "$dist_root/$dist_entry" ]; then
    return 1
  fi

  local freshness_output=""
  if command -v python3 >/dev/null 2>&1; then
    freshness_output="$(python3 - "$source_root" "$dist_root" <<'PY'
from pathlib import Path
import sys

source_root = Path(sys.argv[1])
dist_root = Path(sys.argv[2])
ignore_names = {"dist", "node_modules", ".git", "__pycache__"}

if not source_root.exists() or not dist_root.exists():
    print("stale")
    raise SystemExit(0)

def iter_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in ignore_names for part in path.relative_to(root).parts):
            continue
        yield path

source_mtime = 0.0
for path in iter_files(source_root):
    source_mtime = max(source_mtime, path.stat().st_mtime)

dist_mtime = 0.0
for path in dist_root.rglob("*"):
    if not path.is_file():
        continue
    dist_mtime = max(dist_mtime, path.stat().st_mtime)

print("fresh" if dist_mtime >= source_mtime else "stale")
PY
)"
  elif command -v python >/dev/null 2>&1; then
    freshness_output="$(python - "$source_root" "$dist_root" <<'PY'
from pathlib import Path
import sys

source_root = Path(sys.argv[1])
dist_root = Path(sys.argv[2])
ignore_names = {"dist", "node_modules", ".git", "__pycache__"}

if not source_root.exists() or not dist_root.exists():
    print("stale")
    raise SystemExit(0)

def iter_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in ignore_names for part in path.relative_to(root).parts):
            continue
        yield path

source_mtime = 0.0
for path in iter_files(source_root):
    source_mtime = max(source_mtime, path.stat().st_mtime)

dist_mtime = 0.0
for path in dist_root.rglob("*"):
    if not path.is_file():
        continue
    dist_mtime = max(dist_mtime, path.stat().st_mtime)

print("fresh" if dist_mtime >= source_mtime else "stale")
PY
)"
  else
    return 1
  fi

  [ "$freshness_output" = "fresh" ]
}

write_install_wrappers() {
  local target="$1"
  mkdir -p "$target/bin"
  for command_name in ds ds-cli research resear; do
    cat >"$target/bin/$command_name" <<EOF
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="\$(cd "\$(dirname "\${BASH_SOURCE[0]}")" && pwd)"
HOME_DIR="\$(cd "\$SCRIPT_DIR/../.." && pwd)"
if [ -z "\${DEEPSCIENTIST_HOME:-}" ]; then
  export DEEPSCIENTIST_HOME="\$HOME_DIR"
fi
NODE_BIN="\${DEEPSCIENTIST_NODE:-node}"
exec "\$NODE_BIN" "\$SCRIPT_DIR/ds.js" "\$@"
EOF
    chmod +x "$target/bin/$command_name"
  done
}

write_global_wrapper() {
  local target_path="$1"
  local command_name="$2"
  if [ -L "$target_path" ] || [ -f "$target_path" ]; then
    rm -f "$target_path"
  fi
  cat >"$target_path" <<EOF
#!/usr/bin/env bash
set -euo pipefail
if [ -z "\${DEEPSCIENTIST_HOME:-}" ]; then
  export DEEPSCIENTIST_HOME="$BASE_DIR"
fi
exec "$INSTALL_DIR/bin/$command_name" "\$@"
EOF
  chmod +x "$target_path"
}

require_command node
require_command npm

SOURCE_ROOT_RESOLVED="$(resolve_path "$SOURCE_ROOT")"
INSTALL_DIR_RESOLVED="$(resolve_path "$INSTALL_DIR")"
if [ "$SOURCE_ROOT_RESOLVED" = "$INSTALL_DIR_RESOLVED" ]; then
  echo "Install dir must be different from the development checkout: $INSTALL_DIR" >&2
  exit 1
fi

STAGING_DIR="${INSTALL_DIR}.staging.$$"
safe_remove_dir "$STAGING_DIR"
trap 'rm -rf "$STAGING_DIR"' EXIT

print_step "Preparing staging directory"
mkdir -p "$BASE_DIR"
copy_source_tree "$STAGING_DIR"
prune_tree "$STAGING_DIR"
install_root_runtime "$STAGING_DIR"
build_ui "$STAGING_DIR"
build_tui "$STAGING_DIR"
write_install_wrappers "$STAGING_DIR"

print_step "Replacing previous install"
stop_existing_install
safe_remove_dir "$INSTALL_DIR"
mv "$STAGING_DIR" "$INSTALL_DIR"
trap - EXIT

print_step "Writing launcher wrappers"
mkdir -p "$BIN_DIR"
write_global_wrapper "$BIN_DIR/ds" "ds"
write_global_wrapper "$BIN_DIR/ds-cli" "ds-cli"
write_global_wrapper "$BIN_DIR/research" "research"
write_global_wrapper "$BIN_DIR/resear" "resear"

print_step "Install complete"
printf 'Install dir: %s\n' "$INSTALL_DIR"
printf 'Bin dir: %s\n' "$BIN_DIR"
printf 'Run: %s\n' "$BIN_DIR/ds"
printf 'Start web workspace: %s\n' "$BIN_DIR/ds --web"
printf 'Default start: %s\n' "$BIN_DIR/ds"
printf 'When `ds` starts, it prints the local Web URL and opens it automatically when supported.\n'
printf 'If `uv` is missing, the first `ds` start will bootstrap a local copy automatically under the DeepScientist home.\n'
if [ "$WITH_TINYTEX" -eq 1 ]; then
  print_step "Installing TinyTeX pdflatex runtime"
  "$INSTALL_DIR/bin/ds" latex install-runtime
fi
print_optional_latex_notice
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
  printf 'Add to PATH if needed: export PATH="%s:$PATH"\n' "$BIN_DIR"
fi
