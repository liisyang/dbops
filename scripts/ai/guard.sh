#!/usr/bin/env bash
set -euo pipefail

# Purpose:
#   Block P0 dangerous commands before Claude Code runs Bash tools.
#
# Usage:
#   printf '%s\n' '{"tool_input":{"command":"echo hello"}}' | bash scripts/ai/guard.sh

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  cat <<'USAGE'
Usage:
  printf '%s\n' '{"tool_input":{"command":"echo hello"}}' | bash scripts/ai/guard.sh

This script reads Claude Code hook JSON from stdin and blocks P0 dangerous commands.
USAGE
  exit 0
fi

if [ "$#" -gt 0 ]; then
  echo "[ERROR] Unknown argument: $*" >&2
  exit 1
fi

json_input="$(cat)"

command_text="$(
JSON_INPUT="$json_input" python3 - <<'PY'
import json
import os

try:
    data = json.loads(os.environ.get("JSON_INPUT", "{}"))
    print(data.get("tool_input", {}).get("command", ""))
except Exception:
    print("")
PY
)"

if [ -z "$command_text" ]; then
  exit 0
fi

normalized_command="$(printf '%s' "$command_text" | tr '\n' ' ')"

blocked_patterns=(
  '(^|[;&|[:space:]])rm[[:space:]]+-rf[[:space:]]+/([[:space:]]|$)'
  '(^|[;&|[:space:]])rm[[:space:]]+-rf[[:space:]]+/\*([[:space:]]|$)'
  '(^|[;&|[:space:]])mkfs([.[:alnum:]_-]*|[[:space:]])'
  '(^|[;&|[:space:]])dd[[:space:]].*of=/dev/'
  '(^|[;&|[:space:]])git[[:space:]]+push[[:space:]].*--force'
  '(^|[;&|[:space:]])git[[:space:]]+reset[[:space:]]+--hard'
  '(^|[;&|[:space:]])kubectl[[:space:]]+delete[[:space:]]'
  '(^|[;&|[:space:]])docker[[:space:]]+rm[[:space:]].*-f'
  '(^|[^A-Za-z0-9_])DROP[[:space:]]+(DATABASE|SCHEMA|TABLE|USER|ROLE|OWNED)([^A-Za-z0-9_]|$)'
  '(^|[^A-Za-z0-9_])TRUNCATE([[:space:]]+TABLE)?[[:space:]]+'
  '(^|[^A-Za-z0-9_])ALTER[[:space:]]+SYSTEM([^A-Za-z0-9_]|$)'
  '(^|[^A-Za-z0-9_])SHUTDOWN([^A-Za-z0-9_]|$)'
)

for pattern in "${blocked_patterns[@]}"; do
  if printf '%s' "$normalized_command" | grep -Eiq "$pattern"; then
    echo "Blocked by scripts/ai/guard.sh"
    echo "P0 dangerous command detected:"
    echo "$command_text"
    echo "Run manually only after human confirmation."
    exit 2
  fi
done

exit 0
