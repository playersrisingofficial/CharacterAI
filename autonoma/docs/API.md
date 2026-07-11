# API Reference

All endpoints are under `/api/v1`. Interactive OpenAPI docs are served at `/docs`.
Responses are JSON. Secrets are redacted from every response, log, and event stream.

## Tasks — `/api/v1/tasks`
| Method | Path | Purpose |
|---|---|---|
| POST | `/tasks` | Create a task |
| GET | `/tasks` | List tasks (`?status=`) |
| GET | `/tasks/{id}` | Task status/details |
| POST | `/tasks/{id}/pause` | Pause a running task |
| POST | `/tasks/{id}/resume` | Resume a paused task |
| POST | `/tasks/{id}/cancel` | Cancel safely |
| GET | `/tasks/{id}/logs` | Task logs |
| GET | `/tasks/{id}/timeline` | Chronological action timeline |
| GET | `/tasks/{id}/events` | Live task events (SSE) |
| WS | `/tasks/{id}/events/ws` | Live task events (WebSocket) |

```bash
curl -X POST /api/v1/tasks -H 'Content-Type: application/json' -d '{
  "title": "Log into desktop app",
  "coordination_mode": "independent",
  "skill_refs": [{"skill_id": "skill_...", "version": 1}],
  "input": {"username": "alice", "password_secret_ref": "secret_app_pw"},
  "input_behavior_mode": "human_like"
}'
```
A task referencing an unknown skill is rejected immediately with `404`.

## Agents — `/api/v1/agents`
| Method | Path | Purpose |
|---|---|---|
| GET | `/agents` | List agents |
| POST | `/agents/config` | Set active count 1–3 (`{"count": 2}`) |
| GET | `/agents/{id}` | Agent status |
| POST | `/agents/{id}/pause` · `/resume` · `/stop` | Control an agent |
| GET | `/agents/{id}/events` | Live agent activity (SSE) |
| GET | `/agents/input-lock` | Who holds the shared desktop input lock |
| POST | `/agents/{id}/watchdog` | Assign/unassign watchdog role (`{"assign": true}`) |

## Skills — `/api/v1/skills`
| Method | Path | Purpose |
|---|---|---|
| POST | `/skills` | Create skill → `201` |
| GET | `/skills` | List (`?status=active`) |
| GET | `/skills/{id}` | Latest version |
| GET | `/skills/{id}/versions/{v}` | Specific version |
| PUT | `/skills/{id}` | Update → new immutable version |
| PATCH | `/skills/{id}/status` | `{"status":"active"|"archived"}` |
| POST | `/skills/{id}/rollback` | `{"target_version": 2}` → new version |
| DELETE | `/skills/{id}` | Soft-delete/archive → `204` |
| POST | `/skills/demonstrations/start` | Begin a demonstration recording → `202` |
| POST | `/skills/demonstrations/{sid}/stop` | End recording |
| POST | `/skills/demonstrations/{sid}/trace` | Append a recorded input trace |
| GET | `/skills/demonstrations?skill_name=` | List recordings (expect up to 3) |
| POST | `/skills/demonstrations/generate` | Generate a skill draft from recordings → `201` |

Skills are JSON-Schema validated; invalid payloads return `400`. Raw secrets
embedded in a skill are rejected. Every update creates a new integer version;
older versions remain retrievable, and running tasks keep the version they
started with.

## Inference Mode — `/api/v1/inference-mode`
| Method | Path | Purpose |
|---|---|---|
| GET | `/inference-mode/options?agents=n` | Modes + hardware metadata + detected system |
| GET | `/inference-mode/current` | Active mode + config |
| POST | `/inference-mode` | Set mode + routing config |
| GET | `/inference-mode/requirements?mode=&agents=` | Computed requirement estimate |

`POST` with an `api_config.endpoint_type` of `agentic`, `tool_use`, or
`computer_use` is rejected with `400` (see [SAFETY.md](SAFETY.md)).

## Monitor — `/api/v1/monitor`
| Method | Path | Purpose |
|---|---|---|
| GET | `/monitor/tasks` | Current task states |
| GET | `/monitor/agents` | Agent activity, lock holder, cost, pending approvals |
| GET | `/monitor/events` | Global live events (SSE) |
| WS | `/monitor/events/ws` | Global live events (WebSocket) |
| GET | `/monitor/audit-feed` | Live audit events (SSE), redacted |
| GET | `/monitor/audit` | Recent audit history |
| GET | `/monitor/health` | **Actively re-probed** liveness for backend, agents, local inference |

## Safety, secrets, session — `/api/v1`
| Method | Path | Purpose |
|---|---|---|
| GET | `/approvals` | Pending approvals (sequential, one active at a time) |
| GET | `/approvals/high-risk-actions` | The high-risk action catalog |
| POST | `/approvals/{rid}/grant` · `/deny` | Resolve an approval |
| GET | `/secrets` | List secret **references** (never values) |
| POST | `/secrets` | Store a secret → returns `{"secret_ref": "..."}` |
| GET | `/session/cost` | Current session spend/limit |
| POST | `/session/cost-ceiling` | `{"limit_usd": 5.0}` or `{"limit_usd": null}` |

## Event types
`task_created, task_queued, task_started, task_step_started, task_step_completed,
task_waiting_for_approval, task_paused, task_resumed, task_cancelled, task_failed,
task_completed, agent_started, agent_idle, agent_error, approval_requested,
approval_granted, approval_denied, inference_mode_changed, input_lock_acquired,
input_lock_released, watchdog_assigned, watchdog_unassigned, agent_stuck_detected,
agent_recovery_attempted, agent_recovery_resolved` (+ `audit`).
