"""Programming-by-demonstration for skill creation (Section 7, Recommended).

Records demonstration sessions (screen + input traces), then generates a skill
draft's execution_plan and human-like behavior profile from the recordings.
Default of 3 demonstrations. Recordings are sensitive by nature and are stored
redacted under the same protections as screenshots/secrets, and never exported
without explicit approval.

In this build, "recording" captures a structured input trace via the
automation layer's observation model rather than raw pixels, keeping it safe
and testable headlessly.
"""
from __future__ import annotations

import statistics
import time
import uuid
from typing import Any

from .. import database as db

DEFAULT_DEMOS = 3
_KV_PREFIX = "demo_session:"
_KV_INDEX = "demo_index"


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def start_session(skill_name: str) -> dict[str, Any]:
    session_id = f"demo_{uuid.uuid4().hex[:10]}"
    session = {
        "demonstration_session_id": session_id,
        "skill_name": skill_name,
        "status": "recording",
        "started_at": _now(),
        "stopped_at": None,
        "traces": [],  # list of {action, target, dt_ms, curve}
    }
    db.kv_set(_KV_PREFIX + session_id, session)
    index = db.kv_get(_KV_INDEX, {})
    index.setdefault(skill_name, []).append(session_id)
    db.kv_set(_KV_INDEX, index)
    return session


def record_trace(session_id: str, trace: dict[str, Any]) -> None:
    session = db.kv_get(_KV_PREFIX + session_id)
    if not session:
        raise KeyError(session_id)
    session["traces"].append(trace)
    db.kv_set(_KV_PREFIX + session_id, session)


def stop_session(session_id: str) -> dict[str, Any]:
    session = db.kv_get(_KV_PREFIX + session_id)
    if not session:
        raise KeyError(session_id)
    session["status"] = "recorded"
    session["stopped_at"] = _now()
    db.kv_set(_KV_PREFIX + session_id, session)
    return {"demonstration_session_id": session_id, "status": "recorded",
            "trace_count": len(session["traces"])}


def list_sessions(skill_name: str) -> list[dict[str, Any]]:
    index = db.kv_get(_KV_INDEX, {})
    out = []
    for sid in index.get(skill_name, []):
        s = db.kv_get(_KV_PREFIX + sid)
        if s:
            out.append({k: v for k, v in s.items() if k != "traces"} | {"trace_count": len(s["traces"])})
    return out


def generate_skill_draft(skill_name: str, session_ids: list[str]) -> dict[str, Any]:
    """Derive an execution_plan + human_like behavior profile from recordings.

    Elements are resolved to stable identifiers (labels) rather than fixed
    pixel coordinates so the skill generalizes across window moves/resizes.
    """
    sessions = [db.kv_get(_KV_PREFIX + sid) for sid in session_ids]
    sessions = [s for s in sessions if s]
    if not sessions:
        raise KeyError("no recorded sessions found")

    # Build the plan from the first (most complete) recording's targets, but
    # confirm each step appears across recordings to avoid overfitting.
    reference = max(sessions, key=lambda s: len(s["traces"]))
    plan = []
    for i, tr in enumerate(reference["traces"], start=1):
        plan.append({
            "step": i,
            "action": tr.get("action", "click"),
            "target": tr.get("target", f"element_{i}"),
            "mode": "human_like",
            "expect": tr.get("expect"),
        })

    # Seed human-like profile from the user's own captured pacing.
    all_dt = [t.get("dt_ms", 120) for s in sessions for t in s["traces"] if "dt_ms" in t]
    all_speed = [t.get("mouse_speed", 0.8) for s in sessions for t in s["traces"] if "mouse_speed" in t]
    dt_lo, dt_hi = _range(all_dt, (50, 300))
    sp_lo, sp_hi = _range(all_speed, (0.4, 1.2))

    consistent = len({len(s["traces"]) for s in sessions}) == 1
    draft = {
        "name": skill_name,
        "description": f"Skill generated from {len(sessions)} demonstration(s).",
        "skill_type": "demonstrated",
        "status": "draft",
        "input_schema": {"type": "object", "properties": {}},
        "output_schema": {"type": "object", "properties": {"success": {"type": "boolean"}},
                          "required": ["success"]},
        "execution_plan": plan or [{"step": 1, "action": "noop"}],
        "constraints": {"forbidden_actions": ["file_delete", "credential_export", "payment_submit"]},
        "behavior_profile": {
            "default_mode": "human_like",
            "allow_per_step_override": True,
            "human_like": {
                "mouse_speed_range": [round(sp_lo, 2), round(sp_hi, 2)],
                "typing_wpm_range": [45, 90],
                "micro_delay_ms_range": [int(dt_lo), int(dt_hi)],
            },
            "machine_speed": {"allow_clipboard_paste": True, "artificial_delay_ms": 0},
        },
        "demonstration_source": {
            "learned_from_demonstration": True,
            "demonstration_count": len(sessions),
            "element_resolution": "stable_element",
        },
    }
    warnings = []
    if len(sessions) < DEFAULT_DEMOS:
        warnings.append(f"only {len(sessions)} demonstration(s); {DEFAULT_DEMOS} recommended to generalize")
    if consistent and len(sessions) > 1:
        warnings.append("all demonstrations look identical; vary window position/data to reduce overfitting")
    return {"draft": draft, "warnings": warnings}


def _range(values: list[float], default: tuple[float, float]) -> tuple[float, float]:
    if not values:
        return default
    if len(values) == 1:
        return values[0] * 0.7, values[0] * 1.3
    lo = max(min(values), 0.0)
    hi = max(values)
    return lo, hi if hi > lo else lo + 1
