"""Post-action verification (Section 3, Action Verification & Precision).

No action is marked successful on absence-of-error alone. Each step may
declare an `expect` success condition; after the action is dispatched the
backend observes screen/field/window state and checks the condition. A failed
check is surfaced (feeding Stuck Detection), never silently logged as success.
"""
from __future__ import annotations

from typing import Any


def check_expectation(expect: dict[str, Any] | None, observed: dict[str, Any]) -> tuple[bool, str]:
    """Return (verified, detail).

    Supported expectation keys:
      - text_visible: substring expected to appear in observed screen text
      - field_value: value the target field should read back as
      - window_focused: window title/id expected to be focused
      - element_state: expected state token (e.g. "enabled", "checked")
    If no expectation is declared, the action is treated as UNVERIFIED (not
    silently successful) — callers should prefer declaring one.
    """
    if not expect:
        return False, "no success condition declared; outcome unverified"

    for key, want in expect.items():
        if key == "text_visible":
            screen = observed.get("screen_text", "")
            if want not in screen:
                return False, f"expected text '{want}' not visible on screen"
        elif key == "field_value":
            got = observed.get("field_value")
            if got != want:
                return False, f"field read back as {got!r}, expected {want!r}"
        elif key == "window_focused":
            if observed.get("focused_window") != want:
                return False, f"window '{want}' is not focused"
        elif key == "element_state":
            if observed.get("element_state") != want:
                return False, f"element state {observed.get('element_state')!r} != {want!r}"
        else:
            # Unknown expectation key — do not assume success.
            return False, f"unknown expectation '{key}'"

    return True, "post-condition verified"
