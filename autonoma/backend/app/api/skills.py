"""Skills Management API (Section 8)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query, Response

from ..core import demonstrations as demo
from ..core import skills as sk

router = APIRouter(prefix="/api/v1/skills", tags=["skills"])


def _err(exc: sk.SkillError) -> HTTPException:
    return HTTPException(status_code=exc.status, detail=str(exc))


@router.post("", status_code=201)
@router.post("/", status_code=201)
def create_skill(payload: dict[str, Any] = Body(...)):
    try:
        return sk.create_skill(payload)
    except sk.SkillError as exc:
        raise _err(exc)


@router.get("")
@router.get("/")
def list_skills(status: str | None = Query(default=None)):
    return sk.list_skills(status=status)


# --- demonstration endpoints (declared before /{skill_id} to avoid capture) --

@router.post("/demonstrations/start", status_code=202)
def demo_start(payload: dict[str, Any] = Body(...)):
    name = payload.get("skill_name")
    if not name:
        raise HTTPException(400, "skill_name required")
    return demo.start_session(name)


@router.post("/demonstrations/{session_id}/stop")
def demo_stop(session_id: str):
    try:
        return demo.stop_session(session_id)
    except KeyError:
        raise HTTPException(404, "demonstration session not found")


@router.post("/demonstrations/{session_id}/trace")
def demo_trace(session_id: str, trace: dict[str, Any] = Body(...)):
    try:
        demo.record_trace(session_id, trace)
        return {"ok": True}
    except KeyError:
        raise HTTPException(404, "demonstration session not found")


@router.get("/demonstrations")
def demo_list(skill_name: str = Query(...)):
    return demo.list_sessions(skill_name)


@router.post("/demonstrations/generate", status_code=201)
def demo_generate(payload: dict[str, Any] = Body(...)):
    name = payload.get("skill_name")
    ids = payload.get("demonstration_session_ids", [])
    if not name or not ids:
        raise HTTPException(400, "skill_name and demonstration_session_ids required")
    try:
        return demo.generate_skill_draft(name, ids)
    except KeyError as exc:
        raise HTTPException(404, str(exc))


# --- per-skill endpoints ----------------------------------------------------

@router.get("/{skill_id}")
def get_skill(skill_id: str):
    skill = sk.get_latest(skill_id)
    if skill is None:
        raise HTTPException(404, "skill not found")
    return skill


@router.get("/{skill_id}/versions/{version}")
def get_skill_version(skill_id: str, version: int):
    skill = sk.get_version(skill_id, version)
    if skill is None:
        raise HTTPException(404, "version not found")
    return skill


@router.put("/{skill_id}")
def update_skill(skill_id: str, payload: dict[str, Any] = Body(...)):
    try:
        return sk.update_skill(skill_id, payload)
    except sk.SkillError as exc:
        raise _err(exc)


@router.patch("/{skill_id}/status")
def patch_status(skill_id: str, payload: dict[str, Any] = Body(...)):
    try:
        return sk.set_status(skill_id, payload.get("status"))
    except sk.SkillError as exc:
        raise _err(exc)


@router.post("/{skill_id}/rollback")
def rollback(skill_id: str, payload: dict[str, Any] = Body(...)):
    target = payload.get("target_version")
    if target is None:
        raise HTTPException(400, "target_version required")
    try:
        return sk.rollback(skill_id, int(target))
    except sk.SkillError as exc:
        raise _err(exc)


@router.delete("/{skill_id}", status_code=204)
def delete_skill(skill_id: str):
    try:
        sk.archive(skill_id)
    except sk.SkillError as exc:
        raise _err(exc)
    return Response(status_code=204)
