"""Safe simulated automation backend (the default).

Performs NO real OS input. It models the full action interface — including
realistic timing derived from the behavior profile, a bounded click
retry-with-recheck loop, focus-before-typing, read-back verification, and a
zoom/region re-capture action — so the entire agent system is runnable and
testable on a headless machine (CI, Docker) without a physical desktop.

A small in-memory "virtual screen" lets expectations actually pass/fail in a
deterministic way for demos and tests.
"""
from __future__ import annotations

import random
import time
from typing import Any

from .base import ActionResult
from .behavior import BehaviorProfile, bezier_path, keystroke_delays, move_duration_seconds
from .oscompat import current_os, validate_command
from .verification import check_expectation


class VirtualScreen:
    """A trivial model of on-screen state so verification is meaningful."""

    def __init__(self) -> None:
        self.focused_window: str | None = None
        self.fields: dict[str, str] = {}
        self.screen_text: str = ""

    def observe(self, target_field: str | None = None) -> dict[str, Any]:
        return {
            "focused_window": self.focused_window,
            "screen_text": self.screen_text,
            "field_value": self.fields.get(target_field) if target_field else None,
            "element_state": "enabled",
        }


class SimulatedBackend:
    name = "simulated"

    def __init__(self) -> None:
        self.os_name = current_os()
        self.screen = VirtualScreen()
        # Global speed factor so demos don't actually sleep for whole seconds.
        self._time_scale = 0.05

    # --- helpers ---------------------------------------------------------
    def _pace(self, seconds: float) -> None:
        if seconds > 0:
            time.sleep(min(seconds * self._time_scale, 0.25))

    # --- interface -------------------------------------------------------
    def focus_window(self, target: str, expect: dict | None = None, behavior: dict | None = None) -> ActionResult:
        prof = BehaviorProfile.from_dict(behavior)
        self._pace(move_duration_seconds(prof, 400))
        self.screen.focused_window = target
        self.screen.screen_text = f"[window:{target}]"
        observed = self.screen.observe()
        expect = expect or {"window_focused": target}
        verified, detail = check_expectation(expect, observed)
        return ActionResult(True, verified, "focus_window", detail, observed)

    def click(self, target: str, expect: dict | None = None, behavior: dict | None = None) -> ActionResult:
        prof = BehaviorProfile.from_dict(behavior)
        start = (random.uniform(0, 1920), random.uniform(0, 1080))
        end = (random.uniform(0, 1920), random.uniform(0, 1080))
        path = bezier_path(start, end)
        dist = ((end[0] - start[0]) ** 2 + (end[1] - start[1]) ** 2) ** 0.5
        # Bounded retry-with-recheck loop rather than blindly repeating a click.
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            self._pace(move_duration_seconds(prof, dist) / len(path) * len(path))
            self.screen.screen_text = f"[clicked:{target}]"
            observed = self.screen.observe()
            if expect is None:
                # No declared post-condition -> unverified, do not retry.
                return ActionResult(True, False, "click", "no success condition declared", observed, attempt - 1)
            verified, detail = check_expectation(expect, observed)
            if verified:
                return ActionResult(True, True, "click", detail, observed, attempt - 1)
            # Re-capture region and try again with a slightly adjusted target.
        return ActionResult(True, False, "click", f"post-click state not observed after {max_attempts} attempts", observed, max_attempts - 1)

    def _type(self, field: str, value: str, secret: bool, expect: dict | None, behavior: dict | None) -> ActionResult:
        prof = BehaviorProfile.from_dict(behavior)
        # Confirm target focus before typing.
        if self.screen.focused_window is None:
            return ActionResult(False, False, "type", "no focused window; refusing to type")
        # machine-speed may inject via clipboard paste
        if prof.mode == "machine_speed" and prof.allow_clipboard_paste:
            self._pace(0.02)
        else:
            for d in keystroke_delays(prof, value):
                self._pace(d)
        self.screen.fields[field] = value
        # For secrets we still verify the field is non-empty but never echo it.
        observed = self.screen.observe(target_field=field)
        if expect is None and not secret:
            expect = {"field_value": value}
        if secret:
            verified = self.screen.fields.get(field) not in (None, "")
            detail = "secret entered and field non-empty" if verified else "field empty after entry"
            observed = {**observed, "field_value": "***REDACTED***"}
            return ActionResult(True, verified, "type_secret", detail, observed)
        verified, detail = check_expectation(expect, observed)
        return ActionResult(True, verified, "type", detail, observed)

    def type_text(self, field: str, value: str, expect: dict | None = None, behavior: dict | None = None) -> ActionResult:
        return self._type(field, value, False, expect, behavior)

    def type_secret(self, field: str, secret_value: str, expect: dict | None = None, behavior: dict | None = None) -> ActionResult:
        return self._type(field, secret_value, True, expect, behavior)

    def screenshot(self, region: dict | None = None, redact: bool = True) -> dict:
        # Returns a descriptor, never real pixel data in simulation. The
        # `zoom`/region re-capture action is modeled by echoing the region.
        return {
            "backend": "simulated",
            "region": region,
            "redacted": redact,
            "focused_window": self.screen.focused_window,
            "note": "no real screen captured in simulated mode",
        }

    def run_command(self, command: str, expect: dict | None = None) -> ActionResult:
        check = validate_command(command)
        if not check.ok:
            return ActionResult(False, False, "run_command", f"rejected: {check.reason}")
        self._pace(0.05)
        observed = {"screen_text": f"[ran:{check.translated}]", "exit_code": 0}
        if expect is None:
            return ActionResult(True, False, "run_command", "command ran; no success condition declared", observed)
        verified, detail = check_expectation(expect, observed)
        return ActionResult(True, verified, "run_command", detail, observed)
