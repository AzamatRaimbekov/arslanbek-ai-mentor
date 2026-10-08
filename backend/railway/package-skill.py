"""Build the downloadable school skill with public connection settings only."""
from pathlib import Path
import base64
import hashlib
import json
import zipfile
import argparse

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / 'skills/arslanbek-ai-mentor'
OUTPUT = ROOT / 'dashboard/public/downloads/arslanbek-ai-mentor.zip'
INSTALL = Path(__file__).with_name('skill-install.py').read_text(encoding='utf-8')
INSTRUCTIONS = r'''ARSLANBEK — CLAUDE CODE, CODEX И ПРИЛОЖЕНИЯ С MCP

Используйте актуальное настольное приложение. Служебные команды выполняет
агент, сотруднику не нужно запускать install.py вручную.
Windows-пакет включает Python для x64 и ARM64; Bash и WSL для нативной Windows
не нужны. На macOS/Linux для локального скилла нужен Python 3.10+.
Обычный чат Claude Desktop использует отдельное расширение .mcpb.

CLAUDE DESKTOP — ОБЫЧНЫЙ ЧАТ
Скачайте arslanbek-claude-desktop.mcpb из кабинета школы.
В Claude: Settings → Extensions → Advanced settings → Install Extension.
Выберите файл. Claude сам запускает расширение и управляет Python через UV.
Нужен актуальный Claude с поддержкой MCPB 0.4/UV и интернет при первом запуске.
Начните новый чат: «Используй Arslanbek для моей рабочей задачи».
В обычном чате нет хука всех сообщений: передаются только запросы и сводки,
для которых агент вызвал инструменты расширения. Это не полный журнал чата.

CODEX
Для простой установки скачайте arslanbek-codex.zip.
Распакуйте папку arslanbek-ai-mentor в ~/.agents/skills/ (на Windows это
%USERPROFILE%\.agents\skills\). Вызовите $arslanbek-ai-mentor в новом чате.
Агент сам выполнит подключение по инструкции скилла; служебных команд для
сотрудника нет. При обновлении попросите агента сохранить личный профиль.
Альтернативный установщик для агента: python3 install.py --client codex
Скилл появится в ~/.agents/skills/arslanbek-ai-mentor; хуки — в ~/.codex/hooks.json.
Подключение MCP добавится в ~/.codex/config.toml с сохранением других настроек.
В новой сессии вызовите $arslanbek-ai-mentor. Просмотрите и доверьте хуки в Codex:
это требование самого приложения. Пока они не доверены, сбор запросов не автоматический.

ДРУГИЕ ПРИЛОЖЕНИЯ / DEEPSEEK
Попросите агента установить пакет: python3 install.py --client mcp
Установщик создаст mcp.json с локальным подключением. Добавьте его в настройки
MCP своего приложения, а SKILL.md — в его инструкции. Модель может быть любой.
Приложение должно поддерживать локальные MCP-инструменты. Без хуков запросы
передаются при вызове arslanbek_record_prompt агентом; полной автоматической
истории это не гарантирует. Сводки идут через arslanbek_submit_progress.
В обычном браузерном чате без MCP или исполнения команд сбор не поддерживается.

НАБЛЮДЕНИЯ О РАЗВИТИИ
Кабинет показывает карту навыков, подтверждения по разным задачам, теги промптов,
доступные и применённые инструменты и сигналы для проверки преподавателем.
Снимок выбранного приложения и проекта содержит имена инструментов и наличие
инструкций, хуков, тестов и CI. Команды и конфигурационные значения не загружаются.
В Claude Code содержимое события инструмента проверяется локально на признаки
секретов, затем отбрасывается. В Codex передаются только имена инструментов.
Сигнал не подтверждает факт утечки или отправки конкретному сервису.
Подробнее: references/observability.md.

КАРТА ПРОГРЕССА
Сводка содержит задачу, цель, этап, направления работы, подтверждения навыков,
вклад человека отдельно от ИИ, проверки, препятствия и следующие действия с
критериями готовности. Её составляет агент в текущей сессии, сервер показывает
данные в карточке участника и ленте «Сводки». Правила: references/progress-report.md.
Оценки относятся к наблюдаемым навыкам; отсутствие данных не означает слабый навык.

УСТАНОВКА В CLAUDE CODE
1. Полностью распакуйте архив.
2. Поместите папку arslanbek-ai-mentor в ~/.claude/skills/.
   В итоге файл должен находиться здесь:
   ~/.claude/skills/arslanbek-ai-mentor/SKILL.md
3. Начните новую сессию Claude Code в своём проекте и напишите:
   /arslanbek-ai-mentor
   Помоги мне с моей задачей.

Адрес школы уже настроен. Пароль администратора и API-ключи вводить не нужно.
Запускать install.py или другие команды вручную не требуется. При загрузке
скилл сам подключит отчёты и зарегистрирует участника на API школы.
Этот школьный пакет выдаётся участникам после оформления договора со школой.
Передача промптов и сводок включена в пакет; отдельный вопрос в чате не нужен.
Наставник сообщит, что отчёты подключены. Ранее сохранённое отключение сохраняется.
Хуки промптов начинают работать со следующего запуска сессии; до этого наставник
сам передаёт текущие запросы и сводки. Перезапускать сессию ради сводки не нужно.

КАКИЕ ДАННЫЕ ПОЛУЧИТ ШКОЛА
После подключения хуки работают в сессиях Claude Code во всех проектах на этом
компьютере: передают очищенные тексты промптов, псевдонимы проектов и сессий;
сводки наставника (задача, действия, результат, трудности, следующий шаг и
наблюдения об обучении); псевдонимы имени/email из Claude и Git, пользователя и компьютера, тип ОС.
Переписка до подключения задним числом не отправляется. Ответы агента и исходные
файлы проектов не загружаются. Локальный анонимизатор заменяет обнаруженные
персональные данные шаблонами; таблица замен остаётся на компьютере. Пароли
и ключи удаляются без восстановления. Распознавание всех личных сведений
в произвольном тексте не гарантируется. Подробнее: references/privacy.md.
Очистка отчётности не изменяет исходное сообщение, отправленное модели самого
приложения. Для этого требуется подключение анонимизатора на стороне клиента.

Данные видит администратор школы. Сводку пишет наставник в вашей рабочей сессии;
отдельный внешний ИИ-сервис для анализа этих данных сейчас не вызывается.
После содержательной задачи наставник отправляет сводку; в длинной сессии
получает напоминания на третьем промпте, затем каждые 15 промптов.
При отсутствии сети записи остаются в очереди. Следующая попытка отправки —
при новом запросе, сводке или запуске сессии Claude Code.

ПРОВЕРКА ДОСТАВКИ
Попросите Claude Code: «Проверь статус отправки данных Arslanbek» или выполните:
python3 ~/.claude/skills/arslanbek-ai-mentor/scripts/telemetry.py status
Доставку подтверждает дата в поле «последняя успешная доставка».
Пустая очередь сама по себе доставку не подтверждает.
После первой успешной передачи администратор увидит участника в кабинете.

ВЫКЛЮЧИТЬ СБОР
python3 ~/.claude/skills/arslanbek-ai-mentor/scripts/telemetry.py consent no
Сбор остановится, неотправленная очередь очистится. Ранее доставленные данные
автоматически не удаляются; по ним обращайтесь к администратору школы.

ОБНОВЛЕНИЕ
Скачайте и распакуйте свежий архив. Попросите Claude Code:
«Обнови Arslanbek из этой папки, запусти install.py --setup-only.
Сохрани мой личный профиль, уроки и прежний выбор сбора данных».
Участнику запускать скрипт вручную не нужно. Для тех, кому удобен терминал,
install.py сохранён как дополнительный способ установки.
'''


def main(contract=True):
    config = (SKILL / 'telemetry.conf').read_text(encoding="utf-8")
    if not any(line.startswith('SUPABASE_URL=https://') for line in config.splitlines()):
        raise SystemExit('Configure the public production endpoint before packaging.')
    values = dict(line.split('=', 1) for line in config.splitlines() if line and not line.startswith('#') and '=' in line)
    key = values.get('SUPABASE_ANON_KEY', '').strip()
    if key.startswith('eyJ'):
        payload = json.loads(base64.urlsafe_b64decode(key.split('.')[1] + '==='))
        if payload.get('role') != 'anon':
            raise SystemExit('Only the public anon key may be distributed with the skill.')
    elif not key.startswith('sb_publishable_'):
        raise SystemExit('Missing public anon / publishable key.')
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(OUTPUT, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(SKILL.rglob('*')):
            relative = path.relative_to(SKILL)
            if not path.is_file() or path.is_symlink() or any(part.startswith('.') or part in ('__pycache__', 'privacy') for part in relative.parts):
                continue
            if path.suffix == '.json':
                try:
                    private = json.loads(path.read_text(encoding='utf-8'))
                except (OSError, ValueError):
                    private = None
                if isinstance(private, dict) and 'namespace' in private and ('entries' in private or 'tokens' in private):
                    continue  # Local anonymizer vaults and restoration contexts must never ship.
            if path.name in ('telemetry.local.conf', 'school-policy.json') or path.suffix == '.pyc':
                continue
            if contract and relative.as_posix() == 'SKILL.md':
                content = path.read_text(encoding='utf-8')
                description = 'School coding mentor for enrolled students. Use automatically at the start of software building, debugging, planning, verification, or learning tasks, including direct requests to build, fix, or update code. Initializes school reporting under the existing school agreement and sends prompts and progress summaries without another onboarding question. Also use for учебные задачи, сделай приложение, почини код, помоги разобраться, научи, объясни, веди меня, проверь проект, and learning roadmaps.'
                content = ''.join('description: ' + description + '\n' if line.startswith('description: ') else line for line in content.splitlines(keepends=True))
                archive.writestr('arslanbek-ai-mentor/SKILL.md', content)
            elif not contract and relative.as_posix() == 'scripts/telemetry.py':
                content = ''.join('SKILL_VERSION = "telemetry-9-observability-standard"\n' if line.startswith('SKILL_VERSION = ') else line for line in path.read_text(encoding='utf-8').splitlines(keepends=True))
                archive.writestr(f'arslanbek-ai-mentor/{relative}', content)
            elif relative.as_posix() in ('references/student-profile.md', 'references/lessons.md'):
                title = 'Профиль ученика' if path.name == 'student-profile.md' else 'Уроки наставника'
                content = f'# {title}\n\nПока нет наблюдений. Заполняется по ходу работы.\n'
                if path.name == 'student-profile.md':
                    content += '\n' + '\n\n'.join(line for line in path.read_text(encoding="utf-8").splitlines() if line.startswith('## ') and line not in ('## Как пользоваться', '## Как дописывать', '## Что устаревает', '## Чего сюда не писать')) + '\n'
                archive.writestr(f'arslanbek-ai-mentor/{relative}', content)
            else:
                archive.write(path, f'arslanbek-ai-mentor/{relative}')
        archive.writestr('arslanbek-ai-mentor/.school-release', 'telemetry-9-observability\n' if contract else 'telemetry-9-observability-standard\n')
        if contract:
            policy = {"version": 1, "id": "school-enrollment-v1", "basis": "school_contract",
                      "server_url": values['SUPABASE_URL'].rstrip('/'),
                      "clients": ["claude-code", "codex", "mcp", "claude-desktop"],
                      "collection": ["prompts", "summaries", "student_profile", "account_device"]}
            archive.writestr('arslanbek-ai-mentor/school-policy.json', json.dumps(policy, ensure_ascii=False, indent=2) + '\n')
        archive.writestr('install.py', INSTALL)
        archive.writestr('START_HERE.txt', INSTRUCTIONS if contract else Path(__file__).with_name('multiclient-install.txt').read_text(encoding='utf-8'))
    print(f'Package: {OUTPUT.relative_to(ROOT)} ({OUTPUT.stat().st_size} bytes)')
    print('SHA256:', hashlib.sha256(OUTPUT.read_bytes()).hexdigest())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--standard', action='store_true', help='Сохранить обычный выбор сбора при установке; не включать школьную политику по договору.')
    parser.add_argument('--output', type=Path, help='Путь к архиву для изолированной сборки.')
    args = parser.parse_args()
    if args.output:
        OUTPUT = args.output.resolve()
        ROOT = OUTPUT.parent
    main(contract=not args.standard)
