#!/usr/bin/env python3
"""Local stdio MCP bridge for any compatible application/model. Python stdlib only."""
import contextlib
import io
import json
import os
import sys
import uuid
import telemetry as t
from progress_report import SCHEMA

VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
TOOLS = [
    {'name': 'arslanbek_capture_tool', 'description': 'Обработчик доверенного PostToolUse-хука. Записывает только название инструмента и источник, без аргументов, файлов и результата инструмента.',
     'inputSchema': {'type': 'object', 'properties': {'event': {'type': 'object', 'properties': {'tool_name': {'type': 'string'}, 'tool_use_id': {'type': 'string'}, 'session_id': {'type': 'string'}, 'cwd': {'type': 'string'}}, 'required': ['tool_name'], 'additionalProperties': False}}, 'required': ['event'], 'additionalProperties': False}},
    {"name": "arslanbek_capture_event", "description": "Обработчик доверенного UserPromptSubmit-хука Codex. Вызывается приложением, не дублируй вручную. Не блокирует работу при отключённом сборе.",
     "inputSchema": {"type": "object", "properties": {"event": {"type": "object", "properties": {"prompt": {"type": "string"}, "session_id": {"type": "string"}, "cwd": {"type": "string"}}, "required": ["prompt"], "additionalProperties": False}}, "required": ["event"], "additionalProperties": False}},
    {"name": "arslanbek_flush", "description": "Повторить доставку уже сохранённой очереди Arslanbek. Учитывает сохранённое отключение сбора.",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "arslanbek_status", "description": "Проверить согласие и доставку данных школы. Не включает сбор.",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}, "annotations": {"readOnlyHint": True}},
    {"name": "arslanbek_submit_progress", "description": "Отправить сводку текущей задачи школе после согласия участника. Разделяй действия человека и ИИ; навыки подтверждай наблюдениями. Укажи ближайшее действие и критерий его готовности. Не используй для общей оценки пригодности к работе.",
     "inputSchema": {"type": "object", "properties": {"report": SCHEMA, "session": {"type": "string"}, "project": {"type": "string"}, "model": {"type": "string"}, "level": {"type": ["integer", "null"], "minimum": 0, "maximum": 5}}, "required": ["report"], "additionalProperties": False}},
    {"name": "arslanbek_record_prompt", "description": "Записать текущий запрос участника при включённом сборе. Для приложений без автоматического хука; не пересылай прошлую переписку и не дублируй события хука.",
     "inputSchema": {"type": "object", "properties": {"prompt": {"type": "string", "maxLength": 20000}, "session": {"type": "string"}, "project": {"type": "string"}, "model": {"type": "string"}}, "required": ["prompt"], "additionalProperties": False}},
]


def tool_result(value, error=False):
    return {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False)}], "isError": error}


def call_tool(name, args):
    if name == 'arslanbek_capture_tool':
        event = args.get('event')
        if not isinstance(event, dict):
            raise ValueError('Tool event must be an object')
        t.capture_tool(event)
        return tool_result({'processed': True, 'hookSpecificOutput': {'hookEventName': 'PostToolUse'}})
    if not isinstance(args, dict):
        raise ValueError("arguments must be an object")
    if name == 'arslanbek_capture_event':
        event = args.get('event')
        if not isinstance(event, dict) or not isinstance(event.get('prompt'), str) or len(event['prompt']) > 100000:
            raise ValueError('Expected a current prompt event')
        if any(k in event and not isinstance(event[k], str) for k in ('session_id', 'cwd')):
            raise ValueError('Invalid prompt context')
        with contextlib.redirect_stdout(io.StringIO()) as out:
            previous = sys.stdin
            try:
                sys.stdin = io.StringIO(json.dumps(event, ensure_ascii=False))
                t.cmd_prompt(None)
            finally:
                sys.stdin = previous
        return tool_result({'hookSpecificOutput': {'hookEventName': 'UserPromptSubmit', 'additionalContext': out.getvalue()}})
    if name == 'arslanbek_flush':
        return tool_result({'sent': t.flush(), 'pending': len(list(t.QUEUE.glob('*.json')))})
    if name == "arslanbek_status":
        with contextlib.redirect_stdout(io.StringIO()) as out:
            t.cmd_status(None)
        return tool_result({"status": out.getvalue(), "client": t.CLIENT})
    if name not in {tool["name"] for tool in TOOLS}:
        raise ValueError("Unknown tool")
    t.ensure_school_authorization()
    if t.consent() != "yes" or t.config()[2]:
        raise ValueError("Сбор для этого приложения выключен или школьная политика отсутствует. Сохранённое отключение не переопределяется.")
    for key in ("session", "project", "model"):
        if key in args and (not isinstance(args[key], str) or len(args[key]) > 200):
            raise ValueError(key + " must be a short string")
    if name == "arslanbek_submit_progress":
        event = t.submit_report(args.get("report"), args.get("session", ""), args.get("project", ""), args.get("model", ""), args.get("level"))
    else:
        prompt = args.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 20000:
            raise ValueError("prompt must contain 1..20000 characters")
        event = str(uuid.uuid4())
        t.enqueue({"type": "prompt", "event_id": event, "prompt": t.redact(prompt), "client": t.CLIENT,
                   "session_id": args.get("session", "")[:100], "project": args.get("project", ""), "model": args.get("model", "")[:120],
                   'observability': t.observation_module().observe_prompt(prompt, os.getcwd(), t.CLIENT)})
    t.flush()
    pending = any(json.loads(path.read_text(encoding="utf-8")).get("event_id") == event for path in t.QUEUE.glob("*.json"))
    return tool_result({"event_id": event, "delivery": "queued" if pending else "delivered", "client": t.CLIENT})


def main():
    t.configure_stdio()
    initialized = False
    for line in sys.stdin:
        request = None
        try:
            if len(line) > 200000:
                raise ValueError("Request too large")
            request = json.loads(line)
            if not isinstance(request, dict) or request.get("jsonrpc") != "2.0":
                raise ValueError("Invalid JSON-RPC request")
            if "id" not in request:
                continue
            method, params = request.get("method"), request.get("params", {})
            if method == "initialize":
                version = params.get("protocolVersion")
                result = {"protocolVersion": version if version in VERSIONS else VERSIONS[0],
                          "capabilities": {"tools": {}, "prompts": {}}, "serverInfo": {"name": "arslanbek", "version": "8.1.0"},
                          "instructions": guidance()}
                # The desktop host starts this server. No participant-run installer
                # is necessary. Existing opt-outs and the off switch take priority.
                t.ensure_school_authorization()
                if t.consent() == 'yes' and not t.config()[2]:
                    t.spawn_flush()
                initialized = True
            elif method == "ping":
                result = {}
            elif not initialized:
                raise ValueError("Initialize the server first")
            elif method == "tools/list":
                result = {"tools": TOOLS}
            elif method == 'prompts/list':
                result = {'prompts': [{'name': 'arslanbek_mentor', 'description': 'Наставник Arslanbek: текущая задача, наблюдения о навыках и отчёт школе.'}]}
            elif method == 'prompts/get':
                if params.get('name') != 'arslanbek_mentor':
                    raise ValueError('Unknown prompt')
                result = {'messages': [{'role': 'user', 'content': {'type': 'text', 'text': guidance()}}]}
            elif method == "tools/call":
                try:
                    result = call_tool(params.get("name"), params.get("arguments", {}))
                except (ValueError, OSError, TypeError, KeyError, RuntimeError) as error:
                    result = tool_result({"error": str(error) if isinstance(error, ValueError) else type(error).__name__}, True)
            else:
                print(json.dumps({"jsonrpc": "2.0", "id": request["id"], "error": {"code": -32601, "message": "Method not found"}}), flush=True)
                continue
            response = {"jsonrpc": "2.0", "id": request["id"], "result": result}
        except (ValueError, TypeError, KeyError, AttributeError):
            response = {"jsonrpc": "2.0", "id": request.get("id") if isinstance(request, dict) else None,
                        "error": {"code": -32600, "message": "Invalid request"}}
        print(json.dumps(response, ensure_ascii=False), flush=True)


def guidance():
    return ('Помогай участнику школы Arslanbek выполнить рабочую задачу и понять решение. '
            'Каждый финальный ответ дай понятными блоками в чате и дополнительно как HTML с тем же содержанием. '
            'HTML содержит читаемые заголовки, цветные акценты и карточки. Если доступна папка скилла, '
            'используй references/html-answer.md и scripts/render_html.py; иначе создай HTML-артефакт '
            'или полный самостоятельный HTML в блоке html, честно обозначив ограничение. '
            'Дай ссылку только на реально созданный файл. Не открывай браузер автоматически и не публикуй HTML. '
            'Короткий ответ тоже имеет HTML-версию; явное «только чат» отменяет HTML на выбранный период. '
            'Объявления хода работы и отчёты школе сохраняют свой формат. HTML-ответы не отправляй в учебную телеметрию. '
            'Уточняй только недостающий контекст. Школьный пакет подключает передачу по ранее оформленному договору; '
            'один раз сообщи участнику, что новые запросы и сводки передаются школе. Уважай отключение сбора. '
            'В обычном чате Claude Desktop нет UserPromptSubmit-хука: при включённом сборе используй '
            'arslanbek_record_prompt только для нового текущего запроса, не читай прошлую переписку. '
            'В Codex доверенный хук уже записывает запросы; не дублируй их. '
            'После содержательной задачи или препятствия используй arslanbek_submit_progress: раздели действия человека и ИИ, '
            'укажи этап, направления, навыки с наблюдениями, проверки, препятствия, следующий шаг и критерий готовности. '
            'Добавляй learning_evidence и tool_usage по references/observability.md: наблюдения о навыках и реальном использовании инструментов. Твой код не доказывает навык человека. Не оценивай личность или пригодность к найму. '
            'Сводку составляет текущий агент. Серверный ИИ не вызывается. Очередь не равна доставке. '
            'arslanbek_status показывает статус. Пользователь не должен вручную запускать служебные скрипты.')


if __name__ == "__main__":
    main()
