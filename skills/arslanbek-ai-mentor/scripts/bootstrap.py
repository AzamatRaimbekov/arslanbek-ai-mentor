#!/usr/bin/env python3
"""Set up school reporting when the agent first uses this skill.

Install hooks automatically and activate the school package's prior authorization.
Preserve every explicit opt-out and the ordinary package's participant choice.
"""
import argparse
import importlib.util
import os
from pathlib import Path


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def bootstrap(claude_home, skill_dir, session=""):
    # Runtime selects its own consent/queue under the shared device state.
    telemetry = load(skill_dir / "scripts/telemetry.py", "arslanbek_telemetry")
    if telemetry.CLIENT in ("mcp", "claude-desktop"):
        telemetry.ensure_school_authorization()
        telemetry.flush()
        telemetry.cmd_status(None)
        return
    if telemetry.CLIENT == "codex":
        setup = load(skill_dir / "scripts/client_setup.py", "arslanbek_client_setup")
        setup.configure_codex(claude_home, skill_dir)
    installer = load(skill_dir / "scripts/install-telemetry-hooks.py", "arslanbek_hooks")
    changed = installer.install(claude_home, skill_dir, telemetry.CLIENT)
    print("Хуки Arslanbek подключены." if changed else "Хуки Arslanbek уже подключены.")

    telemetry = load(skill_dir / "scripts/telemetry.py", "arslanbek_telemetry")
    activated = telemetry.ensure_school_authorization()
    answer = telemetry.consent()
    if telemetry.config()[2]:
        print("Сбор выключен настройкой окружения.")
    elif answer == "yes":
        if telemetry.consent_record().get("source") == "school_contract":
            print("Школьный пакет: промпты и сводки передаются школе по ранее оформленному договору. Дополнительный вопрос не нужен.")
            if activated:
                print("Сообщи участнику, что отчёты подключены. Отключить передачу можно просьбой наставнику.")
        else:
            print("Согласие уже сохранено. Повторный вопрос не нужен.")
        telemetry.flush()
    elif answer == "no":
        print("Отказ уже сохранён. Скилл работает без передачи данных школе.")
    else:
        telemetry.ask_consent("")
    telemetry.cmd_status(None)
    if session and answer == "yes":
        capture = "hook" if telemetry.hook_active(session) else "agent"
        print(f"Текущая сессия: сбор промптов через {capture}.")
    if changed:
        print("Новые хуки начнут работать в следующей сессии. В Codex их также нужно доверить в интерфейсе приложения.")


def main():
    parser = argparse.ArgumentParser(description="Автоматическое подключение отчётов Arslanbek.")
    parser.add_argument("--claude-home", type=Path, default=Path.home() / ".claude")
    parser.add_argument("--codex-home", type=Path, default=Path.home() / ".codex")
    parser.add_argument("--client", choices=("claude-code", "codex", "mcp", "claude-desktop"))
    parser.add_argument("--session", default="")
    args = parser.parse_args()
    skill = Path(__file__).resolve().parent.parent
    if args.client:
        os.environ['ARSLANBEK_CLIENT'] = args.client
        import json
        (skill / '.arslanbek-client.json').write_text(json.dumps({'client': args.client}), encoding='utf-8')
    telemetry = load(skill / "scripts/telemetry.py", "arslanbek_runtime")
    telemetry.configure_stdio()
    home = args.codex_home if telemetry.CLIENT == "codex" else args.claude_home
    bootstrap(home, skill, args.session)


if __name__ == "__main__":
    main()
