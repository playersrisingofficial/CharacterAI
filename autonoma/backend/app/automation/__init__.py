"""Desktop automation abstraction layer.

`get_backend()` returns the configured backend. The default is the safe
`SimulatedBackend`, which performs no real OS input — it models the same
interface, timing behavior, verification, and event flow so the whole system
is runnable and testable without a physical desktop. Setting
AUTONOMA_AUTOMATION_BACKEND=desktop selects the real pyautogui-driven backend.
"""
from __future__ import annotations

from functools import lru_cache

from ..config import get_settings
from .base import AutomationBackend
from .simulated import SimulatedBackend


@lru_cache
def get_backend() -> AutomationBackend:
    settings = get_settings()
    if settings.automation_backend == "desktop":
        from .desktop import DesktopBackend  # imported lazily; needs a display

        return DesktopBackend()
    return SimulatedBackend()
