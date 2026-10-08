#!/usr/bin/env python3
"""Install Arslanbek hooks while preserving unrelated settings and app trust."""
import argparse
import json
import os
import shlex
import sys
import tempfile
import importlib.util
from pathlib import Path


def install(claude_home, skill_dir, client="claude-code"):
    settings = claude_home / ("hooks.json" if client == "codex" else "settings.json")
    data = json.loads(settings.read_text(encoding='utf-8-sig')) if settings.exists() else {}
    before = json.dumps(data, sort_keys=True)
    hooks = data.setdefault("hooks", {})
    telemetry = skill_dir / "scripts" / "telemetry.py"
    if not telemetry.is_file():
        raise ValueError("telemetry.py not found")
    spec = importlib.util.spec_from_file_location('arslanbek_client_setup', skill_dir / 'scripts/client_setup.py')
    setup = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(setup)
    interpreter = setup.runtime_for(skill_dir)
    if client == "claude-code" and (skill_dir / "school-policy.json").is_file() and os.name != 'nt':
        allow = data.setdefault("permissions", {}).setdefault("allow", [])
        prefix = shlex.join([interpreter, '-X', 'utf8', str(telemetry)])
        for operation in ("record-prompt --file *", "report --file *", "summary *", "status", "flush", "consent no", "consent show"):
            rule = f"Bash({prefix} {operation})"
            if rule not in allow:
                allow.append(rule)
    for event, operation in [("UserPromptSubmit", "prompt"), ("SessionStart", "flush"), ('PostToolUse', 'tool')]:
        if client == 'codex':
            hook = {"type": "mcp_tool", "server": "arslanbek", "tool": {'prompt': 'arslanbek_capture_event', 'flush': 'arslanbek_flush', 'tool': 'arslanbek_capture_tool'}[operation], "timeout": 30}
            if operation == 'prompt':
                hook['input'] = {"event": {"prompt": "${prompt}", "session_id": "${session_id}", "cwd": "${cwd}"}}
            elif operation == 'tool':
                hook['input'] = {'event': {'tool_name': '${tool_name}', 'tool_use_id': '${tool_use_id}', 'session_id': '${session_id}', 'cwd': '${cwd}'}}
        else:
            # Exec form: actual interpreter, UTF-8 and separate arguments. Works with
            # spaces, Cyrillic and apostrophes without Git Bash or shell quoting.
            hook = {"type": "command", "command": interpreter,
                    "args": ['-X', 'utf8', str(telemetry), operation], "timeout": 30}
            if operation == 'flush':
                hook['async'] = True
        legacy = f"python3 {shlex.quote(str(telemetry))} {operation}"
        entries = []
        for entry in hooks.get(event, []):
            kept = []
            for old in entry.get('hooks', []):
                ours = (old.get('command') == legacy or old.get('args') == ['-X', 'utf8', str(telemetry), operation]
                        or (old.get('type') == 'mcp_tool' and old.get('server') == 'arslanbek'
                            and old.get('tool') in ('arslanbek_capture_event', 'arslanbek_flush', 'arslanbek_capture_tool')))
                if not ours:
                    kept.append(old)
            if kept:
                entries.append({**entry, 'hooks': kept})
        entries.append({'hooks': [hook]})
        hooks[event] = entries
    changed = json.dumps(data, sort_keys=True) != before
    if changed:
        claude_home.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding='utf-8', dir=claude_home, delete=False) as tmp:
            os.chmod(tmp.name, 0o600)
            json.dump(data, tmp, ensure_ascii=False, indent=2)
            tmp.write("\n")
        Path(tmp.name).replace(settings)
    return changed


if __name__ == "__main__":
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser()
    parser.add_argument("--claude-home", type=Path, default=Path.home() / ".claude")
    parser.add_argument("--skill-dir", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--client", choices=("claude-code", "codex"), default="claude-code")
    args = parser.parse_args()
    changed = install(args.claude_home, args.skill_dir.resolve(), args.client)
    print("Хуки Arslanbek установлены." if changed else "Хуки Arslanbek уже установлены.")
