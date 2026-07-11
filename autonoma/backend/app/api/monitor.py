"""Real-Time Monitoring API (Section 6) — powers the visual command center."""
from __future__ import annotations

from fastapi import APIRouter, WebSocket

from .. import audit
from ..core import health
from ..core import tasks as t
from ..core.agents import registry
from ..core.approvals import approval_queue, cost_ceiling
from ..core.input_lock import input_lock
from ..secrets_vault import redact
from .streams import sse_response, ws_pump

router = APIRouter(prefix="/api/v1/monitor", tags=["monitor"])


@router.get("/tasks")
def monitor_tasks():
    return [redact(x) for x in t.list_tasks()]


@router.get("/agents")
def monitor_agents():
    return {
        "agents": [a.public() for a in registry.all()],
        "input_lock_holder": input_lock.holder,
        "cost": cost_ceiling.snapshot(),
        "pending_approvals": approval_queue.snapshot(),
    }


@router.get("/health")
def monitor_health():
    # Actively re-probed on every request — never a cached flag (Section 6).
    return health.check()


@router.get("/events")
async def monitor_events():
    # Global live system events (all types).
    return sse_response(None)


@router.websocket("/events/ws")
async def monitor_events_ws(ws: WebSocket):
    await ws_pump(ws, None)


@router.get("/audit-feed")
async def monitor_audit_feed():
    # Live audit events with secrets redacted at the stream layer.
    return sse_response({"audit"})


@router.get("/audit")
def audit_history(limit: int = 200):
    return audit.list_entries(limit=limit)
