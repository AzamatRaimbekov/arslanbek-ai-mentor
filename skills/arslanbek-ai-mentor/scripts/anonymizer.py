#!/usr/bin/env python3
"""Local reversible PII substitution. No network, models or third-party dependencies.

Secrets are removed irreversibly. PII mappings remain in a private local vault.
Restoration requires the allow-list issued for the particular prepared request.
This is pseudonymization, not a promise to detect all PII in arbitrary prose.
"""
import argparse
from contextlib import contextmanager
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import stat
import sys
import time
import uuid

VERSION = 1
MAX_BYTES = 1_000_000
MAX_ENTRIES = 50_000
CATEGORIES = {'PERSON', 'EMAIL', 'PHONE', 'ADDRESS', 'BIRTHDATE', 'ID', 'CARD',
              'IP', 'URL', 'PATH', 'USER', 'DEVICE', 'ORG', 'PROJECT', 'SESSION'}
TOKEN_RX = re.compile(r'\[(?:' + '|'.join(sorted(CATEGORIES)) + r')_[a-f0-9]{12}_[0-9]{4,8}\]')
SECRET = '[SECRET_REMOVED]'


class PrivacyError(RuntimeError):
    """Errors must not contain the original input or vault contents."""


SECRET_RULES = [
    (r'-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----', re.S),
    (r'\bsk-[A-Za-z0-9_\-]{20,}', 0),
    (r'\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_\-]{20,}|\bgithub_pat_[A-Za-z0-9_\-]{20,}', 0),
    (r'\b(?:AKIA|ASIA)[0-9A-Z]{16}\b', 0),
    (r'\bxox[abprs]-[A-Za-z0-9\-]{10,}', 0),
    (r'\bAIza[0-9A-Za-z_\-]{35}\b', 0),
    (r'\b(?:sbp|sb_secret|sb_publishable|vercel|glpat|npm)_[A-Za-z0-9_\-]{16,}', 0),
    (r'\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}', 0),
    (r'\b\d{8,10}:[A-Za-z0-9_\-]{35}\b', 0),
]
SECRET_RULES = [(re.compile(pattern, flags), SECRET) for pattern, flags in SECRET_RULES] + [
    (re.compile(r'(\b[a-z][a-z0-9+.\-]*://[^\s:/@]+:)[^\s@/]+(@)', re.I), r'\1' + SECRET + r'\2'),
    (re.compile(r'(\b(?:password|passwd|pwd|пароль|secret|token|api[_\-]?key|access[_\-]?key|client[_\-]?secret|private[_\-]?key)\b["\']?\s*[:=]\s*)["\']?[^\s"\',;]+', re.I), r'\1' + SECRET),
    (re.compile(r'(\bAuthorization\s*:\s*Bearer\s+)[^\s"\',;]+', re.I), r'\1' + SECRET),
]


def remove_secrets(text):
    for pattern, replacement in SECRET_RULES:
        text = pattern.sub(replacement, text)
    return text


FIELDS = {
    'email': 'EMAIL', 'e_mail': 'EMAIL', 'claude_email': 'EMAIL', 'git_email': 'EMAIL',
    'phone': 'PHONE', 'telephone': 'PHONE', 'mobile': 'PHONE', 'телефон': 'PHONE',
    'name': 'PERSON', 'full_name': 'PERSON', 'first_name': 'PERSON', 'last_name': 'PERSON',
    'person_name': 'PERSON', 'customer_name': 'PERSON', 'student_name': 'PERSON',
    'claude_name': 'PERSON', 'git_name': 'PERSON', 'фио': 'PERSON',
    'address': 'ADDRESS', 'home_address': 'ADDRESS', 'адрес': 'ADDRESS',
    'birthdate': 'BIRTHDATE', 'date_of_birth': 'BIRTHDATE', 'dob': 'BIRTHDATE',
    'passport': 'ID', 'passport_number': 'ID', 'ssn': 'ID', 'инн': 'ID', 'иин': 'ID',
    'card_number': 'CARD', 'credit_card': 'CARD', 'iban': 'ID', 'bank_account': 'ID',
    'os_user': 'USER', 'username': 'USER', 'user_name': 'USER',
    'hostname': 'DEVICE', 'claude_org': 'ORG', 'organization': 'ORG',
    'project': 'PROJECT', 'session_id': 'SESSION',
}
SECRET_FIELDS = {'password', 'passwd', 'pwd', 'пароль', 'secret', 'token', 'api_key',
                 'access_token', 'refresh_token', 'authorization', 'private_key', 'client_secret', 'credentials'}


def is_secret_key(key):
    key = key.lower().replace('-', '_')
    return key in SECRET_FIELDS or bool(re.search(r'(?:password|passwd|api_?key|private_?key|access_?key|secret|token)$', key))


ENUM_FIELDS = {
    'tag_source': {'keyword_rules'},
    'scope': {'user', 'project'},
    'coverage': {'selected_app_and_project', 'project_only', 'not_available'},
    'competency_id': {'prompt_engineering', 'context_engineering', 'harness', 'skill_authoring', 'plugin_authoring', 'frontend', 'backend', 'databases', 'testing', 'devops', 'security'},
    'actor': {'learner', 'agent', 'together', 'unknown'},
    'state': {'unknown', 'practiced', 'demonstrated', 'needs_practice'},
    'evidence_type': {'learner_action', 'learner_explanation', 'artifact_check', 'mentor_observation'},
    'kind': {'skill', 'plugin', 'mcp', 'harness', 'tool'},
    'action': {'used', 'created', 'configured'},
    'source': {'tool_hook', 'mentor_report'},
    'severity': {'info', 'warning', 'critical'},
    'category': {'api_key', 'private_key', 'credential', 'personal_contact', 'financial_id', 'confidential_marker'},
    'type': {'prompt', 'summary', 'registration', 'tool_event'},
    'client': {'claude-code', 'codex', 'mcp', 'claude-desktop'},
    'stage': {'discovery', 'planning', 'building', 'checking', 'delivery'},
    'status': {'in_progress', 'blocked', 'completed', 'strength', 'developing', 'needs_support', 'unknown', 'passed', 'failed', 'not_run'},
    'confidence': {'low', 'medium', 'high'}, 'owner': {'learner', 'mentor'},
}


def field_category(key, parents):
    category = FIELDS.get(key.lower().replace('-', '_'))
    # Skill/check names describe learning, not the identity of a person.
    if key == 'name' and any(part in ('skills', 'checks', 'directions') for part in parents):
        return None
    return category


PATTERNS = [
    ('EMAIL', re.compile(r'(?<![\w.+-])[\w.!#$%&\'*+/=?^`{|}~-]+@[\w-]+(?:\.[\w-]+)+', re.U)),
    ('URL', re.compile(r'\b(?:https?|ftp|postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis)://[^\s<>"\']+', re.I)),
    ('PATH', re.compile(r'(?:[A-Za-z]:[\\/](?:Users|Documents and Settings)[\\/]|/(?:Users|home)/)[^\s<>"\']+', re.I)),
    ('CARD', re.compile(r'(?<!\w)(?:\d[ -]?){15}\d(?!\w)')),
    ('PHONE', re.compile(r'(?<!\w)\+\d[\d ()\-]{7,24}\d(?!\w)')),
    ('PHONE', re.compile(r'(?<!\w)(?:\d{1,3}[ -])?\(?\d{3}\)?[ -]\d{3}[ -]\d{2}[ -]\d{2}(?!\w)')),
    ('ID', re.compile(r'(?<![\w])\d{8,20}(?![\w])')),
    ('IP', re.compile(r'(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?:/\d{1,2})?(?![\w.])')),
    ('IP', re.compile(r'(?<![\w:])(?:[0-9a-f]{0,4}:){2,7}[0-9a-f]{0,4}(?:%[\w-]+)?(?![\w:])', re.I)),
]
NAME = r'[A-ZА-ЯЁ][a-zа-яёA-ZА-ЯЁ\-]{1,40}(?:\s+[A-ZА-ЯЁ][a-zа-яёA-ZА-ЯЁ\-]{1,40}){0,3}'
LABELED = [
    ('PERSON', re.compile(r'(?i:\b(?:my name is|меня зовут|фио|full[ _]name|customer[ _]name|student[ _]name|имя)\s*[:=]?\s*["\']?)(?P<value>' + NAME + ')')),
    ('PERSON', re.compile(r'(?i:\b(?:Mr\.?|Mrs\.?|Ms\.?|Dr\.?|гражданин|гражданка)\s+)(?P<value>' + NAME + ')')),
    ('PERSON', re.compile(r'(?P<value>[А-ЯЁ][а-яё\-]{2,30}\s+[А-ЯЁ][а-яё\-]{2,30}(?:ович|евич|овна|евна)\s+[А-ЯЁ][а-яё\-]{2,30})')),
    ('PERSON', re.compile(r'(?P<value>\b[А-ЯЁ][а-яё\-]{1,35}\s+[А-ЯЁ][а-яё\-]{1,30}(?:ов|ев|ин|ова|ева|ина|ский|ская|енко|швили|дзе)\b)')),
    ('ADDRESS', re.compile(r'(?i:\b(?:home address|address|адрес)\s*[:=]\s*["\']?)(?P<value>[^\n;"\']{4,180})')),
    ('ADDRESS', re.compile(r'(?P<value>(?i:\b(?:ул\.|улица|проспект|пр-т|переулок)\s+)[^\n;"\']{4,150})')),
    ('BIRTHDATE', re.compile(r'(?i:\b(?:дата рождения|date of birth|birthdate|dob)\s*[:=]?\s*)(?P<value>\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4})')),
    ('ID', re.compile(r'(?i:\b(?:паспорт|passport|ssn|инн|иин|iban|account number|номер сч[её]та)\s*(?:номер|number)?\s*[:=#]?\s*)(?P<value>[A-Za-zА-Яа-я0-9][A-Za-zА-Яа-я0-9 -]{5,32})')),
]


def private_write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        raise PrivacyError('Private output must not be a symbolic link')
    temporary = path.with_name(path.name + '.' + secrets.token_hex(6) + '.tmp')
    fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False))
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


class Anonymizer:
    def __init__(self, vault):
        self.vault = Path(vault)

    @contextmanager
    def _transaction(self):
        self.vault.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.vault.is_symlink():
            raise PrivacyError('Privacy vault must not be a symbolic link')
        lock = self.vault.with_suffix('.lock')
        if lock.is_symlink():
            raise PrivacyError('Privacy lock must not be a symbolic link')
        flags = os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0)
        fd = os.open(lock, flags, 0o600)
        acquired = False
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise PrivacyError('Invalid privacy lock')
            if os.name == 'nt':
                import msvcrt
                if os.fstat(fd).st_size == 0:
                    os.write(fd, b'0')
                def acquire():
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                def release():
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                os.fchmod(fd, 0o600)
                def acquire():
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                def release():
                    fcntl.flock(fd, fcntl.LOCK_UN)
            deadline = time.monotonic() + 10
            while not acquired:
                try:
                    acquire()
                    acquired = True
                except (BlockingIOError, PermissionError):
                    if time.monotonic() >= deadline:
                        raise PrivacyError('Privacy vault is busy') from None
                    time.sleep(.02)
            if self.vault.exists():
                try:
                    if self.vault.stat().st_size > 20 * MAX_BYTES:
                        raise ValueError()
                    self.state = json.loads(self.vault.read_text(encoding='utf-8'))
                    self._validate_vault()
                except (OSError, ValueError, TypeError, KeyError):
                    raise PrivacyError('Privacy vault is invalid; sending is blocked') from None
                if os.name != 'nt':
                    self.vault.chmod(0o600)
            else:
                self.state = {'version': VERSION, 'namespace': secrets.token_hex(6), 'entries': {}}
            self.reverse = {(entry['category'], entry['value'], entry.get('kind', 'str')): token for token, entry in self.state['entries'].items()}
            if len(self.reverse) != len(self.state['entries']):
                raise PrivacyError('Privacy vault contains duplicate entries')
            self.issued = set()
            self.dirty = False
            yield
            if self.dirty:
                if len(json.dumps(self.state, ensure_ascii=False).encode('utf-8')) > 20 * MAX_BYTES:
                    raise PrivacyError('Privacy vault is full; sending is blocked')
                private_write(self.vault, self.state)
        finally:
            if acquired:
                release()
            os.close(fd)

    def _validate_vault(self):
        if not isinstance(self.state, dict):
            raise ValueError()
        if self.state['version'] != VERSION or not re.fullmatch(r'[a-f0-9]{12}', self.state['namespace']):
            raise ValueError()
        entries = self.state['entries']
        if not isinstance(entries, dict) or len(entries) > MAX_ENTRIES:
            raise ValueError()
        for token, entry in entries.items():
            if (not isinstance(entry, dict) or not TOKEN_RX.fullmatch(token) or entry['category'] not in CATEGORIES
                    or not isinstance(entry['value'], str) or len(entry['value']) > MAX_BYTES
                    or entry.get('kind', 'str') not in ('str', 'int', 'float')
                    or not token.startswith('[' + entry['category'] + '_' + self.state['namespace'] + '_')):
                raise ValueError()
            if entry.get('kind') == 'int':
                if str(int(entry['value'])) != entry['value']:
                    raise ValueError()
            elif entry.get('kind') == 'float':
                number = float(entry['value'])
                if not (-float('inf') < number < float('inf')):
                    raise ValueError()

    def _token(self, category, value):
        kind = 'int' if type(value) is int else 'float' if type(value) is float else 'str'
        value = remove_secrets(str(value))
        if not value or value == SECRET:
            return value
        if TOKEN_RX.fullmatch(value):
            if value in self.state['entries']:
                self.issued.add(value)
            return value
        pair = (category, value, kind)
        token = self.reverse.get(pair)
        if token is None:
            if len(self.state['entries']) >= MAX_ENTRIES:
                raise PrivacyError('Privacy vault is full; sending is blocked')
            number = len(self.state['entries']) + 1
            token = f'[{category}_{self.state["namespace"]}_{number:04d}]'
            self.state['entries'][token] = {'category': category, 'value': value, 'kind': kind}
            self.reverse[pair] = token
            self.dirty = True
        self.issued.add(token)
        return token

    def _register_fields(self, value, parents=()):
        if isinstance(value, dict):
            for key, child in value.items():
                if not isinstance(key, str):
                    raise PrivacyError('Expected JSON string keys')
                if is_secret_key(key):
                    continue
                category = field_category(key, parents)
                if category and isinstance(child, (str, int, float)) and not isinstance(child, bool):
                    self._token(category, child)
                self._register_fields(child, (*parents, key))
        elif isinstance(value, list):
            for child in value:
                self._register_fields(child, parents)

    def _segment(self, text):
        candidates = []
        for category, pattern in LABELED:
            for match in pattern.finditer(text):
                candidates.append((*match.span('value'), category))
        # Known account identities and explicitly registered entities are found
        # throughout prose too. Match literal text with word boundaries.
        known = [(value, category) for category, value, kind in self.reverse if kind == 'str' and category in {'PERSON', 'EMAIL', 'USER', 'DEVICE', 'ORG', 'ADDRESS'} and len(value) >= 3 and SECRET not in value]
        for value, category in sorted(known, key=lambda pair: len(pair[0]), reverse=True):
            pattern = re.compile(r'(?<!\w)' + re.escape(value) + r'(?!\w)', re.I)
            candidates.extend((*match.span(), category) for match in pattern.finditer(text))
        for category, pattern in PATTERNS:
            for match in pattern.finditer(text):
                raw = match.group()
                if category == 'PHONE' and not 10 <= len(re.sub(r'\D', '', raw)) <= 15:
                    continue
                if category == 'IP':
                    try:
                        ipaddress.ip_interface(raw)
                    except ValueError:
                        continue
                candidates.append((*match.span(), category))
        # Substitute original spans once. A URL containing a known name must
        # retain the original URL in the vault, not a nested replacement token.
        result, cursor = [], 0
        for start, end, category in sorted(candidates, key=lambda item: (item[0], -(item[1] - item[0]))):
            if start < cursor:
                continue
            result.append(text[cursor:start])
            result.append(self._token(category, text[start:end]))
            cursor = end
        result.append(text[cursor:])
        return ''.join(result)

    def _text(self, text):
        text = remove_secrets(text)
        # Keep already substituted tokens intact, including on queue retries.
        result, previous = [], 0
        for match in TOKEN_RX.finditer(text):
            result.append(self._segment(text[previous:match.start()]))
            result.append(match.group())
            if match.group() in self.state['entries']:
                self.issued.add(match.group())
            previous = match.end()
        result.append(self._segment(text[previous:]))
        return ''.join(result)

    def _walk(self, value, parents=()):
        if isinstance(value, str):
            if parents and parents[-1] in ('tags', 'harness') and value in {'prompt_engineering', 'context_engineering', 'harness', 'skill_authoring', 'plugin_authoring', 'frontend', 'backend', 'databases', 'testing', 'devops', 'security', 'intent:debug', 'intent:learn', 'intent:plan', 'intent:build', 'intent:review', 'project_instructions', 'version_control', 'ci_configuration', 'test_configuration', 'app_hooks'}:
                return value
            return self._text(value)
        if isinstance(value, list):
            return [self._walk(child, parents) for child in value]
        if isinstance(value, dict):
            result = {}
            for key, child in value.items():
                safe_key = self._text(key)
                if safe_key in result:
                    raise PrivacyError('Anonymized JSON keys collide')
                category = field_category(key, parents)
                if is_secret_key(key) and child:
                    safe_child = SECRET
                elif category and isinstance(child, (str, int, float)) and not isinstance(child, bool):
                    safe_child = self._token(category, child)
                elif isinstance(child, str) and child in ENUM_FIELDS.get(key, ()):
                    safe_child = child
                elif key == 'event_id' and isinstance(child, str):
                    # Event UUIDs are random transport IDs, needed unchanged for
                    # retries. Arbitrary user content never gets this exemption.
                    try:
                        if str(uuid.UUID(child)) != child:
                            raise ValueError()
                    except ValueError:
                        safe_child = self._walk(child, (*parents, key))
                    else:
                        safe_child = child
                else:
                    safe_child = self._walk(child, (*parents, key))
                result[safe_key] = safe_child
            return result
        if type(value) is int and abs(value) >= 100_000_000:
            return self._token('ID', value)
        return value

    def prepare(self, value, entities=()):
        try:
            if len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8')) > MAX_BYTES:
                raise PrivacyError('Privacy input is too large')
        except (TypeError, ValueError):
            raise PrivacyError('Expected finite JSON data or text') from None
        with self._transaction():
            for entry in entities:
                if not isinstance(entry, dict) or entry.get('category') not in CATEGORIES or not isinstance(entry.get('value'), str):
                    raise PrivacyError('Invalid local entity dictionary')
                self._token(entry['category'], entry['value'])
            self._register_fields(value)
            cleaned = self._walk(value)
            # Registering an identity alone must not allow an untrusted response
            # to restore it. Only tokens actually in this request are permitted.
            used = set(TOKEN_RX.findall(json.dumps(cleaned, ensure_ascii=False))) & self.state['entries'].keys()
            context = {'version': VERSION, 'namespace': self.state['namespace'], 'tokens': sorted(used)}
        return cleaned, context

    def restore(self, value, context):
        with self._transaction():
            if (not isinstance(context, dict) or context.get('version') != VERSION
                    or context.get('namespace') != self.state['namespace'] or not isinstance(context.get('tokens'), list)):
                raise PrivacyError('Restoration context does not match the local vault')
            if not all(isinstance(token, str) for token in context['tokens']):
                raise PrivacyError('Invalid restoration allow-list')
            allowed = set(context['tokens'])
            if not allowed <= self.state['entries'].keys():
                raise PrivacyError('Restoration context contains unknown tokens')
            def walk(child):
                if isinstance(child, str):
                    if child in allowed:
                        entry = self.state['entries'][child]
                        if entry.get('kind') == 'int':
                            return int(entry['value'])
                        if entry.get('kind') == 'float':
                            return float(entry['value'])
                    # One substitution pass. Never interpret restored strings as tokens.
                    return TOKEN_RX.sub(lambda match: self.state['entries'][match.group()]['value'] if match.group() in allowed else match.group(), child)
                if isinstance(child, list):
                    return [walk(item) for item in child]
                if isinstance(child, dict):
                    restored = {}
                    for key, item in child.items():
                        restored_key = walk(key)
                        if restored_key in restored:
                            raise PrivacyError('Restored JSON keys collide')
                        restored[restored_key] = walk(item)
                    return restored
                return child
            return walk(value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['prepare', 'restore'])
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--context', type=Path, required=True, help='Local context file. Never send it or the vault to a model.')
    parser.add_argument('--vault', type=Path, default=Path(os.environ.get('ARSLANBEK_STATE', Path.home() / '.claude/.arslanbek')) / 'privacy/vault.json')
    parser.add_argument('--entities', type=Path, help='Optional local JSON array of category/value pairs.')
    parser.add_argument('--json', action='store_true', help='Process all strings in a JSON document.')
    args = parser.parse_args()
    try:
        if args.input.stat().st_size > MAX_BYTES:
            raise PrivacyError('Privacy input is too large')
        paths = [path.resolve() for path in (args.input, args.output, args.context, args.vault)]
        if len(set(paths)) != len(paths):
            raise PrivacyError('Input, output, context and vault need separate paths')
        raw = args.input.read_text(encoding='utf-8')
        value = json.loads(raw) if args.json else raw
        anonymizer = Anonymizer(args.vault)
        if args.operation == 'prepare':
            entities = json.loads(args.entities.read_text(encoding='utf-8')) if args.entities else []
            output, context = anonymizer.prepare(value, entities)
            private_write(args.context, context)
        else:
            output = anonymizer.restore(value, json.loads(args.context.read_text(encoding='utf-8')))
        private_write(args.output, output)
        print('Обработка завершена. Результат сохранён локально; содержимое не выводится в журнал.')
    except (PrivacyError, OSError, ValueError, TypeError, KeyError):
        print('Обработка остановлена. Проверьте входные файлы и локальное хранилище; данные не отправлены.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    sys.exit(main())
