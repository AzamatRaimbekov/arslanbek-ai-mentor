"""Offline dependencies for native clients and read-only skill access for MCP."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile

NATIVE = ('claude-code', 'codex')
CLIENTS = (*NATIVE, 'claude-desktop', 'mcp')
STATE = '.arslanbek-dependencies.json'


def relative_file(value):
    if not isinstance(value, str) or not value or '\\' in value:
        raise ValueError('Invalid bundled file path')
    path = PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts or ':' in value or value != path.as_posix():
        raise ValueError('Bundled file path must stay inside its skill')
    return path


def catalog(skill):
    root = Path(skill) / 'bundled'
    value = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
    if not isinstance(value, dict) or value.get('version') != 1 or not isinstance(value.get('skills'), list) or not value['skills']:
        raise ValueError('Invalid bundled skill manifest')
    names = set()
    for entry in value['skills']:
        name = entry.get('name') if isinstance(entry, dict) else None
        if not isinstance(name, str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', name) or name in names:
            raise ValueError('Invalid or duplicate bundled skill name')
        names.add(name)
        files = entry.get('files')
        if not isinstance(files, dict) or 'SKILL.md' not in files:
            raise ValueError('Bundled skill requires SKILL.md')
        directory = root / name
        if directory.is_symlink():
            raise ValueError('Bundled skill must not be a symbolic link')
        if not usable(directory, name):
            raise ValueError('Bundled SKILL.md has a different skill name')
        for relative, checksum in files.items():
            path = directory / relative_file(relative)
            if not isinstance(checksum, str) or not re.fullmatch('[a-f0-9]{64}', checksum):
                raise ValueError('Invalid bundled checksum')
            if path.is_symlink() or not path.resolve().is_relative_to(directory.resolve()):
                raise ValueError('Bundled file escapes its skill')
            if hashlib.sha256(path.read_bytes()).hexdigest() != checksum:
                raise ValueError('Bundled checksum mismatch: ' + name + '/' + relative)
    return value['skills']


def destination(client, native_home=None, skills_home=None):
    override = skills_home or os.environ.get('ARSLANBEK_SKILLS_HOME')
    if override:
        return Path(override).expanduser().resolve()
    if client == 'codex':
        return Path.home() / '.agents/skills'
    if client == 'claude-code':
        return Path(native_home or os.environ.get('CLAUDE_CONFIG_DIR') or Path.home() / '.claude') / 'skills'
    return None


def usable(path, name):
    manifest = path / 'SKILL.md'
    if not manifest.is_file():
        return False
    front = manifest.read_text(encoding='utf-8-sig').split('---', 2)
    if len(front) < 3 or front[0].strip():
        return False
    match = re.search(r'^name:\s*(.+?)\s*$', front[1], re.M)
    return bool(match and match.group(1).strip('"\'') == name)


def matches(path, files):
    return all((path / relative).is_file() and not (path / relative).is_symlink()
               and hashlib.sha256((path / relative).read_bytes()).hexdigest() == checksum
               for relative, checksum in files.items())


def replace_file(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix='.arslanbek-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as target:
            target.write(content)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def ensure(skill, client, native_home=None, skills_home=None, dry_run=False):
    if client not in CLIENTS:
        raise ValueError('Unsupported client')
    entries = catalog(skill)
    if client not in NATIVE:
        return {'client':client, 'ready':True, 'delivery':'mcp',
                'skills':[{'name':entry['name'], 'status':'available-via-mcp'} for entry in entries]}
    target = destination(client, native_home, skills_home)
    state_path = target / STATE
    if state_path.is_symlink():
        raise ValueError('Preserving a symbolic link used as dependency state')
    state = json.loads(state_path.read_text(encoding='utf-8')) if state_path.is_file() else {'version':1,'skills':{}}
    if not isinstance(state, dict) or state.get('version') != 1 or not isinstance(state.get('skills'), dict):
        raise ValueError('Unrecognized dependency state; preserving it')
    for managed in state['skills'].values():
        if not isinstance(managed,dict) or not isinstance(managed.get('files'),dict):
            raise ValueError('Invalid managed dependency state')
        for filename, checksum in managed['files'].items():
            relative_file(filename)
            if not isinstance(checksum,str) or not re.fullmatch('[a-f0-9]{64}',checksum):
                raise ValueError('Invalid managed dependency checksum')
    results = []
    for entry in entries:
        name, files = entry['name'], entry['files']
        path = target / name
        previous = state['skills'].get(name, {})
        status = 'planned' if dry_run else 'installed'
        if path.exists() or path.is_symlink():
            if not usable(path, name):
                results.append({'name':name,'status':'blocked','reason':'Existing directory has no matching SKILL.md; preserved'})
                continue
            if path.is_symlink() or not previous:
                results.append({'name':name,'status':'existing'})
                continue
            previous_files = previous.get('files', {})
            if not previous_files or not matches(path, previous_files) or any((path / filename).exists() and filename not in previous_files for filename in files):
                results.append({'name':name,'status':'preserved','reason':'Personal modifications kept'})
                continue
            if matches(path, files):
                results.append({'name':name,'status':'current'})
                continue
            status = 'planned-update' if dry_run else 'updated'
        if not dry_run:
            source = Path(skill) / 'bundled' / name
            if status == 'installed':
                target.mkdir(parents=True, exist_ok=True)
                with tempfile.TemporaryDirectory(prefix='.arslanbek-skill-', dir=target) as temporary:
                    staged = Path(temporary) / name
                    for filename in files:
                        output = staged / filename
                        output.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(source / filename, output)
                    staged.rename(path)
            else:
                for filename in files:
                    replace_file(path / filename, (source / filename).read_bytes())
            if not usable(path, name) or not matches(path, files):
                raise ValueError('Installed skill verification failed: ' + name)
            state['skills'][name] = {'files':files, 'revision':entry.get('revision','')}
        results.append({'name':name,'status':status})
    if not dry_run:
        encoded = (json.dumps(state,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
        if not state_path.exists() or state_path.read_bytes() != encoded:
            replace_file(state_path, encoded)
    ready = all(item['status'] in ('installed','updated','current','existing','preserved') for item in results)
    return {'client':client,'ready':ready,'delivery':'native','skills_home':str(target),'skills':results}


def read(skill, name, path='SKILL.md'):
    entry = next((entry for entry in catalog(skill) if entry['name'] == name), None)
    if entry is None or path not in entry['files']:
        raise ValueError('Unknown bundled skill or file')
    source = Path(skill) / 'bundled' / name / relative_file(path)
    if source.stat().st_size > 200000:
        raise ValueError('Skill file is too large for one tool response')
    try:
        text = source.read_text(encoding='utf-8')
    except UnicodeError:
        raise ValueError('Only text resources can be read through MCP') from None
    return {'name':name,'path':path,'content':text,'files':list(entry['files']) if path == 'SKILL.md' else []}
