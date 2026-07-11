"""Agent registry (Section 4).

Holds the pool of 1-3 agents, their live status, roles (worker | watchdog),
and the shared input-lock view. Default first-launch configuration: 1 agent,
Independent mode (set in orchestrator startup)."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Agent:
    agent_id: str
    role: str = "worker"  # worker | watchdog
    status: str = "idle"  # idle | running | paused | error | stopped
    current_task: str | None = None
    assigned_skill: str | None = None
    assigned_skill_version: int | None = None
    error: str | None = None
    logs: list[str] = field(default_factory=list)
    last_progress_at: float = field(default_factory=time.time)
    verification_failures: int = 0
    retry_count: int = 0
    _pause_requested: bool = False
    _stop_requested: bool = False

    def log(self, message: str) -> None:
        self.logs.append(f"{time.strftime('%H:%M:%S')} {message}")
        self.logs = self.logs[-200:]

    def public(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "role": self.role,
            "status": self.status,
            "current_task": self.current_task,
            "assigned_skill": self.assigned_skill,
            "assigned_skill_version": self.assigned_skill_version,
            "error": self.error,
            "logs": self.logs[-25:],
            "verification_failures": self.verification_failures,
            "retry_count": self.retry_count,
        }


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, Agent] = {}
        self._active_count: int = 0

    def configure(self, count: int) -> list[Agent]:
        count = max(1, min(3, int(count)))
        # Create up to `count` agents, preserving existing ones.
        existing = list(self._agents.values())
        while len(self._agents) < count:
            idx = len(self._agents) + 1
            aid = f"agent_{idx:03d}"
            self._agents[aid] = Agent(agent_id=aid)
        # Mark extras beyond `count` as stopped (do not delete history).
        for i, agent in enumerate(sorted(self._agents.values(), key=lambda a: a.agent_id)):
            if i >= count and agent.status != "stopped":
                agent.status = "stopped"
            elif i < count and agent.status == "stopped":
                agent.status = "idle"
        self._active_count = count
        return self.active()

    def active(self) -> list[Agent]:
        return [a for a in sorted(self._agents.values(), key=lambda x: x.agent_id)
                if a.status != "stopped"]

    def all(self) -> list[Agent]:
        return sorted(self._agents.values(), key=lambda x: x.agent_id)

    def get(self, agent_id: str) -> Agent | None:
        return self._agents.get(agent_id)

    def active_count(self) -> int:
        return len(self.active())

    def workers(self) -> list[Agent]:
        return [a for a in self.active() if a.role == "worker"]

    def watchdog(self) -> Agent | None:
        for a in self.active():
            if a.role == "watchdog":
                return a
        return None


registry = AgentRegistry()
