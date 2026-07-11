"""Task persistence, state transitions, logs, and action timeline (Section 5)."""
from __future__ import annotations

import time
import uuid
from typing import Any

from .. import database as db
from .. import events
from ..secrets_vault import redact

VALID_STATUS = {
    "queued", "running", "paused", "waiting_approval",
    "completed", "cancelled", "failed",
}
TERMINAL = {"completed", "cancelled", "failed"}


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def create_task(payload: dict[str, Any]) -> dict[str, Any]:
    task_id = f"task_{uuid.uuid4().hex[:12]}"
    now = _now()
    task = {
        "task_id": task_id,
        "title": payload.get("title", "Untitled task"),
        "description": payload.get("description", ""),
        "assigned_agent_count": int(payload.get("assigned_agent_count", 1)),
        "coordination_mode": payload.get("coordination_mode", "independent"),
        "skill_refs": payload.get("skill_refs", []),
        "input": payload.get("input", {}),
        "status": "queued",
        "progress": 0.0,
        "current_step": None,
        "current_skill": None,
        "current_skill_version": None,
        "input_behavior_mode": payload.get("input_behavior_mode", "human_like"),
        "assigned_agents": [],
        "last_action": None,
        "next_action": None,
        "error": None,
        "created_at": now,
        "started_at": None,
    }
    db.execute(
        "INSERT INTO tasks(task_id, title, status, data, created_at, updated_at) VALUES(?,?,?,?,?,?)",
        (task_id, task["title"], task["status"], db.dumps(task), now, now),
    )
    return task


def get_task(task_id: str) -> dict[str, Any] | None:
    row = db.query_one("SELECT data FROM tasks WHERE task_id=?", (task_id,))
    return db.loads(row["data"]) if row else None


def list_tasks(status: str | None = None) -> list[dict[str, Any]]:
    if status:
        rows = db.query("SELECT data FROM tasks WHERE status=? ORDER BY created_at DESC", (status,))
    else:
        rows = db.query("SELECT data FROM tasks ORDER BY created_at DESC")
    return [db.loads(r["data"]) for r in rows]


def save_task(task: dict[str, Any]) -> None:
    db.execute(
        "UPDATE tasks SET status=?, title=?, data=?, updated_at=? WHERE task_id=?",
        (task["status"], task["title"], db.dumps(task), _now(), task["task_id"]),
    )


def update(task_id: str, **changes: Any) -> dict[str, Any] | None:
    task = get_task(task_id)
    if task is None:
        return None
    task.update(changes)
    save_task(task)
    return task


def add_log(task_id: str, level: str, message: str, data: dict | None = None) -> None:
    db.execute(
        "INSERT INTO task_logs(task_id, timestamp, level, message, data) VALUES(?,?,?,?,?)",
        (task_id, _now(), level, message, db.dumps(redact(data)) if data else None),
    )


def get_logs(task_id: str, limit: int = 500) -> list[dict[str, Any]]:
    rows = db.query(
        "SELECT timestamp, level, message, data FROM task_logs WHERE task_id=? ORDER BY id ASC LIMIT ?",
        (task_id, limit),
    )
    return [
        {"timestamp": r["timestamp"], "level": r["level"], "message": r["message"],
         "data": db.loads(r["data"])}
        for r in rows
    ]


def add_timeline(task_id: str, *, step: int | None, action: str | None, status: str,
                 message: str, data: dict | None = None) -> None:
    db.execute(
        "INSERT INTO timeline(task_id, timestamp, step, action, status, message, data) "
        "VALUES(?,?,?,?,?,?,?)",
        (task_id, _now(), step, action, status, message, db.dumps(redact(data)) if data else None),
    )


def get_timeline(task_id: str) -> list[dict[str, Any]]:
    rows = db.query(
        "SELECT timestamp, step, action, status, message, data FROM timeline "
        "WHERE task_id=? ORDER BY id ASC", (task_id,),
    )
    return [
        {"timestamp": r["timestamp"], "step": r["step"], "action": r["action"],
         "status": r["status"], "message": r["message"], "data": db.loads(r["data"])}
        for r in rows
    ]
