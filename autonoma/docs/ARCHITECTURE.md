# Architecture

Autonoma is a FastAPI backend with an event-driven orchestration engine, a
pluggable automation layer, and two interchangeable frontends. It is built in
the three phases described in the spec, each independently runnable.

## Modules

### `app/core/orchestrator.py`
The heart. A background scheduler assigns queued tasks to idle worker agents and
executes each skill's `execution_plan` step by step:
1. Resolve every `skill_ref` against the **live registry** (unknown → explicit
   `404`, never a silent retry or improvised action).
2. Validate skill constraints (file scope, declared capabilities).
3. For each step: check pause/cancel → **approval gate** for high-risk steps →
   charge the **cost ceiling** → acquire the **input lock** for input actions →
   dispatch to the automation backend → verify the post-condition → write the
   audit entry with a truthful `verified`/`status` → emit live events → update
   progress.
Unverified steps increment the agent's `verification_failures`, feeding stuck
detection. A separate monitor loop watches for stalled/drifting agents and
drives bounded recovery (watchdog takeover or a user decision request).

### `app/core/agents.py`
The 1–3 agent pool. Each agent has an id, status, current task, assigned
skill/version, role (`worker`|`watchdog`), and counters. Default first launch:
**1 agent, Independent mode**.

### Coordination primitives
- `input_lock.py` — a single async lock; only one agent controls input at a
  time; emits `input_lock_acquired`/`released`.
- `approvals.py` — `ApprovalQueue` serializes prompts across agents behind one
  gate (sequential, never parallel); `CostCeiling` caps per-session spend.

### `app/core/skills.py`
Versioned, immutable skills with JSON-Schema validation, rollback, archive, and
a live action-space accessor so agents can only reference real, active skills.

### `app/automation/`
`base.py` defines the OS-agnostic interface and `ActionResult` (with the
load-bearing `verified` flag). `behavior.py` computes human-like vs machine-speed
timing/motion. `verification.py` checks declared success conditions.
`oscompat.py` validates/translates commands per target OS. `simulated.py` is the
safe default backend (virtual screen, bounded retry, zoom re-capture);
`desktop.py` is the opt-in real `pyautogui` backend.

### `app/core/inference.py` + `hardware.py`
Inference-mode config with the provider endpoint constraint, and a
requirement estimator that scales with mode + agent count + model footprint.

### `app/core/health.py`
Active liveness: re-probes the orchestrator loop, agents, and (for local/hybrid)
the configured local inference endpoint on **every** call — no cached flags.

### `app/events.py` + `app/api/streams.py`
An in-process async event bus with a recent-history ring buffer, exposed as SSE
and WebSocket streams. Every payload is redacted before leaving the process.

### Persistence
`database.py` is a thin SQLite layer (JSON blobs + indexable columns).
`audit.py` is append-only and redacted. `secrets_vault.py` encrypts secrets and
provides the recursive redactor used across the system.

## Data flow for one step
```
scheduler → agent picks task → resolve+validate skills
  → per step:
      approval? ─yes→ ApprovalQueue (blocks until user) ─deny→ fail
      cost ok?  ─no→ fail
      input action? ─yes→ InputLock.hold(agent) → backend.action(expect, behavior)
      verify(expect, observed) → ActionResult(verified?)
      audit.record(status=verified?success:unverified) + emit events
  → progress++, repeat → task_completed
```

## Design choices
- **Simulated-first** so the entire system runs and is tested headlessly, with
  real desktop automation as a drop-in backend sharing identical safety
  semantics.
- **Truthful verification** everywhere: the `verified` flag is never
  rubber-stamped by absence of an exception.
- **Single control loop**: the provider endpoint constraint and shared input
  lock guarantee exactly one actor drives the desktop.
