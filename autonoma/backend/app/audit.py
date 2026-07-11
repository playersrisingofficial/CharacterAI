"""Append-only audit trail.

Entries are only ever INSERTed — never updated or deleted — and every entry
is redacted before persistence so no raw secret can reach the log. Each audit
write also publishes an event to the live bus so the dashboard audit feed
updates in real time.
"""
from __future__ import annotations

import asyncio
from typing import Any

from . import database as db
from . import events
from .secrets_vault import redact


def record(
    *,
    action: str,
    status: str,
    verified: bool | None = None,
    agent_id: str | None = None,
    task_id: str | None = None,
    skill_id: str | None = None,
    skill_version: int | None = None,
    target: str | None = None,
    requires_approval: bool = False,
    approved_by_user: bool | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write one append-only audit entry and emit an audit_feed event.

    Per spec Section 9: a status of "success" must never coexist with
    verified=False. If the outcome could not be confirmed the caller should
    pass status="unverified" (or "failed"); we defensively correct here too.
    """
    if status == "success" and verified is False:
        status = "unverified"

    ev = events.Event(event_type="audit")
    entry = {
        "event_id": ev.event_id,
        "timestamp": ev.timestamp,
        "agent_id": agent_id,
        "task_id": task_id,
        "skill_id": skill_id,
        "skill_version": skill_version,
        "action": action,
        "target": target,
        "status": status,
        "verified": verified,
        "requires_approval": requires_approval,
        "approved_by_user": approved_by_user,
    }
    if extra:
        entry.update(extra)
    entry = redact(entry)

    db.execute(
        "INSERT INTO audit(event_id, timestamp, agent_id, task_id, skill_id, data) "
        "VALUES(?,?,?,?,?,?)",
        (ev.event_id, ev.timestamp, agent_id, task_id, skill_id, db.dumps(entry)),
    )

    # Fire the live audit event without blocking the caller if we happen to be
    # in a synchronous context.
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(events.bus.publish("audit", **entry))
    except RuntimeError:
        pass
    return entry


def list_entries(limit: int = 200, task_id: str | None = None) -> list[dict[str, Any]]:
    if task_id:
        rows = db.query(
            "SELECT data FROM audit WHERE task_id=? ORDER BY id DESC LIMIT ?", (task_id, limit)
        )
    else:
        rows = db.query("SELECT data FROM audit ORDER BY id DESC LIMIT ?", (limit,))
    # Already redacted at write time; redact again defensively on read.
    return [redact(db.loads(r["data"])) for r in rows]
