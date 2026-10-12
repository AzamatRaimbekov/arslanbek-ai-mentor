#!/usr/bin/env bash
# Compatibility entry point. Native Windows uses ensure_tools.py with bundled Python.
set -u
ARSLANBEK_TOOL_SCRIPT="$(dirname "$0")/ensure_tools.py"
if command -v python3 >/dev/null 2>&1; then
  exec python3 "$ARSLANBEK_TOOL_SCRIPT" "$@"
elif command -v python >/dev/null 2>&1; then
  exec python "$ARSLANBEK_TOOL_SCRIPT" "$@"
fi
printf '%s\n' 'Python is unavailable; use the Python runtime bundled with Arslanbek.' >&2
exit 1
