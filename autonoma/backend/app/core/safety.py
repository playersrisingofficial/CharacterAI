"""High-risk action policy (Section 3 Safety Boundary, Section 9).

Central definition of which actions require explicit user approval, plus the
mapping from a skill's execution-plan step to a risk classification. The
orchestrator consults this before every step.
"""
from __future__ import annotations

from typing import Any

# Human-readable catalog surfaced in the UI (Section 9).
HIGH_RISK_ACTIONS = [
    "file_delete",
    "credential_entry",
    "login_submit",
    "payment_submit",
    "financial_transfer",
    "email_send",
    "mass_messaging",
    "external_network_upload",
    "software_install",
    "system_setting_change",
    "access_sensitive_folder",
    "run_destructive_command",
    "export_secret",
    "direct_file_access",  # any skill declaring direct filesystem access
]

# Map raw execution-plan action verbs to a high-risk classification.
_ACTION_RISK = {
    "type_secret": "credential_entry",
    "submit_login": "login_submit",
    "click_login": "login_submit",
    "submit_payment": "payment_submit",
    "transfer_funds": "financial_transfer",
    "send_email": "email_send",
    "send_bulk": "mass_messaging",
    "upload": "external_network_upload",
    "install": "software_install",
    "change_setting": "system_setting_change",
    "delete_file": "file_delete",
    "export_credentials": "export_secret",
    "run_command": None,  # depends on the command; classified below
}

_DESTRUCTIVE_TOKENS = ("rm -rf", "del /", "format ", "mkfs", "drop table", ":(){", "shutdown", "diskpart")


def classify_step(step: dict[str, Any]) -> str | None:
    """Return a high-risk classification for a step, or None if low-risk."""
    action = step.get("action", "")

    if action == "run_command":
        cmd = (step.get("command") or "").lower()
        if any(tok in cmd for tok in _DESTRUCTIVE_TOKENS):
            return "run_destructive_command"
        return None

    return _ACTION_RISK.get(action)


def step_requires_approval(step: dict[str, Any], skill: dict[str, Any]) -> tuple[bool, str | None]:
    """Decide whether a step needs approval, considering both the intrinsic
    action risk and the skill's declared `requires_user_approval_for` list."""
    risk = classify_step(step)
    constraints = skill.get("constraints", {}) or {}
    explicit = set(constraints.get("requires_user_approval_for", []) or [])

    # Skill authors can name either the action verb or the risk class.
    if step.get("action") in explicit or (risk and risk in explicit):
        return True, risk or step.get("action")
    if risk is not None:
        return True, risk
    return False, None


def validate_skill_constraints(skill: dict[str, Any], work_dir: str | None) -> list[str]:
    """Return a list of constraint violations (empty == ok).

    Enforces: any direct file access must be explicitly declared AND scoped to
    a configured working directory that is not a root/system/home path.
    """
    problems: list[str] = []
    constraints = skill.get("constraints", {}) or {}
    declares_file_access = "direct_file_access" in (constraints.get("declared_capabilities", []) or [])

    plan = skill.get("execution_plan", []) or []
    uses_file_action = any(s.get("action") in {"read_file", "write_file", "delete_file", "move_file"} for s in plan)

    if uses_file_action and not declares_file_access:
        problems.append(
            "execution_plan uses direct file actions but skill does not declare "
            "'direct_file_access' in constraints.declared_capabilities"
        )

    if declares_file_access:
        if not work_dir:
            problems.append(
                "skill declares direct_file_access but no AUTONOMA_WORK_DIR is configured; "
                "file access must be scoped to an explicit working directory"
            )
        else:
            unsafe = {"/", "/root", "/home", "/etc", "c:\\", "c:\\windows", "c:\\users"}
            if work_dir.rstrip("/\\").lower() in unsafe:
                problems.append(f"AUTONOMA_WORK_DIR '{work_dir}' is too broad; refuse root/system/home paths")

    return problems
