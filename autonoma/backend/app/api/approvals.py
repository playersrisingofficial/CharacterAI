"""Approval + secrets + session-config API (Sections 4, 9, 10)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException

from .. import secrets_vault
from ..core.approvals import approval_queue, cost_ceiling
from ..core.safety import HIGH_RISK_ACTIONS

router = APIRouter(prefix="/api/v1", tags=["safety"])


@router.get("/approvals")
def list_approvals():
    """Pending approvals — presented one at a time via the sequential queue."""
    return approval_queue.snapshot()


@router.get("/approvals/high-risk-actions")
def high_risk_actions():
    return {"high_risk_actions": HIGH_RISK_ACTIONS}


@router.post("/approvals/{request_id}/grant")
async def grant(request_id: str):
    if not await approval_queue.resolve(request_id, True):
        raise HTTPException(404, "approval request not found or already resolved")
    return {"ok": True}


@router.post("/approvals/{request_id}/deny")
async def deny(request_id: str):
    if not await approval_queue.resolve(request_id, False):
        raise HTTPException(404, "approval request not found or already resolved")
    return {"ok": True}


@router.get("/session/cost")
def get_cost():
    return cost_ceiling.snapshot()


@router.post("/session/cost-ceiling")
def set_cost_ceiling(payload: dict[str, Any] = Body(...)):
    cost_ceiling.set_limit(payload.get("limit_usd"))
    return cost_ceiling.snapshot()


# --- secrets: store references, never expose raw values (Section 10) --------

@router.get("/secrets")
def list_secrets():
    return {"refs": secrets_vault.list_secret_refs()}


@router.post("/secrets", status_code=201)
def store_secret(payload: dict[str, Any] = Body(...)):
    name = payload.get("name")
    value = payload.get("value")
    if not name or value is None:
        raise HTTPException(400, "name and value required")
    ref = secrets_vault.store_secret(name, value)
    # Return only the opaque reference — never the value.
    return {"secret_ref": ref}
