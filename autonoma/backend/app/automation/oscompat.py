"""OS command-compatibility validation.

A documented failure in comparable tools is generating Unix-style shell syntax
(e.g. `echo -e`, bash-specific flags) that silently produces wrong output on
Windows without raising an error. This module translates or *rejects*
OS-incompatible commands before execution rather than passing them through.
"""
from __future__ import annotations

import platform
import re
from dataclasses import dataclass


@dataclass
class CommandCheck:
    ok: bool
    reason: str = ""
    translated: str | None = None


# Patterns that are bash/POSIX-specific and misbehave silently under cmd.exe.
_UNIX_ONLY = [
    (re.compile(r"\becho\s+-e\b"), "`echo -e` is bash-specific; cmd.exe prints the flag literally"),
    (re.compile(r"\b(ls|grep|cat|rm|cp|mv|touch|chmod|chown|sed|awk)\b"), "POSIX-only coreutils command"),
    (re.compile(r"&&|\|\|"), None),  # allowed on both, informational only
    (re.compile(r"\$\{?\w+\}?"), "POSIX variable expansion (`$VAR`) differs from cmd.exe `%VAR%`"),
    (re.compile(r"/dev/null"), "`/dev/null` does not exist on Windows (use NUL)"),
]

_WINDOWS_ONLY = [
    (re.compile(r"%\w+%"), "cmd.exe variable expansion (`%VAR%`) differs from POSIX `$VAR`"),
    (re.compile(r"\b(dir|copy|del|type|cls)\b", re.I), "cmd.exe builtin not present on POSIX shells"),
    (re.compile(r"\bNUL\b"), "`NUL` is a Windows device; POSIX uses /dev/null"),
]


def current_os() -> str:
    sysname = platform.system().lower()
    if "windows" in sysname:
        return "windows"
    if "darwin" in sysname:
        return "macos"
    return "linux"


def validate_command(command: str, target_os: str | None = None) -> CommandCheck:
    """Reject a command that uses syntax incompatible with the target OS.

    A few safe, deterministic translations are applied (e.g. /dev/null <-> NUL);
    anything not confidently translatable is rejected so the caller can fall
    back to an OS-native action instead of silently doing the wrong thing.
    """
    target = (target_os or current_os()).lower()
    cmd = command.strip()

    if target == "windows":
        for pat, reason in _UNIX_ONLY:
            if reason and pat.search(cmd):
                if pat.pattern == r"/dev/null":
                    return CommandCheck(True, translated=cmd.replace("/dev/null", "NUL"))
                return CommandCheck(False, reason=f"Incompatible with Windows: {reason}")
    else:  # linux / macos
        for pat, reason in _WINDOWS_ONLY:
            if pat.search(cmd):
                if pat.pattern == r"\bNUL\b":
                    return CommandCheck(True, translated=re.sub(r"\bNUL\b", "/dev/null", cmd))
                return CommandCheck(False, reason=f"Incompatible with {target}: {reason}")

    return CommandCheck(True, translated=cmd)
