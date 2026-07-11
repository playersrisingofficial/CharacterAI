"""Task API (Section 5)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query, WebSocket

from ..core import skills as sk
from ..core import tasks as t
from ..events import bus
from ..secrets_vault import redact
from .streams import sse_response, ws_pump

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])

_TASK_EVENTS = {
    "task_created", "task_queued", "task_started", "task_step_started",
    "task_step_completed", "task_waiting_for_approval", "task_paused",
    "task_resumed", "task_cancelled", "task_failed", "task_completed",
}


@router.post("", status_code=201)
@router.post("/", status_code=201)
async def create_task(payload: dict[str, Any] = Body(...)):
    # Validate referenced skills exist up-front (explicit failure, Section 7).
    for ref in payload.get("skill_refs", []):
        try:
            sk.validate_skill_action_ref(ref.get("skill_id"))
        except sk.SkillError as exc:
            raise HTTPException(exc.status, str(exc))
    task = t.create_task(payload)
    await bus.publish("task_created", task_id=task["task_id"], title=task["title"])
    await bus.publish("task_queued", task_id=task["task_id"])
    return redact(task)


@router.get("")
@router.get("/")
def list_tasks(status: str | None = Query(default=None)):
    return [redact(x) for x in t.list_tasks(status=status)]


@router.get("/{task_id}")
def get_task(task_id: str):
    task = t.get_task(task_id)
    if task is None:
        raise HTTPException(404, "task not found")
    return redact(task)


@router.post("/{task_id}/pause")
async def pause_task(task_id: str):
    task = t.get_task(task_id)
    if task is None:
        raise HTTPException(404, "task not found")
    if task["status"] in t.TERMINAL:
        raise HTTPException(409, f"task is {task['status']}")
    t.update(task_id, status="paused")
    from ..core.agents import registry
    for aid in task.get("assigned_agents", []):
        a = registry.get(aid)
        if a:
            a._pause_requested = True
    await bus.publish("task_paused", task_id=task_id)
    return {"ok": True}


@router.post("/{task_id}/resume")
async def resume_task(task_id: str):
    task = t.get_task(task_id)
    if task is None:
        raise HTTPException(404, "task not found")
    from ..core.agents import registry
    for aid in task.get("assigned_agents", []):
        a = registry.get(aid)
        if a:
            a._pause_requested = False
    t.update(task_id, status="running" if task.get("started_at") else "queued")
    await bus.publish("task_resumed", task_id=task_id)
    return {"ok": True}


@router.post("/{task_id}/cancel")
async def cancel_task(task_id: str):
    task = t.get_task(task_id)
    if task is None:
        raise HTTPException(404, "task not found")
    if task["status"] in t.TERMINAL:
        raise HTTPException(409, f"task is already {task['status']}")
    t.update(task_id, status="cancelled")
    from ..core.agents import registry
    for aid in task.get("assigned_agents", []):
        a = registry.get(aid)
        if a:
            a._stop_requested = True
    await bus.publish("task_cancelled", task_id=task_id)
    return {"ok": True}


@router.get("/{task_id}/logs")
def task_logs(task_id: str):
    if t.get_task(task_id) is None:
        raise HTTPException(404, "task not found")
    return t.get_logs(task_id)


@router.get("/{task_id}/timeline")
def task_timeline(task_id: str):
    if t.get_task(task_id) is None:
        raise HTTPException(404, "task not found")
    return t.get_timeline(task_id)


@router.get("/{task_id}/events")
async def task_events(task_id: str):
    return sse_response(_TASK_EVENTS, filter_fn=lambda d: d.get("task_id") == task_id)


@router.websocket("/{task_id}/events/ws")
async def task_events_ws(ws: WebSocket, task_id: str):
    await ws_pump(ws, _TASK_EVENTS, filter_fn=lambda d: d.get("task_id") == task_id)
