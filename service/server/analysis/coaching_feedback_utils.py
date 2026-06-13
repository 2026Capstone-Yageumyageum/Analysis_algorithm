from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


MIN_CONFIDENCE = 0.05
PHASE_ORDER = {
    "windup": 0,
    "leg_lift": 1,
    "stride": 2,
    "acceleration": 3,
    "follow_through": 4,
}
SEVERITY_WEIGHT = {"high": 3.0, "medium": 2.0, "info": 1.0}


@dataclass(frozen=True)
class PosePoint:
    x: float
    y: float
    frame: int | float | None


@dataclass(frozen=True)
class AxisRule:
    phase: str
    joint_role: str
    axis: str
    percent: float
    threshold: float
    category: str
    metric_label: str
    positive_message: str
    negative_message: str


@dataclass(frozen=True)
class CoachingTip:
    phase: str | None
    category: str
    severity: str
    message: str
    magnitude: float
    evidence: dict[str, Any]

    def feedback_item(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "message": self.message,
            "evidence": feedback_evidence(self.evidence),
        }


def make_tip(
    phase: str | None,
    category: str,
    severity: str,
    message: str,
    magnitude: float,
    evidence: dict[str, Any],
) -> CoachingTip:
    return CoachingTip(
        phase=phase or None,
        category=category,
        severity=severity,
        message=message,
        magnitude=float(magnitude),
        evidence=evidence,
    )


def feedback_evidence(raw: dict[str, Any]) -> dict[str, Any]:
    pro_frame = safe_float(raw.get("proFrame"), fallback=None)
    user_frame = safe_float(raw.get("userFrame"), fallback=None)
    pro_percent = safe_float(raw.get("proPhasePercent", raw.get("proPitchPercent")), fallback=None)
    user_percent = safe_float(raw.get("userPhasePercent", raw.get("userPitchPercent")), fallback=None)
    difference_percent = safe_float(raw.get("differencePercent"), fallback=None)
    difference = safe_float(raw.get("difference"), fallback=None)
    if difference is None and difference_percent is not None:
        difference = abs(difference_percent) / 100.0
    return {
        "proFrame": frame_value(pro_frame),
        "userFrame": frame_value(user_frame),
        "proPhasePercent": _percent_value(pro_percent),
        "userPhasePercent": _percent_value(user_percent),
        "differencePercent": _percent_value(difference_percent),
        "difference": round(abs(difference), 4) if difference is not None else None,
    }


def point_at_phase(table: pd.DataFrame, phases: Any, phase: str, joint: str, percent: float) -> PosePoint | None:
    frame = phase_frame(phases, phase, percent)
    if frame is None:
        return None
    return point_at_frame(table, joint, frame)


def point_at_frame(table: pd.DataFrame, joint: str, frame: float) -> PosePoint | None:
    if table.empty or "frame_index" not in table:
        return None
    x_column = f"{joint}_body_x"
    y_column = f"{joint}_body_y"
    if x_column not in table or y_column not in table:
        return None
    frames = pd.to_numeric(table["frame_index"], errors="coerce").to_numpy(dtype=float)
    x_values = pd.to_numeric(table[x_column], errors="coerce").interpolate(limit_direction="both").to_numpy(dtype=float)
    y_values = pd.to_numeric(table[y_column], errors="coerce").interpolate(limit_direction="both").to_numpy(dtype=float)
    valid = np.isfinite(frames) & np.isfinite(x_values) & np.isfinite(y_values)
    confidence_column = f"{joint}_confidence"
    if confidence_column in table:
        confidence = pd.to_numeric(table[confidence_column], errors="coerce").fillna(0.0).to_numpy(dtype=float)
        valid = valid & (confidence >= MIN_CONFIDENCE)
    if not valid.any():
        return None
    order = np.argsort(frames[valid])
    sorted_frames = frames[valid][order]
    return PosePoint(
        x=float(np.interp(frame, sorted_frames, x_values[valid][order])),
        y=float(np.interp(frame, sorted_frames, y_values[valid][order])),
        frame=frame_value(frame),
    )


def phase_frame(phases: Any, phase: str, percent: float) -> float | None:
    interval = (getattr(phases, "intervals", {}) or {}).get(phase) or {}
    start = safe_float(interval.get("startFrame"), fallback=None)
    end = safe_float(interval.get("endFrame"), fallback=None)
    if start is None or end is None:
        return None
    return start + ((end - start) * max(0.0, min(100.0, percent)) / 100.0)


def metric_value(point: PosePoint, axis: str) -> float:
    if axis == "y":
        return point.y
    if axis == "abs_x":
        return abs(point.x)
    if axis == "distance":
        return math.hypot(point.x, point.y)
    return point.x


def joint_name(table: pd.DataFrame, role: str) -> str:
    throwing_side = side_value(table, "throwing_side", "right")
    stride_side = side_value(table, "stride_side", "left" if throwing_side == "right" else "right")
    names = {
        "throwing_wrist": f"{throwing_side}_wrist",
        "throwing_elbow": f"{throwing_side}_elbow",
        "stride_knee": f"{stride_side}_knee",
        "stride_foot": f"{stride_side}_foot_index",
    }
    return names.get(role, role)


def side_value(table: pd.DataFrame, column: str, fallback: str) -> str:
    if column not in table or table.empty:
        return fallback
    value = str(table[column].iloc[0] or fallback)
    return value if value in {"left", "right"} else fallback


def phase_duration_ratio(phases: Any, phase: str) -> float | None:
    intervals = getattr(phases, "intervals", {}) or {}
    target = intervals.get(phase) or {}
    total = 0.0
    for interval in intervals.values():
        start = safe_float(interval.get("startFrame"), fallback=None)
        end = safe_float(interval.get("endFrame"), fallback=None)
        if start is not None and end is not None:
            total += max(0.0, end - start)
    start = safe_float(target.get("startFrame"), fallback=None)
    end = safe_float(target.get("endFrame"), fallback=None)
    if start is None or end is None or total <= 0.0:
        return None
    return max(0.0, end - start) / total


def phase_label(phases: Any, phase: str) -> str:
    interval = (getattr(phases, "intervals", {}) or {}).get(phase) or {}
    return str(interval.get("label") or phase)


def unique_tips(tips: list[CoachingTip]) -> list[CoachingTip]:
    seen: set[tuple[str | None, str]] = set()
    unique: list[CoachingTip] = []
    for tip in tips:
        key = (tip.phase, tip.category)
        if key in seen:
            continue
        seen.add(key)
        unique.append(tip)
    return unique


def safe_float(value: Any, *, fallback: float | None) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if math.isfinite(parsed) else fallback


def frame_value(value: float | None) -> int | float | None:
    if value is None:
        return None
    if math.isclose(value, round(value)):
        return int(round(value))
    return round(value, 4)


def _percent_value(value: float | None) -> int | None:
    if value is None:
        return None
    return int(round(max(-100.0, min(100.0, value))))
