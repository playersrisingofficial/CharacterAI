"""Common automation interface and result types shared by all OS backends."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ActionResult:
    """Outcome of a single automation action.

    `verified` is the load-bearing field: it is True only when the action's
    post-condition was actually observed (Section 3, Action Verification).
    An action that dispatched without raising but whose outcome could not be
    confirmed is `ok=True, verified=False` and must NOT be reported as a
    successful, verified step.
    """

    ok: bool
    verified: bool
    action: str
    detail: str = ""
    observed: dict[str, Any] = field(default_factory=dict)
    retries: int = 0

    @property
    def audit_status(self) -> str:
        if not self.ok:
            return "failed"
        return "success" if self.verified else "unverified"


class AutomationBackend(Protocol):
    """OS-agnostic automation surface. Concrete backends implement each verb.

    Every verb accepts an optional `expect` dict describing the success
    condition to verify after acting, and a `behavior` profile controlling
    human-like vs machine-speed timing.
    """

    name: str
    os_name: str

    def focus_window(self, target: str, expect: dict | None = None, behavior: dict | None = None) -> ActionResult: ...

    def click(self, target: str, expect: dict | None = None, behavior: dict | None = None) -> ActionResult: ...

    def type_text(self, field: str, value: str, expect: dict | None = None, behavior: dict | None = None) -> ActionResult: ...

    def type_secret(self, field: str, secret_value: str, expect: dict | None = None, behavior: dict | None = None) -> ActionResult: ...

    def screenshot(self, region: dict | None = None, redact: bool = True) -> dict: ...

    def run_command(self, command: str, expect: dict | None = None) -> ActionResult: ...
