"""Versioned, provider-neutral progress reports. No inference happens on the server."""
import json


def text(limit=2000):
    return {"type": "string", "maxLength": limit}


def obj(properties, required=None):
    return {"type": "object", "properties": properties, "required": required or list(properties), "additionalProperties": False}


def items(schema, limit=12):
    return {"type": "array", "items": schema, "maxItems": limit}


def enum(*values):
    return {"type": "string", "enum": list(values)}


SCHEMA = obj({
    "version": {"type": "integer", "enum": [1]},
    "task": text(300), "goal": text(),
    "stage": enum("discovery", "planning", "building", "checking", "delivery"),
    "status": enum("in_progress", "blocked", "completed"),
    "directions": items(text(120), 8),
    "learner_actions": items(text()), "agent_actions": items(text()),
    "result": text(5000),
    "skills": items(obj({"name": text(120), "status": enum("strength", "developing", "needs_support", "unknown"),
                         "evidence": text(), "next_action": text()})),
    "checks": items(obj({"name": text(300), "status": enum("passed", "failed", "not_run"), "evidence": text()})),
    "blockers": items(text()),
    "next_steps": items(obj({"action": text(), "done_when": text(), "owner": enum("learner", "mentor")}), 5),
    "confidence": enum("low", "medium", "high"), "limitations": items(text(), 8),
    "learning_evidence": items(obj({
        "competency_id": enum("prompt_engineering", "context_engineering", "harness", "skill_authoring", "plugin_authoring", "frontend", "backend", "databases", "testing", "devops", "security"),
        "state": enum("unknown", "practiced", "demonstrated", "needs_practice"),
        "actor": enum("learner", "agent", "together", "unknown"),
        "evidence_type": enum("learner_action", "learner_explanation", "artifact_check", "mentor_observation"),
        "evidence": text(), "next_action": text(),
    })),
    "tool_usage": items(obj({"kind": enum("skill", "plugin", "mcp", "harness", "tool"),
                             "tool_id": text(160), "action": enum("used", "created", "configured"),
                             "actor": enum("learner", "agent", "together", "unknown"), "evidence": text()})),
}, required=["version", "task", "goal", "stage", "status", "directions", "learner_actions", "agent_actions", "result", "skills", "checks", "blockers", "next_steps", "confidence", "limitations"])


def validate(value, schema=SCHEMA, path="report"):
    kind = schema["type"]
    correct = {"object": isinstance(value, dict), "array": isinstance(value, list),
               "string": isinstance(value, str), "integer": type(value) is int}[kind]
    if not correct:
        raise ValueError(f"{path}: expected {kind}")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{path}: unsupported value")
    if kind == "object":
        if set(schema["required"]) - value.keys() or value.keys() - schema["properties"].keys():
            raise ValueError(f"{path}: missing or unknown fields")
        for name, child in value.items():
            validate(child, schema["properties"][name], f"{path}.{name}")
    elif kind == "array":
        if len(value) > schema["maxItems"]:
            raise ValueError(f"{path}: too many items")
        for index, child in enumerate(value):
            validate(child, schema["items"], f"{path}[{index}]")
    elif kind == "string" and len(value) > schema.get("maxLength", 100000):
        raise ValueError(f"{path}: text is too long")
    if path == "report":
        if not value["task"].strip() or not value["result"].strip():
            raise ValueError("report: task and result must not be empty")
        if not value["next_steps"]:
            raise ValueError("report: describe at least one next step, including after completion")
        if any(not s["action"].strip() or not s["done_when"].strip() for s in value["next_steps"]):
            raise ValueError("report: next steps need an action and completion criterion")
        if any(s["status"] != "unknown" and not s["evidence"].strip() for s in value["skills"]):
            raise ValueError("report: skill observations require evidence")
        for item in value.get('learning_evidence', []):
            if item['state'] != 'unknown' and not item['evidence'].strip():
                raise ValueError('report: learning observations require evidence')
            if item['state'] == 'demonstrated' and item['actor'] != 'learner':
                raise ValueError('report: independent demonstration requires learner evidence')
        if any(not item['tool_id'].strip() or not item['evidence'].strip() for item in value.get('tool_usage', [])):
            raise ValueError('report: tool use requires an identifier and evidence')
        if len(json.dumps(value, ensure_ascii=False).encode()) > 60000:
            raise ValueError("report: maximum size is 60 KB")
    return value


STAGES = {"discovery": "Понимание задачи", "planning": "Планирование", "building": "Реализация", "checking": "Проверка", "delivery": "Передача результата"}


def flat_summary(report):
    return {
        "stage": STAGES[report["stage"]], "summary": report["result"],
        "strengths": "\n".join(s["name"] + ": " + s["evidence"] for s in report["skills"] if s["status"] == "strength"),
        "struggles": "\n".join(s["name"] + ": " + s["evidence"] for s in report["skills"] if s["status"] in ("developing", "needs_support")),
        "next_step": "\n".join(s["action"] + " Готово, когда: " + s["done_when"] for s in report["next_steps"]),
    }
