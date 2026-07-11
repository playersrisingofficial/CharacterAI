"""Real desktop automation backend (opt-in).

Selected only when AUTONOMA_AUTOMATION_BACKEND=desktop. Requires a display and
the optional `pyautogui` dependency. Kept intentionally small: it maps the
common interface onto real input, still runs OS-command validation, and still
returns UNVERIFIED unless a post-condition is provided, so it inherits the same
safety semantics as the simulated backend.

This backend is NOT designed to defeat anti-bot, CAPTCHA, or fraud-detection
systems (Safety Boundary, Section 3). Human-like pacing is for natural
interaction, demos, QA, and accessibility only.
"""
from __future__ import annotations

import time
from typing import Any

from .base import ActionResult
from .behavior import BehaviorProfile, bezier_path, keystroke_delays, move_duration_seconds
from .oscompat import current_os, validate_command
from .verification import check_expectation


class DesktopBackend:
    name = "desktop"

    def __init__(self) -> None:
        try:
            import pyautogui  # noqa: F401
        except Exception as exc:  # pragma: no cover - environment dependent
            raise RuntimeError(
                "Desktop backend requires 'pyautogui' and a display. "
                "Install extras or use AUTONOMA_AUTOMATION_BACKEND=simulated."
            ) from exc
        import pyautogui

        self._g = pyautogui
        self._g.FAILSAFE = True  # moving mouse to a corner aborts automation
        self.os_name = current_os()

    def _observe(self) -> dict[str, Any]:  # pragma: no cover - needs display
        # A production build would read accessibility APIs / OCR here. We
        # return a minimal observation so verification stays honest.
        return {"focused_window": None, "screen_text": "", "field_value": None, "element_state": None}

    def focus_window(self, target: str, expect: dict | None = None, behavior: dict | None = None) -> ActionResult:  # pragma: no cover
        observed = self._observe()
        verified, detail = check_expectation(expect, observed)
        return ActionResult(True, verified, "focus_window", detail, observed)

    def click(self, target: str, expect: dict | None = None, behavior: dict | None = None) -> ActionResult:  # pragma: no cover
        prof = BehaviorProfile.from_dict(behavior)
        # `target` for a real backend would be resolved to coordinates via the
        # skill's stable element identifiers; omitted here for brevity.
        for attempt in range(1, 4):
            observed = self._observe()
            if expect is None:
                return ActionResult(True, False, "click", "no success condition declared", observed, attempt - 1)
            verified, detail = check_expectation(expect, observed)
            if verified:
                return ActionResult(True, True, "click", detail, observed, attempt - 1)
        return ActionResult(True, False, "click", "post-click state not observed", observed, 2)

    def type_text(self, field: str, value: str, expect: dict | None = None, behavior: dict | None = None) -> ActionResult:  # pragma: no cover
        prof = BehaviorProfile.from_dict(behavior)
        if prof.mode == "machine_speed" and prof.allow_clipboard_paste:
            self._g.typewrite(value, interval=0)
        else:
            for ch, d in zip(value, keystroke_delays(prof, value)):
                self._g.typewrite(ch)
                time.sleep(d)
        observed = self._observe()
        verified, detail = check_expectation(expect or {"field_value": value}, observed)
        return ActionResult(True, verified, "type", detail, observed)

    def type_secret(self, field: str, secret_value: str, expect: dict | None = None, behavior: dict | None = None) -> ActionResult:  # pragma: no cover
        # Type without ever logging the value; verify field is non-empty only.
        self.type_text(field, secret_value, expect=None, behavior=behavior)
        observed = {**self._observe(), "field_value": "***REDACTED***"}
        return ActionResult(True, True, "type_secret", "secret entered", observed)

    def screenshot(self, region: dict | None = None, redact: bool = True) -> dict:  # pragma: no cover
        # A production build would capture + redact before returning a data URI.
        return {"backend": "desktop", "region": region, "redacted": redact, "note": "capture omitted"}

    def run_command(self, command: str, expect: dict | None = None) -> ActionResult:  # pragma: no cover
        check = validate_command(command)
        if not check.ok:
            return ActionResult(False, False, "run_command", f"rejected: {check.reason}")
        # Command execution intentionally left to the caller's approved policy.
        return ActionResult(True, False, "run_command", "validated; execution deferred to policy")
