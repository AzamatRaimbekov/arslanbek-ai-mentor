#!/usr/bin/env bash
# Рядом стоит ruflo (claude-flow)? Тогда агенты, рой, память и маршрутизация — его зона,
# а скил только учит и отвечает за язык. Подключается через `source`.
# VIBECODING_NO_RUFLO=1 — считать, что ruflo нет (ruflo удалили, а папка осталась).
ruflo_present() {
  [ -n "${VIBECODING_NO_RUFLO:-}" ] && return 1
  [ -d "$HOME/.claude-flow" ] && return 0
  [ -n "${CLAUDE_PROJECT_DIR:-}" ] && [ -d "$CLAUDE_PROJECT_DIR/.claude-flow" ] && return 0
  grep -qs '"claude-flow"' "$HOME/.claude.json"
}

# Плагины, которые при ruflo не ставим никогда: их хуки дублируют хуки ruflo
# (claude-mem — вторая память, ecc — 24 хука на те же события).
RUFLO_SKIP_PLUGINS="claude-mem ecc"
