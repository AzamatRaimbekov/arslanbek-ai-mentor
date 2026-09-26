#!/usr/bin/env bash
# Согласие ученика на сбор данных для школы.
#   consent.sh yes   — разрешить отправку промптов и срезов
#   consent.sh no    — запретить и очистить неотправленное
#   consent.sh show  — текущее состояние
exec python3 "$(dirname "$0")/telemetry.py" consent "$@"
