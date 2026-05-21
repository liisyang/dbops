#!/usr/bin/env bash
set -u

# Purpose:
#   Run available baseline checks for AI Coding tasks.
#
# Usage:
#   bash scripts/ai/verify.sh
#
# Notes:
#   This script does not use set -e because it collects multiple check results.

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  cat <<'USAGE'
Usage:
  bash scripts/ai/verify.sh

Runs available checks:
  - JS lint/typecheck/build if package scripts exist
  - Python pytest if pytest is available
  - Bash syntax check for scripts/*.sh
USAGE
  exit 0
fi

if [ "$#" -gt 0 ]; then
  echo "[ERROR] Unknown argument: $*" >&2
  exit 1
fi

echo "[INFO] AI verification started"

repo_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$repo_root" || exit 1

fail_count=0
skip_count=0

run_step() {
  local name="$1"
  shift

  echo "[INFO] Run: $name"

  if "$@"; then
    echo "[OK] $name"
  else
    echo "[FAIL] $name"
    fail_count=$((fail_count + 1))
  fi
}

skip_step() {
  local reason="$1"
  echo "[WARN] Skip: $reason"
  skip_count=$((skip_count + 1))
}

has_package_script() {
  local dir="$1"
  local script_name="$2"

  if [ ! -f "$dir/package.json" ]; then
    return 1
  fi

  if ! command -v node >/dev/null 2>&1; then
    return 1
  fi

  node -e "
const fs = require('fs');
const p = '$dir/package.json';
const pkg = JSON.parse(fs.readFileSync(p, 'utf8'));
process.exit(pkg.scripts && pkg.scripts['$script_name'] ? 0 : 1);
" >/dev/null 2>&1
}

run_js_script() {
  local dir="$1"
  local script_name="$2"
  local status=0

  if [ ! -f "$dir/package.json" ]; then
    return 0
  fi

  if ! has_package_script "$dir" "$script_name"; then
    skip_step "$dir package.json has no script: $script_name"
    return 0
  fi

  cd "$repo_root/$dir" || return 1

  if [ -f "pnpm-lock.yaml" ] && command -v pnpm >/dev/null 2>&1; then
    pnpm "$script_name" || status=$?
  elif [ -f "yarn.lock" ] && command -v yarn >/dev/null 2>&1; then
    yarn "$script_name" || status=$?
  elif command -v npm >/dev/null 2>&1; then
    npm run "$script_name" || status=$?
  else
    cd "$repo_root" || return 1
    skip_step "$dir no available package manager for $script_name"
    return 0
  fi

  cd "$repo_root" || return 1
  return "$status"
}

check_js_project() {
  local dir="$1"

  if [ ! -f "$dir/package.json" ]; then
    return 0
  fi

  echo "[INFO] Check JS project: $dir"

  if [ ! -d "$dir/node_modules" ]; then
    skip_step "$dir/node_modules not found"
    return 0
  fi

  run_step "$dir lint" run_js_script "$dir" "lint"
  run_step "$dir typecheck" run_js_script "$dir" "typecheck"
  run_step "$dir build" run_js_script "$dir" "build"
}

run_pytest_dir() {
  local dir="$1"
  local status=0

  cd "$repo_root/$dir" || return 1

  if [ -f "$repo_root/venv/bin/activate" ]; then
    . "$repo_root/venv/bin/activate"
  elif [ -f "$repo_root/.venv/bin/activate" ]; then
    . "$repo_root/.venv/bin/activate"
  fi

  pytest -v || status=$?

  cd "$repo_root" || return 1
  return "$status"
}

check_python_project() {
  local dir="$1"

  if [ ! -d "$dir" ]; then
    return 0
  fi

  if [ ! -d "$dir/tests" ] && [ ! -f "$dir/pytest.ini" ] && [ ! -f "$dir/pyproject.toml" ]; then
    return 0
  fi

  if ! command -v pytest >/dev/null 2>&1; then
    skip_step "pytest not found for $dir"
    return 0
  fi

  run_step "$dir pytest" run_pytest_dir "$dir"
}

check_shell_scripts() {
  if [ ! -d "scripts" ]; then
    return 0
  fi

  while IFS= read -r script_file; do
    run_step "bash -n $script_file" bash -n "$script_file"
  done < <(find scripts -type f -name "*.sh" | sort)
}

echo "[INFO] Detect and run available checks"

check_js_project "."
check_js_project "frontend"
check_js_project "web"

check_python_project "."
check_python_project "backend"
check_python_project "server"

check_shell_scripts

echo "[INFO] Git status"
git status --short

echo "[INFO] Verification summary"
echo "[INFO] failed: $fail_count"
echo "[INFO] skipped: $skip_count"

if [ "$fail_count" -gt 0 ]; then
  echo "[FAIL] AI verification finished with errors"
  exit 1
fi

echo "[OK] AI verification finished"
exit 0
