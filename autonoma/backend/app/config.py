"""Application configuration, loaded from environment with safe defaults."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path


def _bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    """Runtime settings. All values overridable via environment variables."""

    def __init__(self) -> None:
        self.data_dir: Path = Path(os.getenv("AUTONOMA_DATA_DIR", "./data")).resolve()
        self.db_path: Path = self.data_dir / "autonoma.db"

        # Master key used to encrypt the local secret vault. If unset a
        # process-local key is generated (secrets will not survive a restart).
        self.vault_key: str | None = os.getenv("AUTONOMA_VAULT_KEY")

        # Desktop automation backend: "simulated" (safe, default) performs no
        # real OS input; "desktop" drives real mouse/keyboard via pyautogui.
        self.automation_backend: str = os.getenv("AUTONOMA_AUTOMATION_BACKEND", "simulated")

        # Explicit, user-configured working directory for any skill that is
        # granted direct file access. Never defaults to a root/home path.
        self.work_dir: Path | None = (
            Path(os.getenv("AUTONOMA_WORK_DIR")).resolve() if os.getenv("AUTONOMA_WORK_DIR") else None
        )

        # Default session cost ceiling (USD). None disables the ceiling.
        _ceiling = os.getenv("AUTONOMA_SESSION_COST_CEILING")
        self.session_cost_ceiling: float | None = float(_ceiling) if _ceiling else None

        # Stuck-detection thresholds (seconds / counts).
        self.stuck_no_progress_seconds: int = int(os.getenv("AUTONOMA_STUCK_SECONDS", "60"))
        self.stuck_retry_limit: int = int(os.getenv("AUTONOMA_STUCK_RETRIES", "3"))
        self.stuck_verification_failures: int = int(os.getenv("AUTONOMA_STUCK_VERIFY_FAILS", "3"))

        # Health heartbeat interval (seconds).
        self.heartbeat_interval: float = float(os.getenv("AUTONOMA_HEARTBEAT_INTERVAL", "5"))

        # How fast the simulated agent steps through a plan (seconds/step).
        self.sim_step_seconds: float = float(os.getenv("AUTONOMA_SIM_STEP_SECONDS", "1.2"))

        self.cors_origins: list[str] = [
            o.strip() for o in os.getenv("AUTONOMA_CORS_ORIGINS", "*").split(",") if o.strip()
        ]

        self.serve_frontend: bool = _bool("AUTONOMA_SERVE_FRONTEND", True)

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    return s
