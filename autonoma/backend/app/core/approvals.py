"""Sequential approval queue and session cost ceiling (Sections 4, 9).

When multiple agents hit high-risk actions around the same time, approval
requests are presented to the user ONE AT A TIME in a single queue — never
stacked or shown in parallel — to avoid approval fatigue and reduce the chance
of approving the wrong action.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from .. import audit, events


@dataclass
class ApprovalRequest:
    request_id: str
    agent_id: str
    task_id: str
    skill_id: str | None
    skill_version: int | None
    step: int
    action: str
    risk: str
    message: str
    created_at: float = field(default_factory=time.time)
    status: str = "pending"  # pending | granted | denied
    future: asyncio.Future = field(default_factory=lambda: asyncio.get_event_loop().create_future())

    def public(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "agent_id": self.agent_id,
            "task_id": self.task_id,
            "skill_id": self.skill_id,
            "skill_version": self.skill_version,
            "step": self.step,
            "action": self.action,
            "risk": self.risk,
            "message": self.message,
            "status": self.status,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.created_at)),
        }


class ApprovalQueue:
    """Serializes approval prompts across all agents behind one gate."""

    def __init__(self) -> None:
        self._gate = asyncio.Lock()  # ensures one active prompt at a time
        self._pending: dict[str, ApprovalRequest] = {}
        self._order: list[str] = []

    def snapshot(self) -> list[dict[str, Any]]:
        return [self._pending[rid].public() for rid in self._order if rid in self._pending]

    def _current(self) -> ApprovalRequest | None:
        for rid in self._order:
            req = self._pending.get(rid)
            if req and req.status == "pending":
                return req
        return None

    async def request(self, **kwargs: Any) -> bool:
        """Enqueue a request and block until the user grants/denies it. The
        `_gate` lock guarantees only one prompt is active at a time even if
        several agents call concurrently."""
        request_id = f"appr_{uuid.uuid4().hex[:10]}"
        req = ApprovalRequest(request_id=request_id, **kwargs)
        async with self._gate:
            self._pending[request_id] = req
            self._order.append(request_id)
            await events.bus.publish(
                "approval_requested",
                request_id=request_id, agent_id=req.agent_id, task_id=req.task_id,
                action=req.action, risk=req.risk, message=req.message,
            )
            audit.record(action=req.action, status="waiting_approval", verified=None,
                         agent_id=req.agent_id, task_id=req.task_id, skill_id=req.skill_id,
                         skill_version=req.skill_version, requires_approval=True,
                         extra={"risk": req.risk})
            try:
                granted: bool = await req.future
            finally:
                self._pending.pop(request_id, None)
                if request_id in self._order:
                    self._order.remove(request_id)
        return granted

    async def resolve(self, request_id: str, granted: bool) -> bool:
        req = self._pending.get(request_id)
        if req is None or req.status != "pending":
            return False
        req.status = "granted" if granted else "denied"
        if not req.future.done():
            req.future.set_result(granted)
        await events.bus.publish(
            "approval_granted" if granted else "approval_denied",
            request_id=request_id, agent_id=req.agent_id, task_id=req.task_id, action=req.action,
        )
        audit.record(action=req.action, status="approved" if granted else "denied",
                     verified=None, agent_id=req.agent_id, task_id=req.task_id,
                     skill_id=req.skill_id, skill_version=req.skill_version,
                     requires_approval=True, approved_by_user=granted, extra={"risk": req.risk})
        return True


class CostCeiling:
    """Optional, user-configurable per-session token/cost limit (Section 4)."""

    def __init__(self, limit_usd: float | None = None) -> None:
        self.limit_usd = limit_usd
        self.spent_usd = 0.0

    def set_limit(self, limit_usd: float | None) -> None:
        self.limit_usd = limit_usd

    def would_exceed(self, add_usd: float) -> bool:
        if self.limit_usd is None:
            return False
        return (self.spent_usd + add_usd) > self.limit_usd

    def charge(self, add_usd: float) -> None:
        self.spent_usd += add_usd

    def snapshot(self) -> dict[str, Any]:
        return {"limit_usd": self.limit_usd, "spent_usd": round(self.spent_usd, 4)}


approval_queue = ApprovalQueue()
cost_ceiling = CostCeiling()
