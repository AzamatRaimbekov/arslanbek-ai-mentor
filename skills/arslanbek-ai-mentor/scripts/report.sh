#!/usr/bin/env bash
# Срез по ученику на бэкенд школы: уровень владения ИИ, этап, итог.
#   report.sh --level <0-5> --stage "..." --summary "..." \
#             [--strengths ".."] [--struggles ".."] [--next ".."] [--session ID]
# Шкала уровней: references/ai-levels.md
exec python3 "$(dirname "$0")/telemetry.py" summary "$@"
