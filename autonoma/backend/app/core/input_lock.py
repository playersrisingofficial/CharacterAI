"""Shared desktop input lock (Section 4, Multi-Agent Coordination Guardrails).

There is only one physical cursor/keyboard, so only one agent may hold active
control of desktop input at any instant. Independent-mode agents on separate
tasks still queue for input turns rather than acting simultaneously. Acquire
and release emit `input_lock_acquired` / `input_lock_released` events.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from .. import events


class InputLock:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._holder: str | None = None

    @property
    def holder(self) -> str | None:
        return self._holder

    @asynccontextmanager
    async def hold(self, agent_id: str):
        await self._lock.acquire()
        self._holder = agent_id
        await events.bus.publish("input_lock_acquired", agent_id=agent_id)
        try:
            yield
        finally:
            self._holder = None
            self._lock.release()
            await events.bus.publish("input_lock_released", agent_id=agent_id)


# Single shared instance.
input_lock = InputLock()
