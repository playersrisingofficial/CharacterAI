"""Inference Mode Selection & Hardware Requirements API (Section 2)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query

from ..core import hardware, inference

router = APIRouter(prefix="/api/v1/inference-mode", tags=["inference-mode"])


@router.get("/options")
def options(agents: int = Query(default=1)):
    cfg = inference.get_config()
    return {
        "modes": hardware.all_modes(agents, cfg.get("local_config")),
        "allowed_endpoint_types": sorted(inference.ALLOWED_ENDPOINT_TYPES),
        "disallowed_endpoint_types": sorted(inference.DISALLOWED_ENDPOINT_TYPES),
        "detected_system": hardware.detect_system(),
    }


@router.get("/current")
def current():
    return inference.get_config()


@router.post("")
@router.post("/")
async def set_mode(config: dict[str, Any] = Body(...)):
    try:
        return await inference.set_config(config)
    except inference.InferenceError as exc:
        raise HTTPException(exc.status, str(exc))


@router.get("/requirements")
def requirements(mode: str = Query(...), agents: int = Query(default=1)):
    cfg = inference.get_config()
    try:
        return hardware.estimate(mode, agents, cfg.get("local_config"))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
