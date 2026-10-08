"""Bounded local observations. No model calls, file contents, credentials or transcripts leave here."""
import json
import importlib.util
from itertools import islice
from pathlib import Path
import re
_spec = importlib.util.spec_from_file_location('arslanbek_observation_privacy', Path(__file__).with_name('anonymizer.py'))
anonymizer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(anonymizer)

COMPETENCIES = ('prompt_engineering', 'context_engineering', 'harness', 'skill_authoring',
                'plugin_authoring', 'frontend', 'backend', 'databases', 'testing', 'devops', 'security')
TAGS = {
    'frontend': r'\b(frontend|front.end|react|vue|svelte|css|html|интерфейс|верстк\w*|фронтенд)\b',
    'backend': r'\b(backend|back.end|django|fastapi|express|бэкенд|бекенд|сервер\w*|endpoint|rest api)\b',
    'databases': r'\b(sql|postgres\w*|mysql|sqlite|supabase|баз[аыуе] данных|миграци\w*|database)\b',
    'testing': r'\b(test\w*|pytest|playwright|провер\w*|тест\w*)\b',
    'devops': r'\b(docker|kubernetes|deploy\w*|railway|vercel|депло\w*|ci/cd)\b',
    'prompt_engineering': r'\b(prompt engineering|промпт\w*|промт\w*|system prompt|инструкци\w* для (?:ии|модел\w*))\b',
    'context_engineering': r'\b(context engineering|контекст\w*|rag|retrieval|memory|памят\w*)\b',
    'harness': r'\b(harness|харнес\w*|хуки?|hooks?|orchestr\w*|оркестр\w*|агент\w*|agent\w*)\b',
    'skill_authoring': r'\b(skills?|скилл?\w*)\b',
    'plugin_authoring': r'\b(plugins?|плагин\w*|mcp)\b',
    'security': r'\b(security|безопасност\w*|секрет\w*|аноним\w*|конфиденц\w*)\b',
    'intent:debug': r'\b(debug\w*|ошиб\w*|почин\w*|исправ\w*|не работает|bug\w*)\b',
    'intent:learn': r'\b(learn\w*|объясн\w*|науч\w*|разбер\w*|почему|как работает)\b',
    'intent:plan': r'\b(plan\w*|план\w*|roadmap|роадмап|декомпоз\w*|разобь\w*)\b',
    'intent:build': r'\b(build|create|implement|созд\w*|добав\w*|сдела\w*|реализ\w*)\b',
    'intent:review': r'\b(review|ревью|оцени\w*|аудит\w*|проверь\w*)\b',
}
TAG_IDS = tuple(TAGS)
SIGNALS = ('api_key', 'private_key', 'credential', 'personal_contact', 'financial_id', 'confidential_marker')
KINDS = ('skill', 'plugin', 'mcp', 'harness', 'tool')
DEFAULT_MARKERS = ('strictly confidential', 'do not distribute', 'коммерческая тайна', 'конфиденциально', 'внутренний документ')
PLACEHOLDER = re.compile(r'^(?:\$\{|<|\[|example|demo|dummy|test|your[_-]|changeme|xxx|\.{3})', re.I)


def tags(text):
    return [tag for tag, pattern in TAGS.items() if re.search(pattern, text, re.I)]


def privacy_signals(text, markers=DEFAULT_MARKERS):
    """Return categories and counts only. Never emit a value, excerpt or hash of a secret."""
    found = {}
    def add(category, severity, count):
        if count:
            found[category] = {'category': category, 'severity': severity,
                               'count': min(100, found.get(category, {}).get('count', 0) + count)}
    for pattern, _ in anonymizer.SECRET_RULES:
        matches = list(pattern.finditer(text))
        if not matches:
            continue
        category = 'private_key' if 'PRIVATE KEY' in pattern.pattern else 'api_key'
        if 'password' in pattern.pattern or '://[^' in pattern.pattern or 'Authorization' in pattern.pattern:
            category = 'credential'
            matches = [m for m in matches if not PLACEHOLDER.match(m.group()[len(m.group(1)):] if m.lastindex else m.group())]
        add(category, 'critical' if category in ('private_key', 'api_key') else 'warning', len(matches))
    for category, pattern in anonymizer.PATTERNS:
        if category in ('EMAIL', 'PHONE'):
            add('personal_contact', 'info', len(list(pattern.finditer(text))))
        elif category == 'CARD':
            add('financial_id', 'warning', len(list(pattern.finditer(text))))
    add('confidential_marker', 'warning', sum(1 for marker in markers if marker.lower() in text.lower()))
    return list(found.values())


def read_json(path):
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 128_000:
        return {}
    try:
        result = json.loads(path.read_text(encoding='utf-8'))
        return result if isinstance(result, dict) else {}
    except (OSError, ValueError):
        return {}


def environment(cwd, client, home=None):
    """Only names/presence from selected app and project. No recursive computer scan."""
    home = Path(home) if home else Path.home()
    project = Path(cwd)
    if client in ('mcp', 'claude-desktop'):
        return {'version': 1, 'client': client, 'tools': [], 'harness': [],
                'truncated': False, 'coverage': 'not_available'}
    tools, harness = [], []
    app = home / ('.codex' if client == 'codex' else '.claude')
    skill_roots = [home / '.agents/skills', project / '.agents/skills'] if client == 'codex' else [app / 'skills', project / '.claude/skills']
    if client in ('mcp', 'claude-desktop'):
        skill_roots = []  # Do not inspect configuration belonging to other apps.
    truncated = False
    for folder in skill_roots:
        if not folder.is_dir() or folder.is_symlink():
            continue
        children = sorted(islice(folder.iterdir(), 65), key=lambda item: item.name)
        truncated |= len(children) > 64
        for item in children[:64]:
            if not item.is_symlink() and (item / 'SKILL.md').is_file():
                tools.append({'kind': 'skill', 'tool_id': item.name[:120], 'scope': 'project' if folder.is_relative_to(project) else 'user'})
    instruction = 'AGENTS.md' if client == 'codex' else 'CLAUDE.md'
    if (project / instruction).is_file():
        harness.append('project_instructions')
    if (project / '.git').exists():
        harness.append('version_control')
    if (project / '.github/workflows').is_dir():
        harness.append('ci_configuration')
    package = read_json(project / 'package.json')
    scripts = package.get('scripts')
    if (isinstance(scripts, dict) and any(re.search(r'(^|:)test($|:)', key) for key in scripts)) or any((project / name).is_file() for name in ('pytest.ini', 'tox.ini', 'playwright.config.ts', 'vitest.config.ts')):
        harness.append('test_configuration')
    if client == 'claude-code':
        for path in (app / 'settings.json', project / '.claude/settings.json'):
            settings = read_json(path)
            if settings.get('hooks'):
                harness.append('app_hooks')
            enabled = settings.get('enabledPlugins', {})
            if isinstance(enabled, dict):
                for name, active in list(enabled.items())[:64]:
                    if active is True:
                        tools.append({'kind': 'plugin', 'tool_id': name[:120], 'scope': 'user' if path.parent == app else 'project'})
        for path in (home / '.claude.json', project / '.mcp.json'):
            settings = read_json(path)
            servers = settings.get('mcpServers')
            for name in list(servers if isinstance(servers, dict) else {})[:64]:
                tools.append({'kind': 'mcp', 'tool_id': name[:120], 'scope': 'user' if path.parent == home else 'project'})
    if client == 'codex':
        if read_json(app / 'hooks.json').get('hooks'):
            harness.append('app_hooks')
        config = app / 'config.toml'
        if config.is_file() and not config.is_symlink() and config.stat().st_size <= 128_000:
            for name in re.findall(r'^\s*\[mcp_servers\.(?:"([^"\n]+)"|([\w-]+))\]\s*$', config.read_text(encoding='utf-8'), re.M):
                tools.append({'kind': 'mcp', 'tool_id': (name[0] or name[1])[:120], 'scope': 'user'})
    unique = {(item['kind'], item['tool_id'], item['scope']): item for item in tools}
    return {'version': 1, 'client': client, 'tools': list(unique.values())[:64],
            'harness': sorted(set(harness)), 'truncated': truncated or len(unique) > 64,
            'coverage': 'selected_app_and_project' if client in ('codex', 'claude-code') else 'project_only'}


def observe_prompt(text, cwd, client):
    policy = read_json(Path(cwd) / '.arslanbek/privacy-policy.json')
    markers = policy.get('markers', [])
    if not isinstance(markers, list) or any(not isinstance(m, str) or not 3 <= len(m) <= 100 for m in markers) or len(markers) > 20:
        markers = []
    return {'version': 1, 'tags': tags(text), 'tag_source': 'keyword_rules',
            'privacy_signals': privacy_signals(text, (*DEFAULT_MARKERS, *markers)),
            'environment': environment(cwd, client)}


def tool_event(event):
    name = event.get('tool_name')
    if not isinstance(name, str) or not name or 'arslanbek' in name.lower():
        return None  # Reporting hooks must not recursively report themselves.
    kind, identifier = 'tool', name
    args = event.get('tool_input')
    if name == 'Skill' and isinstance(args, dict) and isinstance(args.get('skill'), str):
        kind, identifier = 'skill', args['skill']
    elif name.startswith('mcp__'):
        kind = 'mcp'
    elif name in ('Agent', 'Task', 'spawn_agent', 'Subagent'):
        kind = 'harness'
    counts = {}
    for field in ('tool_input', 'tool_response'):
        value = event.get(field)
        if value is None:
            continue
        content = json.dumps(value, ensure_ascii=False)
        if len(content) > 2_000_000:
            continue
        for signal in privacy_signals(content):
            current = counts.setdefault(signal['category'], {**signal, 'count': 0})
            current['count'] = min(100, current['count'] + signal['count'])
    return {'kind': kind, 'tool_id': identifier[:160], 'action': 'used',
            'actor': 'agent', 'source': 'tool_hook', 'privacy_signals': list(counts.values())}
