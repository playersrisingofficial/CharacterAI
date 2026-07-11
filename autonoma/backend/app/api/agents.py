"""Agent Control API (Section 4)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, WebSocket

from ..core.agents import registry
from ..core.input_lock import input_lock
from ..events import bus
from .streams import sse_response, ws_pump

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])

_AGENT_EVENTS = {
    "agent_started", "agent_idle", "agent_error", "agent_stuck_detected",
    "agent_recovery_attempted", "agent_recovery_resolved",
    "watchdog_assigned", "watchdog_unassigned",
    "input_lock_acquired", "input_lock_released",
    "task_step_started", "task_step_completed",
}


@router.get("")
@router.get("/")
def list_agents():
    return [a.public() for a in registry.all()]


@router.post("/config")
def set_config(payload: dict[str, Any] = Body(...)):
    count = payload.get("count", payload.get("active_agent_count", 1))
    agents = registry.configure(int(count))
    return {"active_agent_count": len(agents), "agents": [a.public() for a in agents]}


@router.get("/input-lock")
def get_input_lock():
    return {"holder": input_lock.holder}


# Static-ish routes must precede /{agent_id} dynamic capture.
@router.get("/{agent_id}")
def get_agent(agent_id: str):
    a = registry.get(agent_id)
    if a is None:
        raise HTTPException(404, "agent not found")
    return a.public()


@router.post("/{agent_id}/pause")
async def pause_agent(agent_id: str):
    a = registry.get(agent_id)
    if a is None:
        raise HTTPException(404, "agent not found")
    a._pause_requested = True
    return {"ok": True, "agent": a.public()}


@router.post("/{agent_id}/resume")
async def resume_agent(agent_id: str):
    a = registry.get(agent_id)
    if a is None:
        raise HTTPException(404, "agent not found")
    a._pause_requested = False
    return {"ok": True, "agent": a.public()}


@router.post("/{agent_id}/stop")
async def stop_agent(agent_id: str):
    a = registry.get(agent_id)
    if a is None:
        raise HTTPException(404, "agent not found")
    a._stop_requested = True
    return {"ok": True, "agent": a.public()}


@router.post("/{agent_id}/watchdog")
async def set_watchdog(agent_id: str, payload: dict[str, Any] = Body(default={})):
    a = registry.get(agent_id)
    if a is None:
        raise HTTPException(404, "agent not found")
    assign = payload.get("assign", True)
    if assign and registry.active_count() < 2:
        raise HTTPException(409, "watchdog role only applies when >1 agent is active")
    a.role = "watchdog" if assign else "worker"
    await bus.publish("watchdog_assigned" if assign else "watchdog_unassigned", agent_id=agent_id)
    return {"ok": True, "agent": a.public()}


@router.get("/{agent_id}/events")
async def agent_events(agent_id: str):
    return sse_response(_AGENT_EVENTS, filter_fn=lambda d: d.get("agent_id") == agent_id)


@router.websocket("/{agent_id}/events/ws")
async def agent_events_ws(ws: WebSocket, agent_id: str):
    await ws_pump(ws, _AGENT_EVENTS, filter_fn=lambda d: d.get("agent_id") == agent_id)
