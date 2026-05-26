from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd


RELEASE_POINT_GOOD_THRESHOLD = 0.22
RELEASE_TIMING_GOOD_THRESHOLD = 7.0
PHASE_GOOD_THRESHOLD = 78.0
PHASE_BAD_THRESHOLD = 68.0


def build_analysis_feedback(
    *,
    user_pose: pd.DataFrame,
    pro_pose: pd.DataFrame,
    user_phases: Any,
    pro_phases: Any,
    phase_scores: list[dict[str, Any]],
) -> dict[str, Any]:
    release = _build_release_feedback(
        user_pose=user_pose,
        pro_pose=pro_pose,
        user_phases=user_phases,
        pro_phases=pro_phases,
    )
    feedback = _build_phase_feedback(phase_scores)
    return {"release": release, "feedback": feedback}


def _build_release_feedback(
    *,
    user_pose: pd.DataFrame,
    pro_pose: pd.DataFrame,
    user_phases: Any,
    pro_phases: Any,
) -> dict[str, Any]:
    user_release = _release_frame(user_phases)
    pro_release = _release_frame(pro_phases)
    pro_percent = _pitch_percent(pro_release, pro_phases)
    user_percent = _pitch_percent(user_release, user_phases)
    difference_percent = _difference_percent(pro_percent, user_percent)

    pro_point = _throwing_wrist_point_at_frame(pro_pose, pro_release)
    user_point = _throwing_wrist_point_at_frame(user_pose, user_release)
    point_metrics = _point_metrics(pro_point, user_point)

    return {
        "proFrame": _frame_value(pro_release),
        "userFrame": _frame_value(user_release),
        "pro": _release_event_detail(pro_phases),
        "user": _release_event_detail(user_phases),
        "timing": {
            "proPitchPercent": pro_percent,
            "userPitchPercent": user_percent,
            "differencePercent": difference_percent,
            "message": _release_timing_message(difference_percent),
        },
        "point": {
            "difference": point_metrics["difference"],
            "heightDifference": point_metrics["heightDifference"],
            "sideDifference": point_metrics["sideDifference"],
            "message": _release_point_message(point_metrics),
        },
    }


def _release_event_detail(phases: Any) -> dict[str, Any]:
    event = ((getattr(phases, "events", {}) or {}).get("release") or {})
    frame = _safe_float(event.get("frame"), fallback=_release_frame(phases))
    before_frame = _safe_float(event.get("beforeFrame"), fallback=None)
    exit_frame = _safe_float(event.get("exitFrame"), fallback=None)
    return {
        "frame": _frame_value(frame),
        "beforeFrame": _frame_value(before_frame),
        "exitFrame": _frame_value(exit_frame),
        "method": str(event.get("method") or "unknown"),
        "status": str(event.get("status") or "unknown"),
        "source": str(event.get("source") or "unknown"),
    }


def _build_phase_feedback(phase_scores: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    ready_scores = [
        phase
        for phase in phase_scores
        if _safe_float(phase.get("score"), fallback=None) is not None
    ]
    good: list[dict[str, Any]] = []
    bad: list[dict[str, Any]] = []

    good_candidates = sorted(
        [phase for phase in ready_scores if float(phase["score"]) >= PHASE_GOOD_THRESHOLD],
        key=lambda phase: float(phase["score"]),
        reverse=True,
    )
    bad_candidates = sorted(
        [phase for phase in ready_scores if float(phase["score"]) <= PHASE_BAD_THRESHOLD],
        key=lambda phase: float(phase["score"]),
    )

    for phase in good_candidates[:2]:
        good.append(
            {
                "phase": phase.get("phase"),
                "message": f"{phase.get('label', '해당')} 구간의 전체 움직임이 선수와 비교적 비슷합니다.",
                "evidence": _phase_feedback_evidence(phase),
            }
        )

    for phase in bad_candidates[:2]:
        bad.append(
            {
                "phase": phase.get("phase"),
                "message": f"{phase.get('label', '해당')} 구간에서 선수와 움직임 차이가 크게 나타납니다.",
                "evidence": _phase_feedback_evidence(phase),
            }
        )

    if not good and ready_scores:
        phase = max(ready_scores, key=lambda item: float(item["score"]))
        good.append(
            {
                "phase": phase.get("phase"),
                "message": f"{phase.get('label', '해당')} 구간이 가장 안정적으로 유사합니다.",
                "evidence": _phase_feedback_evidence(phase),
            }
        )
    if not bad and ready_scores:
        phase = min(ready_scores, key=lambda item: float(item["score"]))
        bad.append(
            {
                "phase": phase.get("phase"),
                "message": f"{phase.get('label', '해당')} 구간은 비교적 더 점검이 필요합니다.",
                "evidence": _phase_feedback_evidence(phase),
            }
        )

    return {"good": good[:2], "bad": bad[:2]}


def _phase_feedback_evidence(phase: dict[str, Any]) -> dict[str, Any]:
    pro_start = _safe_float(phase.get("proStartFrame"), fallback=0.0)
    pro_end = _safe_float(phase.get("proEndFrame"), fallback=pro_start)
    user_start = _safe_float(phase.get("userStartFrame"), fallback=0.0)
    user_end = _safe_float(phase.get("userEndFrame"), fallback=user_start)
    score = _safe_float(phase.get("score"), fallback=None)
    return {
        "proFrame": _frame_value((pro_start + pro_end) / 2.0),
        "userFrame": _frame_value((user_start + user_end) / 2.0),
        "proPhasePercent": 50,
        "userPhasePercent": 50,
        "differencePercent": 0,
        "difference": round((100.0 - score) / 100.0, 4) if score is not None else None,
    }


def _release_frame(phases: Any) -> float | None:
    event_frame = ((getattr(phases, "events", {}) or {}).get("release") or {}).get("frame")
    frame = _safe_float(event_frame, fallback=None)
    if frame is not None:
        return frame
    representative_frame = (getattr(phases, "representative_frames", {}) or {}).get("release")
    return _safe_float(representative_frame, fallback=None)


def _pitch_percent(frame: float | None, phases: Any) -> int | None:
    if frame is None:
        return None
    intervals = getattr(phases, "intervals", {}) or {}
    if not intervals:
        return None
    starts = [_safe_float(interval.get("startFrame"), fallback=None) for interval in intervals.values()]
    ends = [_safe_float(interval.get("endFrame"), fallback=None) for interval in intervals.values()]
    valid_values = [value for value in starts + ends if value is not None]
    if len(valid_values) < 2:
        return None
    start = min(valid_values)
    end = max(valid_values)
    if math.isclose(start, end):
        return None
    percent = (frame - start) / (end - start) * 100.0
    return int(round(max(0.0, min(100.0, percent))))


def _difference_percent(pro_percent: int | None, user_percent: int | None) -> int | None:
    if pro_percent is None or user_percent is None:
        return None
    return int(round(user_percent - pro_percent))


def _throwing_wrist_point_at_frame(table: pd.DataFrame, frame: float | None) -> tuple[float, float] | None:
    if frame is None or table.empty or "frame_index" not in table.columns:
        return None
    throwing_side = str(table["throwing_side"].iloc[0] if "throwing_side" in table.columns else "right")
    x_column = f"{throwing_side}_wrist_body_x"
    y_column = f"{throwing_side}_wrist_body_y"
    confidence_column = f"{throwing_side}_wrist_confidence"
    if x_column not in table.columns or y_column not in table.columns:
        return None
    frames = pd.to_numeric(table["frame_index"], errors="coerce").to_numpy(dtype=float)
    x_values = pd.to_numeric(table[x_column], errors="coerce").interpolate(limit_direction="both").to_numpy(dtype=float)
    y_values = pd.to_numeric(table[y_column], errors="coerce").interpolate(limit_direction="both").to_numpy(dtype=float)
    valid = np.isfinite(frames) & np.isfinite(x_values) & np.isfinite(y_values)
    if confidence_column in table.columns:
        confidence = pd.to_numeric(table[confidence_column], errors="coerce").fillna(0.0).to_numpy(dtype=float)
        valid = valid & (confidence >= 0.05)
    if not valid.any():
        return None
    return (
        float(np.interp(frame, frames[valid], x_values[valid])),
        float(np.interp(frame, frames[valid], y_values[valid])),
    )


def _point_metrics(
    pro_point: tuple[float, float] | None,
    user_point: tuple[float, float] | None,
) -> dict[str, float | None]:
    if pro_point is None or user_point is None:
        return {"difference": None, "heightDifference": None, "sideDifference": None}
    side_difference = user_point[0] - pro_point[0]
    height_difference = user_point[1] - pro_point[1]
    return {
        "difference": round(math.dist(pro_point, user_point), 4),
        "heightDifference": round(height_difference, 4),
        "sideDifference": round(side_difference, 4),
    }


def _release_timing_message(difference_percent: int | None) -> str:
    if difference_percent is None:
        return "릴리즈 타이밍을 계산하지 못했습니다."
    if abs(difference_percent) <= RELEASE_TIMING_GOOD_THRESHOLD:
        return "릴리즈 타이밍이 선수와 비슷합니다."
    if difference_percent > 0:
        return "릴리즈 타이밍이 선수보다 늦게 나타납니다."
    return "릴리즈 타이밍이 선수보다 빠르게 나타납니다."


def _release_point_message(metrics: dict[str, float | None]) -> str:
    difference = metrics.get("difference")
    height_difference = metrics.get("heightDifference")
    side_difference = metrics.get("sideDifference")
    if difference is None:
        return "릴리즈 포인트를 계산하지 못했습니다."
    if difference <= RELEASE_POINT_GOOD_THRESHOLD:
        return "릴리즈 포인트가 선수와 비슷합니다."
    if height_difference is not None and abs(height_difference) >= abs(side_difference or 0.0):
        return "릴리즈 포인트가 선수보다 높게 형성됩니다." if height_difference > 0 else "릴리즈 포인트가 선수보다 낮게 형성됩니다."
    return "릴리즈 포인트가 선수보다 바깥쪽에 형성됩니다." if (side_difference or 0.0) > 0 else "릴리즈 포인트가 선수보다 몸쪽에 형성됩니다."


def _safe_float(value: Any, *, fallback: float | None) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if math.isfinite(parsed) else fallback


def _frame_value(value: float | None) -> int | float | None:
    if value is None:
        return None
    if math.isclose(value, round(value)):
        return int(round(value))
    return round(value, 4)
