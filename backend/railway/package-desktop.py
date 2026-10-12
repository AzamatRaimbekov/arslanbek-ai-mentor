"""Build platform-specific downloads from the school package. No private credentials.

Windows Python archives are pinned to the SHA-256 published on python.org.
They remain inside the skill: no system installation or PATH changes.
"""
import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[2]
RUNTIMES = {
    'windows-x64': ('https://www.python.org/ftp/python/3.14.8/python-3.14.8-embed-amd64.zip',
                    'a93abe456ab01bd96d7a085b3cdb6566b3063f4241360d114142fbdb07f0a310'),
    'windows-arm64': ('https://www.python.org/ftp/python/3.14.8/python-3.14.8-embed-arm64.zip',
                      '155be84ccb57c6331cf0e39001c78a1dfac3be62f403f3ff5f2e29b80dda7ebe'),
}


def runtime_files(cache):
    files = {}
    cache.mkdir(parents=True, exist_ok=True)
    for arch, (url, checksum) in RUNTIMES.items():
        archive = cache / url.rsplit('/', 1)[-1]
        if not archive.exists():
            with urllib.request.urlopen(url, timeout=60) as response:
                content = response.read(30000000)
            if hashlib.sha256(content).hexdigest() != checksum:
                raise ValueError('Python download checksum mismatch: ' + arch)
            archive.write_bytes(content)
        if hashlib.sha256(archive.read_bytes()).hexdigest() != checksum:
            raise ValueError('Cached Python checksum mismatch: ' + arch)
        with zipfile.ZipFile(archive) as source:
            for info in source.infolist():
                name = info.filename
                if info.is_dir():
                    continue
                if name.startswith('/') or '..' in Path(name).parts or '\\' in name:
                    raise ValueError('Unsafe runtime archive path')
                content = source.read(name)
                if name.endswith('._pth'):
                    content += b'\n../../scripts\n'
                files[f'arslanbek-ai-mentor/runtime/{arch}/{name}'] = content
    files['arslanbek-ai-mentor/runtime/SOURCES.json'] = json.dumps(
        {arch: {'url': url, 'sha256': sha} for arch, (url, sha) in RUNTIMES.items()}, indent=2).encode()
    return files


def write_zip(path, entries):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as target:
        for name, content in entries.items():
            target.writestr(name, content)
    temporary.replace(path)


def build(output, cache, include_windows=True, contract=True):
    spec = importlib.util.spec_from_file_location('school_builder', Path(__file__).with_name('package-skill.py'))
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    with tempfile.TemporaryDirectory() as folder:
        builder.ROOT = Path(folder)
        builder.OUTPUT = Path(folder) / 'base.zip'
        with contextlib.redirect_stdout(io.StringIO()):
            builder.main(contract=contract)
        with zipfile.ZipFile(builder.OUTPUT) as archive:
            base = {name: archive.read(name) for name in archive.namelist()}
    windows = runtime_files(cache) if include_windows else {}
    write_zip(output / 'arslanbek-ai-mentor.zip', {**base, **windows})
    codex = {**base, **windows}
    codex['arslanbek-ai-mentor/SKILL.md'] = base['arslanbek-ai-mentor/references/portable-skill.md']
    codex['arslanbek-ai-mentor/.arslanbek-client.json'] = b'{"client":"codex"}'
    codex['START_HERE.txt'] = ('''ARSLANBEK ДЛЯ CODEX DESKTOP

Распакуйте папку arslanbek-ai-mentor в ~/.agents/skills/.
На Windows: %USERPROFILE%\\.agents\\skills\\arslanbek-ai-mentor.
В новом локальном чате вызовите $arslanbek-ai-mentor и дайте рабочую задачу.
Агент сам выполнит подключение. Запускать скрипты вручную не нужно.
Первый запуск подключает 11 встроенных скиллов, включая visual-explainer,
диагностику и базовые инструкции Superpowers. Для этого не нужны сеть, npm и Bash.
Личные правки и другие установленные скиллы сохраняются.
Первый вызов сохраняет формат «чат + HTML» глобально для последующих вопросов,
проектов и сессий Codex. Другие инструкции и выбор «только чат» сохраняются.
Windows-пакет содержит свой Python x64/ARM64, Bash и WSL не требуются.
На macOS/Linux нужен Python 3.10+. В WSL устанавливайте скилл внутри WSL.
Просмотрите и доверьте хуки в Codex: это отдельное требование приложения.
Новые MCP/хуки могут потребовать новой сессии. До неё агент отправляет данные сам.

Передаются новые запросы, сводки задач/навыков, псевдонимы проекта,
сессии и участника. Распознанные личные данные заменяются локально,
типовые секреты удаляются. Автоматическое распознавание может пропустить
личные сведения в свободном тексте. Таблица замен остаётся на компьютере.
Ответы ИИ, файлы проектов и старая история не загружаются.
Школьный пакет действует по договору со школой; прежнее отключение сохраняется.
Доставку показывает arslanbek_status. Попросите агента выключить сбор,
если хотите остановить передачу. При обновлении попросите сохранить личный
профиль, уроки и прежний выбор. Подробности: references/desktop-start.md.
''').encode('utf-8')
    write_zip(output / 'arslanbek-codex.zip', codex)
    desktop = {name: content for name, content in base.items() if name.startswith('arslanbek-ai-mentor/')}
    desktop['arslanbek-ai-mentor/.arslanbek-client.json'] = b'{"client":"claude-desktop"}'
    desktop['arslanbek-ai-mentor/SKILL.md'] = base['arslanbek-ai-mentor/references/portable-skill.md']
    desktop['manifest.json'] = json.dumps({
        'manifest_version': '0.4', 'name': 'arslanbek-ai-mentor', 'display_name': 'Arslanbek — наставник и прогресс',
        'version': '9.2.0', 'description': 'Наставник Arslanbek с 11 встроенными скиллами и прогрессом обучения.',
        'long_description': 'Школьный пакет для участников с договором. Передаёт текущие запросы и сводки, которые отправляет агент, псевдонимы проектов и участника. Распознанные личные данные заменяются локально, типовые секреты удаляются; распознавание может пропустить личные сведения в свободном тексте. Не считывает прошлые чаты, ответы ИИ или файлы проектов. В обычном чате нет хука каждого сообщения: полнота зависит от вызовов инструментов. Выключить сбор можно в настройках расширения. Сохранённый отказ не переопределяется.',
        'author': {'name': 'Arslanbek'},
        'tools_generated': True, 'prompts_generated': True,
        'privacy_policies': ['https://frontend-production-a08a.up.railway.app/install#reporting'],
        'server': {'type': 'uv', 'entry_point': 'arslanbek-ai-mentor/scripts/mcp-server.py',
                   'mcp_config': {'command': 'uv', 'args': ['run', '--directory', '${__dirname}', '--no-dev', 'arslanbek-ai-mentor/scripts/mcp-server.py'],
                                  'env': {'PYTHONUTF8': '1', 'ARSLANBEK_CLIENT': 'claude-desktop', 'ARSLANBEK_TELEMETRY': '${user_config.collection_enabled}'}}},
        'compatibility': {'platforms': ['darwin', 'win32'], 'runtimes': {'python': '>=3.10'}},
        'user_config': {'collection_enabled': {'type': 'boolean', 'title': 'Передавать учебные данные школе',
                                              'description': 'Текущие запросы и сводки, отправленные агентом. История и файлы не считываются.', 'default': True}},
    }, ensure_ascii=False, indent=2).encode('utf-8')
    desktop['pyproject.toml'] = b'[project]\nname = "arslanbek-desktop"\nversion = "9.2.0"\nrequires-python = ">=3.10"\ndependencies = []\n\n[tool.uv]\npackage = false\n'
    write_zip(output / 'arslanbek-claude-desktop.mcpb', desktop)
    manifest = {p.name: {'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'bytes': p.stat().st_size}
                for p in (output / n for n in ('arslanbek-ai-mentor.zip', 'arslanbek-codex.zip', 'arslanbek-claude-desktop.mcpb'))}
    (output / 'release.json').write_text(json.dumps({'version': '9.2.0', 'windows_runtime_bundled': include_windows, 'files': manifest}, indent=2) + '\n', encoding='utf-8')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'dashboard/public/downloads')
    parser.add_argument('--cache', type=Path, default=Path(tempfile.gettempdir()) / 'arslanbek-python-runtime')
    parser.add_argument('--without-windows-runtime', action='store_true', help='For fast source tests only, not the Windows release.')
    args = parser.parse_args()
    print(json.dumps(build(args.output, args.cache, not args.without_windows_runtime), indent=2))
