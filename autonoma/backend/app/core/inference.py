"""Inference-mode configuration manager (Section 2).

Governs where *model inference* runs (Local / API-Based / Hybrid) and enforces
the Provider Endpoint Constraint: only plain chat/completion endpoints
(including multimodal) are allowed. The provider's own autonomous
agentic/tool-use/"computer use" endpoints are disallowed, because routing
through them would create a second, uncoordinated control loop that bypasses
this app's input lock, approval queue, and audit trail.
"""
from __future__ import annotations

from typing import Any

from .. import database as db
from .. import events

_KV_KEY = "inference_config"

# Allowed endpoint capability types. Constraint is by capability TYPE, not a
# hardcoded allow/deny list of specific models/providers (which change often).
ALLOWED_ENDPOINT_TYPES = {"chat_completion", "multimodal_completion"}
DISALLOWED_ENDPOINT_TYPES = {"agentic", "tool_use", "computer_use", "responses_agent", "assistant"}

DEFAULT_CONFIG: dict[str, Any] = {
    "inference_mode": "api_based",
    "local_config": {
        "model": "example-local-model",
        "min_ram_gb": 16,
        "gpu_required": True,
        "min_vram_gb": 8,
        "disk_space_gb": 20,
    },
    "api_config": {
        "provider": "openrouter",
        "model": "example-api-model",
        "endpoint_type": "multimodal_completion",
        "requires_network": True,
    },
    "routing_rules": {
        "simple_steps": "local",
        "complex_reasoning": "api_based",
    },
}


class InferenceError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def get_config() -> dict[str, Any]:
    return db.kv_get(_KV_KEY, DEFAULT_CONFIG)


def _validate(config: dict[str, Any]) -> None:
    mode = config.get("inference_mode")
    if mode not in {"local", "api_based", "hybrid"}:
        raise InferenceError("inference_mode must be local|api_based|hybrid")

    if mode in {"api_based", "hybrid"}:
        api = config.get("api_config") or {}
        etype = api.get("endpoint_type")
        if etype in DISALLOWED_ENDPOINT_TYPES:
            raise InferenceError(
                f"endpoint_type '{etype}' is disallowed: the provider's own "
                "agentic/tool-use/computer-use endpoint would bypass this app's "
                "input lock, approval queue, and audit trail. Use a plain "
                "chat/completion or multimodal_completion endpoint instead."
            )
        if etype not in ALLOWED_ENDPOINT_TYPES:
            raise InferenceError(
                f"endpoint_type must be one of {sorted(ALLOWED_ENDPOINT_TYPES)} "
                "(vision/multimodal input is allowed and expected)."
            )


async def set_config(config: dict[str, Any]) -> dict[str, Any]:
    merged = {**get_config(), **config}
    _validate(merged)
    db.kv_set(_KV_KEY, merged)
    await events.bus.publish("inference_mode_changed", inference_mode=merged["inference_mode"],
                             config=merged)
    return merged


def route_step(step_kind: str) -> str:
    """Resolve which inference target handles a step under the current config."""
    cfg = get_config()
    mode = cfg["inference_mode"]
    if mode != "hybrid":
        return mode
    rules = cfg.get("routing_rules", {})
    return rules.get(step_kind, "api_based")
