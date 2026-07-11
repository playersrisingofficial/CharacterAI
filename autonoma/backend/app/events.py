"""In-process async event bus used to power live monitoring streams.

Producers publish structured events; consumers (SSE/WebSocket handlers)
subscribe and receive an async queue. A bounded ring buffer keeps recent
events so a newly-connected client can be primed with current state.
"""
from __future__ import annotations

import asyncio
import itertools
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, AsyncIterator


# Canonical event types emitted across the system (Section 6 of the spec).
EVENT_TYPES = {
    "task_created",
    "task_queued",
    "task_started",
    "task_step_started",
    "task_step_completed",
    "task_waiting_for_approval",
    "task_paused",
    "task_resumed",
    "task_cancelled",
    "task_failed",
    "task_completed",
    "agent_started",
    "agent_idle",
    "agent_error",
    "approval_requested",
    "approval_granted",
    "approval_denied",
    "inference_mode_changed",
    "input_lock_acquired",
    "input_lock_released",
    "watchdog_assigned",
    "watchdog_unassigned",
    "agent_stuck_detected",
    "agent_recovery_attempted",
    "agent_recovery_resolved",
}

_counter = itertools.count(1)


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@dataclass
class Event:
    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: f"evt_{next(_counter):06d}")
    timestamp: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        d = {"event_id": self.event_id, "timestamp": self.timestamp, "event_type": self.event_type}
        d.update(self.payload)
        return d


class EventBus:
    def __init__(self, history: int = 500) -> None:
        self._subscribers: set[asyncio.Queue[Event]] = set()
        self._history: deque[Event] = deque(maxlen=history)
        self._lock = asyncio.Lock()

    async def publish(self, event_type: str, **payload: Any) -> Event:
        if event_type not in EVENT_TYPES:
            # Non-fatal: still deliver, but tag it so consumers can notice.
            payload = {**payload, "_unregistered_type": True}
        ev = Event(event_type=event_type, payload=payload)
        self._history.append(ev)
        # Copy under no await; queues are unbounded put_nowait.
        for q in list(self._subscribers):
            try:
                q.put_nowait(ev)
            except asyncio.QueueFull:  # pragma: no cover - unbounded queues
                pass
        return ev

    def recent(self, event_types: set[str] | None = None, limit: int = 100) -> list[Event]:
        items = [e for e in self._history if not event_types or e.event_type in event_types]
        return items[-limit:]

    async def subscribe(self) -> asyncio.Queue[Event]:
        q: asyncio.Queue[Event] = asyncio.Queue()
        async with self._lock:
            self._subscribers.add(q)
        return q

    async def unsubscribe(self, q: asyncio.Queue[Event]) -> None:
        async with self._lock:
            self._subscribers.discard(q)

    async def stream(
        self, event_types: set[str] | None = None, prime: bool = True
    ) -> AsyncIterator[Event]:
        q = await self.subscribe()
        try:
            if prime:
                for ev in self.recent(event_types):
                    yield ev
            while True:
                ev = await q.get()
                if event_types is None or ev.event_type in event_types:
                    yield ev
        finally:
            await self.unsubscribe(q)


# A single shared bus instance for the application.
bus = EventBus()
