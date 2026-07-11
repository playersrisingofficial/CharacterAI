"""Skills registry: create, version, archive, roll back, and validate skills.

Every mutation creates a new immutable integer version; older versions remain
retrievable so running tasks keep using the version they started with
(Section 8). Skill payloads are validated against a JSON Schema before saving.
"""
from __future__ import annotations

import time
import uuid
from typing import Any

from jsonschema import Draft202012Validator

from .. import database as db

# JSON Schema every skill payload must satisfy (Section 7 requirements).
SKILL_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["name", "description", "skill_type", "input_schema", "output_schema", "execution_plan"],
    "properties": {
        "name": {"type": "string", "minLength": 1},
        "description": {"type": "string"},
        "skill_type": {"type": "string", "minLength": 1},
        "status": {"type": "string", "enum": ["active", "archived", "draft"]},
        "input_schema": {"type": "object"},
        "output_schema": {"type": "object"},
        "execution_plan": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["step", "action"],
                "properties": {
                    "step": {"type": "integer"},
                    "action": {"type": "string"},
                    "mode": {"type": "string", "enum": ["human_like", "machine_speed"]},
                },
            },
        },
        "constraints": {"type": "object"},
        "behavior_profile": {"type": "object"},
        "demonstration_source": {"type": "object"},
    },
    "additionalProperties": True,
}

_validator = Draft202012Validator(SKILL_SCHEMA)


class SkillError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def validate_payload(payload: dict[str, Any]) -> None:
    errors = sorted(_validator.iter_errors(payload), key=lambda e: e.path)
    if errors:
        msgs = "; ".join(f"{'/'.join(map(str, e.path)) or '<root>'}: {e.message}" for e in errors[:8])
        raise SkillError(f"skill failed schema validation: {msgs}", status=400)
    # Secrets must never be embedded in skills (Section 8 / 10).
    _reject_embedded_secrets(payload)


def _reject_embedded_secrets(obj: Any, path: str = "") -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str) and k.lower() in {"password", "secret", "api_key", "token"} and isinstance(v, str) and v:
                raise SkillError(f"skill must not embed raw secret at {path}/{k}; use a secret_ref", status=400)
            _reject_embedded_secrets(v, f"{path}/{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _reject_embedded_secrets(v, f"{path}[{i}]")


def _row_to_skill(row) -> dict[str, Any]:
    return db.loads(row["data"])


def create_skill(payload: dict[str, Any]) -> dict[str, Any]:
    validate_payload(payload)
    skill_id = f"skill_{uuid.uuid4().hex[:12]}"
    now = _now()
    skill = {
        **payload,
        "skill_id": skill_id,
        "version": 1,
        "status": payload.get("status", "active"),
        "created_at": now,
        "updated_at": now,
    }
    skill.setdefault("demonstration_source", {
        "learned_from_demonstration": False,
        "demonstration_count": 0,
        "element_resolution": "fixed_coordinates",
    })
    _insert_version(skill, is_latest=True)
    return skill


def _insert_version(skill: dict[str, Any], is_latest: bool) -> None:
    if is_latest:
        db.execute("UPDATE skills SET is_latest=0 WHERE skill_id=?", (skill["skill_id"],))
    db.execute(
        "INSERT INTO skills(skill_id, version, name, status, is_latest, data, created_at) "
        "VALUES(?,?,?,?,?,?,?)",
        (
            skill["skill_id"],
            skill["version"],
            skill["name"],
            skill["status"],
            1 if is_latest else 0,
            db.dumps(skill),
            skill["created_at"],
        ),
    )


def update_skill(skill_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    latest = get_latest(skill_id)
    if latest is None:
        raise SkillError(f"skill not found: {skill_id}", status=404)
    validate_payload(payload)
    new_version = latest["version"] + 1
    skill = {
        **payload,
        "skill_id": skill_id,
        "version": new_version,
        "status": payload.get("status", latest.get("status", "active")),
        "created_at": latest.get("created_at", _now()),
        "updated_at": _now(),
    }
    skill.setdefault("demonstration_source", latest.get("demonstration_source", {}))
    _insert_version(skill, is_latest=True)
    return skill


def set_status(skill_id: str, status: str) -> dict[str, Any]:
    if status not in {"active", "archived", "draft"}:
        raise SkillError("status must be active|archived|draft", status=400)
    latest = get_latest(skill_id)
    if latest is None:
        raise SkillError(f"skill not found: {skill_id}", status=404)
    # Status change updates the latest row in place (not a new behavioral version).
    latest["status"] = status
    latest["updated_at"] = _now()
    db.execute(
        "UPDATE skills SET status=?, data=? WHERE skill_id=? AND version=?",
        (status, db.dumps(latest), skill_id, latest["version"]),
    )
    return latest


def rollback(skill_id: str, target_version: int) -> dict[str, Any]:
    src = get_version(skill_id, target_version)
    if src is None:
        raise SkillError(f"version {target_version} not found for {skill_id}", status=404)
    latest = get_latest(skill_id)
    new_version = latest["version"] + 1
    skill = {**src, "version": new_version, "updated_at": _now(),
             "rolled_back_from": target_version, "status": "active"}
    _insert_version(skill, is_latest=True)
    return skill


def archive(skill_id: str) -> None:
    if get_latest(skill_id) is None:
        raise SkillError(f"skill not found: {skill_id}", status=404)
    set_status(skill_id, "archived")


def get_latest(skill_id: str) -> dict[str, Any] | None:
    row = db.query_one("SELECT data FROM skills WHERE skill_id=? AND is_latest=1", (skill_id,))
    return _row_to_skill(row) if row else None


def get_version(skill_id: str, version: int) -> dict[str, Any] | None:
    row = db.query_one("SELECT data FROM skills WHERE skill_id=? AND version=?", (skill_id, version))
    return _row_to_skill(row) if row else None


def resolve(skill_id: str, version: int | None) -> dict[str, Any] | None:
    """Resolve an explicit version if given, else the latest."""
    return get_version(skill_id, version) if version is not None else get_latest(skill_id)


def list_skills(status: str | None = None) -> list[dict[str, Any]]:
    if status:
        rows = db.query("SELECT data FROM skills WHERE is_latest=1 AND status=? ORDER BY created_at DESC", (status,))
    else:
        rows = db.query("SELECT data FROM skills WHERE is_latest=1 ORDER BY created_at DESC")
    out = []
    for r in rows:
        s = _row_to_skill(r)
        out.append({
            "skill_id": s["skill_id"], "version": s["version"], "name": s["name"],
            "skill_type": s.get("skill_type"), "status": s["status"],
            "description": s.get("description"), "updated_at": s.get("updated_at"),
        })
    return out


def list_versions(skill_id: str) -> list[int]:
    rows = db.query("SELECT version FROM skills WHERE skill_id=? ORDER BY version", (skill_id,))
    return [r["version"] for r in rows]


def active_skill_action_space() -> dict[str, list[str]]:
    """The valid (skill_id -> [action names]) map. Agents are only ever given
    this as their action space — never free-form skill naming (Section 7)."""
    space: dict[str, list[str]] = {}
    for meta in list_skills(status="active"):
        skill = get_latest(meta["skill_id"])
        if skill:
            space[skill["skill_id"]] = [s.get("action") for s in skill.get("execution_plan", [])]
    return space


def validate_skill_action_ref(skill_id: str, action: str | None = None) -> None:
    """Validate a skill (and optional action) against the live registry.

    Raises SkillError if the reference is unresolvable — callers must fail
    explicitly ("skill not found"), never silently retry or improvise
    (Section 7, Skill/Action Call Validation)."""
    skill = get_latest(skill_id)
    if skill is None or skill.get("status") != "active":
        raise SkillError(f"skill not found or not active: {skill_id}", status=404)
    if action is not None:
        actions = {s.get("action") for s in skill.get("execution_plan", [])}
        if action not in actions:
            raise SkillError(f"action '{action}' not in skill {skill_id}", status=404)
