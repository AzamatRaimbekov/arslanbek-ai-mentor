"""Configure Codex MCP without a shell or changes to unrelated settings."""
import json
import re
import sys
import os
import platform
from pathlib import Path


def runtime_for(skill):
    if os.name == 'nt':
        arch = 'windows-arm64' if platform.machine().lower() in ('arm64', 'aarch64') else 'windows-x64'
        bundled = skill / 'runtime' / arch / 'python.exe'
        if bundled.is_file():
            return str(bundled)
    return sys.executable


def configure_codex(codex_home, skill):
    path = codex_home / 'config.toml'
    existing = path.read_text(encoding='utf-8-sig') if path.exists() else ''
    start, end = '# BEGIN ARSLANBEK MCP', '# END ARSLANBEK MCP'
    block = '\n'.join([start, '[mcp_servers.arslanbek]',
                       'command = ' + json.dumps(runtime_for(skill)),
                       'args = ' + json.dumps(['-X', 'utf8', str(skill / 'scripts/mcp-server.py')]), end])
    if start in existing:
        if end not in existing:
            raise ValueError('Незавершённый блок Arslanbek в config.toml; исправьте его, сохранив остальные настройки.')
        updated = re.sub(re.escape(start) + r'.*?' + re.escape(end), lambda _: block, existing, flags=re.S)
    elif re.search(r'^\s*\[mcp_servers\.(?:arslanbek|"arslanbek")\]', existing, re.M):
        print('Существующий MCP arslanbek сохранён. Проверьте его путь в config.toml.')
        return False
    else:
        updated = existing.rstrip() + '\n\n' + block + '\n'
    if updated == existing:
        return False
    codex_home.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.arslanbek.tmp')
    temporary.write_text(updated, encoding='utf-8')
    temporary.chmod(0o600)
    temporary.replace(path)
    return True
