"""Agent orchestration engine (Sections 3, 4, 7, 9).

Responsibilities:
  * Assign queued tasks to idle worker agents.
  * Execute a skill's execution_plan step-by-step through the automation
    backend, honoring the input lock, behavior modes, approval gates, and
    post-action verification.
  * Detect stuck/drifting agents and drive bounded recovery.
  * Emit the full live event stream and append-only audit trail.

The engine is fully runnable against the default SimulatedBackend, so it works
in CI/Docker with no physical desktop.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

from .. import audit, events
from ..automation import get_backend
from ..config import get_settings
from ..secrets_vault import resolve_secret, redact
from . import skills as skills_mod
from . import tasks as tasks_mod
from . import inference
from .agents import Agent, registry
from .approvals import approval_queue, cost_ceiling
from .input_lock import input_lock
from .safety import step_requires_approval, validate_skill_constraints


# Which action verbs actually drive shared desktop input (need the lock).
_INPUT_ACTIONS = {"focus_window", "click", "type", "type_secret", "submit_login",
                  "click_login", "submit_payment", "drag", "scroll"}


class Orchestrator:
    def __init__(self) -> None:
        self._running = False
        self._bg: list[asyncio.Task] = []
        self._agent_tasks: dict[str, asyncio.Task] = {}
        self.started_at = time.time()
        self.backend = None

    # --- lifecycle -------------------------------------------------------
    async def start(self) -> None:
        if self._running:
            return
        settings = get_settings()
        self.backend = get_backend()
        # Default first-launch configuration: 1 agent, Independent mode.
        if registry.active_count() == 0:
            registry.configure(1)
        cost_ceiling.set_limit(settings.session_cost_ceiling)
        self._running = True
        self._bg = [
            asyncio.create_task(self._scheduler_loop(), name="scheduler"),
            asyncio.create_task(self._stuck_monitor_loop(), name="stuck-monitor"),
        ]

    async def stop(self) -> None:
        self._running = False
        for t in self._bg + list(self._agent_tasks.values()):
            t.cancel()
        await asyncio.gather(*self._bg, *self._agent_tasks.values(), return_exceptions=True)
        self._bg.clear()
        self._agent_tasks.clear()

    def uptime(self) -> float:
        return time.time() - self.started_at

    # --- scheduling ------------------------------------------------------
    async def _scheduler_loop(self) -> None:
        while self._running:
            try:
                await self._assign_once()
            except Exception as exc:  # pragma: no cover - defensive
                await events.bus.publish("agent_error", message=f"scheduler error: {exc}")
            await asyncio.sleep(0.5)

    async def _assign_once(self) -> None:
        queued = tasks_mod.list_tasks(status="queued")
        if not queued:
            return
        for agent in registry.workers():
            if agent.status not in {"idle"}:
                continue
            if not queued:
                break
            task = queued.pop(0)
            self._agent_tasks[agent.agent_id] = asyncio.create_task(
                self._run_task(agent, task["task_id"])
            )

    # --- execution -------------------------------------------------------
    async def _run_task(self, agent: Agent, task_id: str) -> None:
        task = tasks_mod.get_task(task_id)
        if task is None:
            return
        agent.status = "running"
        agent.current_task = task_id
        agent.error = None
        agent.retry_count = 0
        agent.verification_failures = 0
        agent.last_progress_at = time.time()

        assigned = list(task.get("assigned_agents", []))
        if agent.agent_id not in assigned:
            assigned.append(agent.agent_id)
        tasks_mod.update(task_id, status="running", started_at=tasks_mod._now(),
                         assigned_agents=assigned)
        await events.bus.publish("task_started", task_id=task_id, agent_id=agent.agent_id)
        await events.bus.publish("agent_started", agent_id=agent.agent_id, task_id=task_id)
        tasks_mod.add_log(task_id, "info", f"{agent.agent_id} started task")

        try:
            ok = await self._execute_plan(agent, task_id)
            final = tasks_mod.get_task(task_id)
            if final and final["status"] in tasks_mod.TERMINAL:
                pass  # already resolved (cancelled/failed)
            elif ok:
                tasks_mod.update(task_id, status="completed", progress=1.0, next_action=None)
                await events.bus.publish("task_completed", task_id=task_id, agent_id=agent.agent_id)
                tasks_mod.add_log(task_id, "info", "task completed")
            else:
                tasks_mod.update(task_id, status="failed")
                await events.bus.publish("task_failed", task_id=task_id, agent_id=agent.agent_id)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            agent.error = str(exc)
            tasks_mod.update(task_id, status="failed", error=str(exc))
            await events.bus.publish("task_failed", task_id=task_id, agent_id=agent.agent_id,
                                     message=str(exc))
            await events.bus.publish("agent_error", agent_id=agent.agent_id, message=str(exc))
            audit.record(action="task", status="failed", verified=False, agent_id=agent.agent_id,
                         task_id=task_id, extra={"error": str(exc)})
        finally:
            agent.status = "idle"
            agent.current_task = None
            agent.assigned_skill = None
            agent.assigned_skill_version = None
            await events.bus.publish("agent_idle", agent_id=agent.agent_id)
            self._agent_tasks.pop(agent.agent_id, None)

    async def _resolve_skills(self, task: dict[str, Any]) -> list[dict[str, Any]]:
        """Resolve every skill_ref against the LIVE registry. Unresolvable
        references fail immediately and explicitly (Section 7)."""
        resolved = []
        for ref in task.get("skill_refs", []):
            skill_id = ref.get("skill_id")
            version = ref.get("version")  # explicit version preferred
            if version is None and not ref.get("use_latest_active"):
                # "Latest active version" only when explicitly configured.
                skills_mod.validate_skill_action_ref(skill_id)
                version = skills_mod.get_latest(skill_id)["version"]
            skill = skills_mod.resolve(skill_id, version)
            if skill is None:
                raise skills_mod.SkillError(f"skill not found: {skill_id} v{version}", status=404)
            resolved.append(skill)
        return resolved

    async def _execute_plan(self, agent: Agent, task_id: str) -> bool:
        task = tasks_mod.get_task(task_id)
        settings = get_settings()
        try:
            skills = await self._resolve_skills(task)
        except skills_mod.SkillError as exc:
            # Explicit, non-retried failure.
            await events.bus.publish("agent_error", agent_id=agent.agent_id, task_id=task_id,
                                     message=str(exc), reason="skill_not_found")
            audit.record(action="resolve_skill", status="failed", verified=False,
                         agent_id=agent.agent_id, task_id=task_id, extra={"error": str(exc)})
            tasks_mod.update(task_id, status="failed", error=str(exc))
            return False

        # Constraint validation (file scope etc.) before doing anything.
        for skill in skills:
            problems = validate_skill_constraints(skill, str(settings.work_dir) if settings.work_dir else None)
            if problems:
                msg = "; ".join(problems)
                tasks_mod.update(task_id, status="failed", error=msg)
                audit.record(action="constraint_check", status="failed", verified=False,
                             agent_id=agent.agent_id, task_id=task_id, skill_id=skill["skill_id"],
                             extra={"violations": problems})
                return False

        # Count total steps across all skills for progress.
        all_steps = [(s, step) for s in skills for step in s.get("execution_plan", [])]
        total = max(len(all_steps), 1)
        done = 0

        for skill, step in all_steps:
            # Respect cancel/pause between steps.
            if agent._stop_requested or tasks_mod.get_task(task_id)["status"] == "cancelled":
                tasks_mod.update(task_id, status="cancelled")
                await events.bus.publish("task_cancelled", task_id=task_id, agent_id=agent.agent_id)
                return False
            await self._await_if_paused(agent, task_id)

            agent.assigned_skill = skill["skill_id"]
            agent.assigned_skill_version = skill["version"]
            ok = await self._execute_step(agent, task_id, skill, step)
            if not ok:
                return False
            done += 1
            progress = round(done / total, 3)
            next_action = all_steps[done][1].get("action") if done < len(all_steps) else None
            tasks_mod.update(task_id, progress=progress, current_step=step.get("step"),
                             current_skill=skill["skill_id"],
                             current_skill_version=skill["version"],
                             last_action=step.get("action"), next_action=next_action)
            agent.last_progress_at = time.time()
            agent.retry_count = 0
        return True

    async def _execute_step(self, agent: Agent, task_id: str, skill: dict, step: dict) -> bool:
        action = step.get("action")
        step_no = step.get("step")
        behavior = self._behavior_for(skill, step, task_id)
        task_input = (tasks_mod.get_task(task_id) or {}).get("input", {})

        # Approval gate BEFORE acting on any high-risk step.
        needs, risk = step_requires_approval(step, skill)
        if needs:
            tasks_mod.update(task_id, status="waiting_approval")
            await events.bus.publish("task_waiting_for_approval", task_id=task_id,
                                     agent_id=agent.agent_id, action=action, risk=risk, step=step_no)
            granted = await approval_queue.request(
                agent_id=agent.agent_id, task_id=task_id, skill_id=skill["skill_id"],
                skill_version=skill["version"], step=step_no or 0, action=action,
                risk=risk or action, message=f"Approve high-risk action '{action}' ({risk})?",
            )
            if not granted:
                tasks_mod.update(task_id, status="failed", error=f"user denied '{action}'")
                await events.bus.publish("task_failed", task_id=task_id, agent_id=agent.agent_id,
                                         message=f"denied: {action}")
                return False
            tasks_mod.update(task_id, status="running")

        await events.bus.publish("task_step_started", task_id=task_id, agent_id=agent.agent_id,
                                 skill_id=skill["skill_id"], skill_version=skill["version"],
                                 step=step_no, action=action, status="running",
                                 message=f"{action} (mode={behavior.get('mode')})")
        tasks_mod.add_timeline(task_id, step=step_no, action=action, status="running",
                               message=f"executing {action}")

        # Simulate small per-step inference cost under API/hybrid mode + ceiling.
        est_cost = self._estimate_step_cost(step)
        if cost_ceiling.would_exceed(est_cost):
            msg = f"session cost ceiling would be exceeded (limit ${cost_ceiling.limit_usd})"
            tasks_mod.update(task_id, status="failed", error=msg)
            await events.bus.publish("task_failed", task_id=task_id, agent_id=agent.agent_id, message=msg)
            return False
        cost_ceiling.charge(est_cost)

        result = await self._dispatch_action(agent, skill, step, behavior, task_input)

        # Audit with truthful verified/status coupling (Section 9).
        audit.record(action=action, status=result.audit_status, verified=result.verified,
                     agent_id=agent.agent_id, task_id=task_id, skill_id=skill["skill_id"],
                     skill_version=skill["version"], target=step.get("target") or step.get("field"),
                     requires_approval=needs, approved_by_user=True if needs else None,
                     extra={"detail": result.detail, "retries": result.retries})

        tasks_mod.add_timeline(task_id, step=step_no, action=action, status=result.audit_status,
                               message=result.detail, data=redact(result.observed))
        await events.bus.publish("task_step_completed", task_id=task_id, agent_id=agent.agent_id,
                                 skill_id=skill["skill_id"], skill_version=skill["version"],
                                 step=step_no, action=action, status=result.audit_status,
                                 verified=result.verified, message=result.detail)

        if not result.ok:
            agent.error = result.detail
            return False
        if not result.verified:
            # Action dispatched but outcome not confirmed -> feeds stuck detection.
            agent.verification_failures += 1
            agent.log(f"unverified step {step_no} ({action}): {result.detail}")
            # A single unverified step is tolerated; repeated ones trip the monitor.
        return True

    async def _dispatch_action(self, agent: Agent, skill: dict, step: dict, behavior: dict, task_input: dict):
        from .base_result import make_ok, make_failure
        backend = self.backend
        action = step.get("action")
        expect = self._interpolate_struct(step.get("expect"), task_input)

        async def with_lock(fn):
            async with input_lock.hold(agent.agent_id):
                return await asyncio.get_event_loop().run_in_executor(None, fn)

        if action == "focus_window":
            return await with_lock(lambda: backend.focus_window(step.get("target", ""), expect, behavior))
        if action in {"click", "click_login", "submit_login", "submit_payment"}:
            return await with_lock(lambda: backend.click(step.get("target", ""), expect, behavior))
        if action == "type":
            value = self._interpolate(step.get("value", ""), task_input)
            return await with_lock(lambda: backend.type_text(step.get("field", ""), value, expect, behavior))
        if action == "type_secret":
            ref = self._interpolate(step.get("secret_ref", ""), task_input)
            try:
                secret_value = resolve_secret(ref)
            except KeyError as exc:
                return make_failure(action, str(exc))
            return await with_lock(lambda: backend.type_secret(step.get("field", ""), secret_value, expect, behavior))
        if action == "run_command":
            cmd = self._interpolate(step.get("command", ""), task_input)
            return await asyncio.get_event_loop().run_in_executor(None, lambda: backend.run_command(cmd, expect))
        if action == "screenshot":
            desc = backend.screenshot(step.get("region"), redact=True)
            return make_ok(action, "captured (redacted)", desc)
        # Non-input reasoning/wait step: no lock needed.
        await asyncio.sleep(0.02)
        return make_ok(action, f"executed {action}")

    # --- helpers ---------------------------------------------------------
    def _behavior_for(self, skill: dict, step: dict, task_id: str) -> dict:
        profile = dict(skill.get("behavior_profile", {}))
        default_mode = profile.get("default_mode", "human_like")
        # Per-step override, else task-level mode, else skill default.
        task = tasks_mod.get_task(task_id) or {}
        mode = step.get("mode") or task.get("input_behavior_mode") or default_mode
        return {"mode": mode,
                "human_like": profile.get("human_like", {}),
                "machine_speed": profile.get("machine_speed", {})}

    def _interpolate(self, template: str, task_input: dict) -> str:
        """Resolve {{input.x}} references against the running task input."""
        if not isinstance(template, str) or "{{" not in template:
            return template
        out = template
        for key, val in (task_input or {}).items():
            out = out.replace(f"{{{{input.{key}}}}}", str(val))
        return out

    def _interpolate_struct(self, obj, task_input: dict):
        """Interpolate {{input.x}} throughout a nested dict/list (e.g. expect)."""
        if isinstance(obj, str):
            return self._interpolate(obj, task_input)
        if isinstance(obj, dict):
            return {k: self._interpolate_struct(v, task_input) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._interpolate_struct(v, task_input) for v in obj]
        return obj

    def _estimate_step_cost(self, step: dict) -> float:
        target = inference.route_step("complex_reasoning" if step.get("action") in
                                      {"reason", "plan"} else "simple_steps")
        return 0.002 if target == "api_based" else 0.0

    async def _await_if_paused(self, agent: Agent, task_id: str) -> None:
        was_paused = False
        while agent._pause_requested or tasks_mod.get_task(task_id)["status"] == "paused":
            if not was_paused:
                agent.status = "paused"
                await events.bus.publish("task_paused", task_id=task_id, agent_id=agent.agent_id)
                was_paused = True
            await asyncio.sleep(0.2)
            if agent._stop_requested:
                return
        if was_paused:
            agent.status = "running"
            tasks_mod.update(task_id, status="running")
            await events.bus.publish("task_resumed", task_id=task_id, agent_id=agent.agent_id)

    # --- stuck detection & recovery (Section 4) --------------------------
    async def _stuck_monitor_loop(self) -> None:
        settings = get_settings()
        while self._running:
            await asyncio.sleep(2.0)
            now = time.time()
            watchdog = registry.watchdog()
            for agent in registry.workers():
                if agent.status != "running" or agent.current_task is None:
                    continue
                stalled = (now - agent.last_progress_at) > settings.stuck_no_progress_seconds
                too_many_retries = agent.retry_count > settings.stuck_retry_limit
                drifting = agent.verification_failures >= settings.stuck_verification_failures
                if stalled or too_many_retries or drifting:
                    reason = ("no_progress" if stalled else
                              "retry_limit" if too_many_retries else "verification_drift")
                    await self._handle_stuck(agent, reason, watchdog)

    async def _handle_stuck(self, agent: Agent, reason: str, watchdog: Agent | None) -> None:
        task_id = agent.current_task
        snapshot = self.backend.screenshot(redact=True) if self.backend else {}
        await events.bus.publish("agent_stuck_detected", agent_id=agent.agent_id,
                                 task_id=task_id, reason=reason)
        audit.record(action="stuck_detected", status="unverified", verified=None,
                     agent_id=agent.agent_id, task_id=task_id, extra={"reason": reason,
                     "snapshot": snapshot})
        # Bounded recovery attempt.
        await events.bus.publish("agent_recovery_attempted", agent_id=agent.agent_id, task_id=task_id)
        agent.verification_failures = 0
        agent.last_progress_at = time.time()

        if watchdog is not None:
            watchdog.log(f"intervening on stuck agent {agent.agent_id} ({reason})")
            await events.bus.publish("agent_recovery_resolved", agent_id=agent.agent_id,
                                     task_id=task_id, resolved_by=watchdog.agent_id)
            audit.record(action="stuck_recovery", status="success", verified=True,
                         agent_id=agent.agent_id, task_id=task_id,
                         extra={"resolved_by": watchdog.agent_id, "reason": reason})
        else:
            # No watchdog: surface to the user as a decision/approval request.
            granted = await approval_queue.request(
                agent_id=agent.agent_id, task_id=task_id or "", skill_id=agent.assigned_skill,
                skill_version=agent.assigned_skill_version, step=0, action="stuck_recovery",
                risk="agent_stuck", message=f"Agent {agent.agent_id} appears stuck ({reason}). "
                                            f"Approve continue/retry, or deny to fail the task.",
            )
            if granted:
                await events.bus.publish("agent_recovery_resolved", agent_id=agent.agent_id,
                                         task_id=task_id, resolved_by="user")
            else:
                agent._stop_requested = True
                if task_id:
                    tasks_mod.update(task_id, status="failed", error=f"stuck: {reason} (user declined)")
                    await events.bus.publish("task_failed", task_id=task_id, agent_id=agent.agent_id)


orchestrator = Orchestrator()
