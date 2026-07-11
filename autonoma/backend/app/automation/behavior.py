"""Input behavior modes (Section 3): human-like vs machine-speed.

These helpers compute the *timing and motion characteristics* of an action.
The simulated backend uses them to model realistic pacing; the real backend
uses them to drive actual cursor paths and keystroke delays.

Note: human-like pacing exists for natural interaction, demos, QA, and
accessibility workflows. It is explicitly NOT tuned to defeat anti-bot,
CAPTCHA, or fraud-detection systems (Safety Boundary, Section 3).
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass


@dataclass
class BehaviorProfile:
    mode: str = "human_like"  # or "machine_speed"
    mouse_speed_range: tuple[float, float] = (0.4, 1.2)
    typing_wpm_range: tuple[float, float] = (45, 90)
    micro_delay_ms_range: tuple[int, int] = (50, 300)
    allow_clipboard_paste: bool = True
    artificial_delay_ms: int = 0

    @classmethod
    def from_dict(cls, d: dict | None, default_mode: str = "human_like") -> "BehaviorProfile":
        d = d or {}
        mode = d.get("mode", default_mode)
        human = d.get("human_like", {})
        machine = d.get("machine_speed", {})
        return cls(
            mode=mode,
            mouse_speed_range=tuple(human.get("mouse_speed_range", (0.4, 1.2))),
            typing_wpm_range=tuple(human.get("typing_wpm_range", (45, 90))),
            micro_delay_ms_range=tuple(human.get("micro_delay_ms_range", (50, 300))),
            allow_clipboard_paste=machine.get("allow_clipboard_paste", True),
            artificial_delay_ms=machine.get("artificial_delay_ms", 0),
        )


def bezier_path(start: tuple[float, float], end: tuple[float, float], steps: int = 24) -> list[tuple[float, float]]:
    """Quadratic Bézier path with a randomized control point and slight
    spatial jitter — a natural, curved cursor trajectory."""
    cx = (start[0] + end[0]) / 2 + random.uniform(-40, 40)
    cy = (start[1] + end[1]) / 2 + random.uniform(-40, 40)
    pts: list[tuple[float, float]] = []
    for i in range(steps + 1):
        t = i / steps
        x = (1 - t) ** 2 * start[0] + 2 * (1 - t) * t * cx + t ** 2 * end[0]
        y = (1 - t) ** 2 * start[1] + 2 * (1 - t) * t * cy + t ** 2 * end[1]
        # micro spatial randomness that decays near the target
        jitter = (1 - t) * 2.0
        x += random.uniform(-jitter, jitter)
        y += random.uniform(-jitter, jitter)
        pts.append((x, y))
    return pts


def move_duration_seconds(profile: BehaviorProfile, distance: float) -> float:
    if profile.mode == "machine_speed":
        return max(profile.artificial_delay_ms / 1000.0, 0.0)
    lo, hi = profile.mouse_speed_range
    base = random.uniform(lo, hi)
    # Variable acceleration: longer distances take proportionally more time.
    return base * (0.3 + math.log10(max(distance, 1)) / 4)


def keystroke_delays(profile: BehaviorProfile, text: str) -> list[float]:
    """Per-character delays in seconds."""
    if profile.mode == "machine_speed":
        return [0.0 for _ in text]
    wpm = random.uniform(*profile.typing_wpm_range)
    cps = max(wpm * 5 / 60.0, 1.0)  # ~5 chars/word
    base = 1.0 / cps
    delays = []
    for ch in text:
        d = base * random.uniform(0.6, 1.5)
        if random.random() < 0.06:  # occasional micro-pause
            lo, hi = profile.micro_delay_ms_range
            d += random.uniform(lo, hi) / 1000.0
        delays.append(d)
    return delays
