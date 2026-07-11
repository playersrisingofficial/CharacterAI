"""Hardware requirement estimator for the three inference modes (Section 2).

Estimates scale with the active agent count (1-3) and, for local/hybrid, the
selected model's declared footprint. Used by both the API and the dashboard's
Hardware Requirements comparison panel.
"""
from __future__ import annotations

from typing import Any

try:
    import psutil
except Exception:  # pragma: no cover
    psutil = None


def detect_system() -> dict[str, Any]:
    """Best-effort detection of the host's CPU/RAM so the UI can render an
    inline recommendation. GPU detection is intentionally conservative."""
    info: dict[str, Any] = {"cpu_cores": None, "ram_gb": None, "gpu": "unknown"}
    if psutil is not None:
        info["cpu_cores"] = psutil.cpu_count(logical=True)
        info["ram_gb"] = round(psutil.virtual_memory().total / (1024 ** 3), 1)
    return info


def _local_estimate(agents: int, model: dict[str, Any] | None) -> dict[str, Any]:
    model = model or {}
    base_ram = model.get("min_ram_gb", 16)
    vram = model.get("min_vram_gb", 8)
    disk = model.get("disk_space_gb", 20)
    # Concurrency multiplies working-set memory but weights, cache, and disk
    # can be shared, so RAM scales sub-linearly and disk stays roughly fixed.
    ram = round(base_ram * (1 + 0.6 * (agents - 1)), 1)
    return {
        "min_cpu_cores": 4 + 2 * (agents - 1),
        "min_ram_gb": ram,
        "gpu": "required" if model.get("gpu_required", True) else "recommended",
        "min_vram_gb": round(vram * (1 + 0.5 * (agents - 1)), 1),
        "disk_space_gb": disk,
        "network_dependency": "none",
        "relative_cost": "high one-time hardware, no per-call cost",
        "relative_latency": "low latency once loaded; startup/model-load overhead",
    }


def _api_estimate(agents: int) -> dict[str, Any]:
    return {
        "min_cpu_cores": 2,
        "min_ram_gb": round(2 + 0.5 * (agents - 1), 1),
        "gpu": "none",
        "min_vram_gb": 0,
        "disk_space_gb": 1,
        "network_dependency": "required",
        "relative_cost": f"no hardware cost; ongoing API spend scales ~{agents}x with agents",
        "relative_latency": "network-bound; depends on provider",
    }


def _hybrid_estimate(agents: int, model: dict[str, Any] | None) -> dict[str, Any]:
    local = _local_estimate(agents, model)
    return {
        "min_cpu_cores": local["min_cpu_cores"],
        "min_ram_gb": round(local["min_ram_gb"] * 0.7, 1),
        "gpu": "recommended",
        "min_vram_gb": round(local["min_vram_gb"] * 0.6, 1),
        "disk_space_gb": local["disk_space_gb"],
        "network_dependency": "partial",
        "relative_cost": "moderate hardware + reduced API spend (local handles simple steps)",
        "relative_latency": "mixed; simple steps local/fast, complex steps network-bound",
    }


def estimate(mode: str, agents: int = 1, model: dict[str, Any] | None = None) -> dict[str, Any]:
    agents = max(1, min(3, int(agents)))
    if mode == "local":
        est = _local_estimate(agents, model)
    elif mode == "api_based":
        est = _api_estimate(agents)
    elif mode == "hybrid":
        est = _hybrid_estimate(agents, model)
    else:
        raise ValueError(f"unknown mode: {mode}")
    est["mode"] = mode
    est["agents"] = agents
    est["recommendation"] = _recommend(mode, est)
    return est


def _recommend(mode: str, est: dict[str, Any]) -> str:
    sysinfo = detect_system()
    ram = sysinfo.get("ram_gb")
    if mode in {"local", "hybrid"} and ram is not None and est["min_ram_gb"] > ram:
        # Non-blocking warning surfaced by the UI.
        return (
            f"Warning: estimated {est['min_ram_gb']} GB RAM exceeds detected {ram} GB. "
            "Consider API-Based mode or fewer agents."
        )
    if mode == "api_based":
        return "Recommended when local GPU/RAM is limited; requires network."
    if ram is not None:
        return f"Fits detected {ram} GB RAM for the current agent count."
    return "System specs not detected; enter them manually for a tailored recommendation."


def all_modes(agents: int = 1, local_model: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return [estimate(m, agents, local_model) for m in ("local", "api_based", "hybrid")]
