#!/usr/bin/env python3
"""Packaged as install.py at the root of the school download."""
import argparse
import importlib.util
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys


NOTICE = """ARSLANBEK — УСТАНОВКА

Если включить сбор, школа будет получать данные из выбранного приложения
ВО ВСЕХ ПРОЕКТАХ на этом компьютере:
  • тексты ваших запросов, имена проектов и идентификаторы сессий;
  • сводки наставника: задача, действия, результат, трудности и следующий шаг;
  • профиль обучения, имя/email из доступного аккаунта Claude и Git, имя компьютера и ОС;
  • название приложения и модели, если приложение передало его.
Данные доступны администратору школы. Отдельный внешний ИИ-сервис для анализа
этих данных сейчас не вызывается. Прошлая переписка, ответы агента и исходные
файлы проектов не загружаются. Типовые секреты скрываются по шаблонам,
но удаление всех секретов не гарантируется.

Сбор можно выключить в любой момент:
python3 scripts/telemetry.py consent no
Команду запускают из папки скилла выбранного приложения. Она остановит сбор
в этом приложении и очистит его неотправленную очередь. Уже доставленные данные
автоматически не удалятся; по ним обращайтесь к администратору школы.
"""


def load_telemetry(skill):
    spec = importlib.util.spec_from_file_location('arslanbek_telemetry', skill / 'scripts/telemetry.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def configure_codex(codex_home, target):
    spec = importlib.util.spec_from_file_location('arslanbek_client_setup', target / 'scripts/client_setup.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.configure_codex(codex_home, target)


def choose_collection(previous, choose_again=False):
    print(NOTICE, flush=True)
    if previous in ('yes', 'no') and not choose_again:
        print('Сохраняем ваш прежний выбор: сбор ' + ('включён.' if previous == 'yes' else 'выключен.'))
        print('Для изменения выбора запустите: python3 install.py --choose-collection')
        return previous
    print('1 — Установить и включить сбор (согласен на передачу перечисленных данных школе)')
    print('2 — Установить без сбора данных')
    print('0 — Отмена (также Enter)')
    while True:
        try:
            choice = input('Ваш выбор [0]: ').strip()
        except (EOFError, KeyboardInterrupt):
            choice = '0'
        if choice in ('', '0'):
            print('\nУстановка отменена. Настройки не изменены.')
            return None
        if choice in ('1', '2'):
            return 'yes' if choice == '1' else 'no'
        print('Введите 1, 2 или 0.')


def main():
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description='Установить Arslanbek и выбрать режим сбора данных.')
    parser.add_argument('--client', choices=('claude-code', 'codex', 'mcp'), default='claude-code')
    parser.add_argument('--codex-home', type=Path, default=Path.home() / '.codex')
    parser.add_argument('--agents-home', type=Path, default=Path.home() / '.agents')
    parser.add_argument('--mcp-home', type=Path, default=Path.home() / '.arslanbek/mcp')
    parser.add_argument('--claude-home', type=Path, default=Path.home() / '.claude')
    parser.add_argument('--choose-collection', action='store_true', help='Заново выбрать режим сбора при обновлении.')
    parser.add_argument('--setup-only', action='store_true', help='Установить файлы и хуки без изменения выбора сбора; для автоматического обновления агентом.')
    args = parser.parse_args()
    if args.setup_only and args.choose_collection:
        parser.error('--setup-only нельзя совмещать с --choose-collection')
    source = Path(__file__).resolve().parent / 'arslanbek-ai-mentor'
    base = args.claude_home if args.client == 'claude-code' else args.agents_home if args.client == 'codex' else args.mcp_home
    target = (base / 'skills/arslanbek-ai-mentor').resolve()
    os.environ['ARSLANBEK_CLIENT'] = args.client
    print('Приложение: ' + args.client)
    telemetry = load_telemetry(source)
    previous = telemetry.consent()
    school = telemetry.school_policy()
    answer = previous if args.setup_only or (school and not args.choose_collection) else choose_collection(previous, args.choose_collection)
    if answer is None:
        return

    personal = {'references/student-profile.md', 'references/lessons.md', 'telemetry.local.conf'}
    for path in source.rglob('*'):
        if not path.is_file() or '__pycache__' in path.parts or path.suffix == '.pyc':
            continue
        relative = path.relative_to(source)
        destination = target / relative
        if relative.as_posix() in personal and destination.exists():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
    (target / '.arslanbek-client.json').write_text(json.dumps({'client': args.client}), encoding='utf-8')
    if args.client != 'claude-code':
        shutil.copy2(target / 'references/portable-skill.md', target / 'SKILL.md')
    if args.client in ('claude-code', 'codex'):
        hook_home = args.claude_home if args.client == 'claude-code' else args.codex_home
        subprocess.run([sys.executable, str(target / 'scripts/install-telemetry-hooks.py'),
                        '--claude-home', str(hook_home), '--skill-dir', str(target), '--client', args.client], check=True)
    if args.client == 'codex':
        configure_codex(args.codex_home, target)
    if args.client == 'mcp':
        connection = {'mcpServers': {'arslanbek': {'command': sys.executable, 'args': [str(target / 'scripts/mcp-server.py')]}}}
        (target / 'mcp.json').write_text(json.dumps(connection, ensure_ascii=False, indent=2), encoding='utf-8')
        print('Подключите локальный MCP в своём приложении: ' + str(target / 'mcp.json'))
        print('Для работы наставника загрузите SKILL.md из этой же папки в инструкции приложения.')
    telemetry = load_telemetry(target)
    activated = telemetry.ensure_school_authorization() if school and not args.choose_collection else False
    if activated:
        answer = telemetry.consent()
        print('Школьный пакет: передача промптов и сводок включена по ранее оформленному договору.')
    if answer == 'yes':
        print('Проверяем отправку. При недоступном сервере записи останутся в очереди.', flush=True)
    if answer and answer != previous and not activated:
        telemetry.cmd_consent(argparse.Namespace(answer=answer, source='installer', wait=True))
    elif answer == 'yes':
        telemetry.flush()
    if args.client == 'claude-code':
        print('Скилл установлен. В новой сессии Claude Code напишите: /arslanbek-ai-mentor')
    elif args.client == 'codex':
        print('Скилл установлен. В новой сессии Codex напишите: $arslanbek-ai-mentor')
        print('В Codex просмотрите и доверьте хуки Arslanbek. Пока хуки не доверены, автоматический сбор запросов не запускается.')
    else:
        print('После подключения MCP попросите приложение вызвать arslanbek_status.')
    print('Выключить сбор: ' + sys.executable + ' ' + str(target / 'scripts/telemetry.py') + ' consent no')
    if answer:
        print('Повторного вопроса о согласии в чате не будет.')
    if answer == 'yes':
        telemetry.cmd_status(None)
        print('Доставку подтверждает дата последней успешной доставки; пустая очередь сама по себе её не подтверждает.')
    elif answer == 'no':
        print('Сбор выключен. Данные для школы не собираются.')
    else:
        print('Выбор сбора не задан. Наставник объяснит передачу данных при первом использовании.')
    print('Обновления — из кабинета школы. Подробности — в START_HERE.txt.')


if __name__ == '__main__':
    main()
