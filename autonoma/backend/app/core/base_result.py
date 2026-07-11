"""Small helpers to build ActionResults for non-backend (reasoning/wait) steps."""
from __future__ import annotations

from typing import Any

from ..automation.base import ActionResult


def make_ok(action: str, detail: str, observed: dict[str, Any] | None = None) -> ActionResult:
    # Non-input reasoning/utility steps are considered verified by completion.
    return ActionResult(ok=True, verified=True, action=action, detail=detail, observed=observed or {})


def make_failure(action: str, detail: str) -> ActionResult:
    return ActionResult(ok=False, verified=False, action=action, detail=detail)
