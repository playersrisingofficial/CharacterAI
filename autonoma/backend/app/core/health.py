"""Active liveness checks (Section 6).

Status must reflect an actual, freshly-performed check — not a flag set once
and never re-verified. Each call to `check()` re-probes the components right
then, and records the timestamp of the probe so the UI can show staleness.
"""
from __future__ import annotations

import time
from typing import Any

from .agents import registry
from .orchestrator import orchestrator


def check() -> dict[str, Any]:
    now = time.time()

    # Backend: verify the orchestrator loop is actually running right now.
    backend_alive = orchestrator._running and any(
        (not t.done()) for t in orchestrator._bg
    )

    agents_health = []
    for a in registry.all():
        # An agent is "online" if it is not stopped and its state was touched
        # recently (running agents update last_progress_at each step).
        recent = (now - a.last_progress_at) < 30 if a.status == "running" else True
        agents_health.append({
            "agent_id": a.agent_id,
            "status": a.status,
            "online": a.status != "stopped" and recent,
            "seconds_since_progress": round(now - a.last_progress_at, 1),
        })

    # Local inference server liveness (only relevant for local/hybrid).
    from . import inference
    cfg = inference.get_config()
    local_server = None
    if cfg["inference_mode"] in {"local", "hybrid"}:
        local_server = _probe_local_inference(cfg.get("local_config", {}))

    return {
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "backend": {"online": bool(backend_alive), "uptime_seconds": round(orchestrator.uptime(), 1)},
        "agents": agents_health,
        "local_inference_server": local_server,
        "inference_mode": cfg["inference_mode"],
    }


def _probe_local_inference(local_config: dict[str, Any]) -> dict[str, Any]:
    """Best-effort TCP/HTTP probe of a configured local inference endpoint.

    Returns online=False when unreachable rather than assuming it is up — the
    whole point of an active check.
    """
    endpoint = local_config.get("endpoint")  # e.g. http://127.0.0.1:11434
    if not endpoint:
        return {"configured": False, "online": False,
                "note": "no local inference endpoint configured"}
    try:
        import socket
        from urllib.parse import urlparse

        parsed = urlparse(endpoint)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        with socket.create_connection((host, port), timeout=1.0):
            return {"configured": True, "online": True, "endpoint": endpoint}
    except Exception as exc:
        return {"configured": True, "online": False, "endpoint": endpoint, "error": str(exc)}
