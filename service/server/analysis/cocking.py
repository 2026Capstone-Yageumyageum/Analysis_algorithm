from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd


MIN_CONFIDENCE = 0.05
MIN_LATE_ELBOW_HEIGHT_DELTA = -0.35


def detect_cocking_events(
    normalized_pose: pd.DataFrame,
    intervals: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Detect 2D elbow-based cocking proxy frames."""
    if normalized_pose.empty:
        return _unavailable("정규화된 keypoints가 없어 코킹 proxy를 계산하지 못했습니다.")

    throwing_side = str(normalized_pose["throwing_side"].iloc[0] if "throwing_side" in normalized_pose else "right")
    shoulder = f"{throwing_side}_shoulder"
    elbow = f"{throwing_side}_elbow"
    required_columns = [
        f"{shoulder}_body_x",
        f"{shoulder}_body_y",
        f"{shoulder}_confidence",
        f"{elbow}_body_x",
        f"{elbow}_body_y",
        f"{elbow}_confidence",
        "frame_index",
    ]
    missing = [column for column in required_columns if column not in normalized_pose.columns]
    if missing:
        return _unavailable(f"코킹 proxy에 필요한 컬럼이 없습니다: {', '.join(missing)}")

    early = _detect_early_cocking(normalized_pose, intervals.get("stride"), shoulder=shoulder, elbow=elbow)
    late = _detect_late_cocking(normalized_pose, intervals.get("acceleration"), shoulder=shoulder, elbow=elbow)
    status = "ready" if early["status"] == "ready" or late["status"] == "ready" else "unavailable"
    return {
        "status": status,
        "method": "2d_elbow_based_cocking_proxy_v1",
        "throwingSide": throwing_side,
        "earlyCocking": early,
        "lateCocking": late,
    }


def _detect_early_cocking(
    table: pd.DataFrame,
    interval: dict[str, Any] | None,
    *,
    shoulder: str,
    elbow: str,
) -> dict[str, Any]:
    if interval is None:
        return _unavailable_event("stride 구간이 없어 얼리 코킹 proxy를 계산하지 못했습니다.")

    start_frame = float(interval["startFrame"])
    end_frame = float(interval["endFrame"])
    segment = _segment(table, start_frame, end_frame)
    if segment.empty:
        return _unavailable_event("얼리 코킹 탐색 구간에 프레임이 없습니다.")

    side_sign = _throwing_side_sign(table, shoulder=shoulder, elbow=elbow)
    lateral_offset = (
        _numeric(segment[f"{elbow}_body_x"]) - _numeric(segment[f"{shoulder}_body_x"])
    ) * side_sign
    confidence = _joint_confidence(segment, shoulder=shoulder, elbow=elbow)
    return _choose_event(
        segment=segment,
        metric=lateral_offset,
        confidence=confidence,
        search_start_frame=start_frame,
        search_end_frame=end_frame,
        metric_name="throwing_elbow_lateral_offset_from_shoulder",
        unavailable_reason="confidence가 충분한 얼리 코킹 후보가 없습니다.",
    )


def _detect_late_cocking(
    table: pd.DataFrame,
    interval: dict[str, Any] | None,
    *,
    shoulder: str,
    elbow: str,
) -> dict[str, Any]:
    if interval is None:
        return _unavailable_event("가속 구간이 없어 레이트 코킹 proxy를 계산하지 못했습니다.")

    start_frame = float(interval["startFrame"])
    end_frame = max(start_frame, float(interval["endFrame"]) - 1.0)
    segment = _segment(table, start_frame, end_frame)
    if segment.empty:
        return _unavailable_event("레이트 코킹 탐색 구간에 프레임이 없습니다.")

    elbow_x = _numeric(segment[f"{elbow}_body_x"])
    elbow_y = _numeric(segment[f"{elbow}_body_y"])
    shoulder_x = _numeric(segment[f"{shoulder}_body_x"])
    shoulder_y = _numeric(segment[f"{shoulder}_body_y"])
    elbow_shoulder_distance = pd.Series(
        np.hypot(elbow_x - shoulder_x, elbow_y - shoulder_y),
        index=segment.index,
    )
    confidence = _joint_confidence(segment, shoulder=shoulder, elbow=elbow)
    elbow_height_delta = elbow_y - shoulder_y
    height_filtered_confidence = confidence.where(elbow_height_delta >= MIN_LATE_ELBOW_HEIGHT_DELTA, 0.0)
    if (height_filtered_confidence >= MIN_CONFIDENCE).any():
        confidence = height_filtered_confidence

    event = _choose_event(
        segment=segment,
        metric=elbow_shoulder_distance,
        confidence=confidence,
        search_start_frame=start_frame,
        search_end_frame=end_frame,
        metric_name="throwing_elbow_shoulder_distance",
        unavailable_reason="confidence가 충분한 레이트 코킹 후보가 없습니다.",
    )
    event["elbowHeightFilter"] = {
        "applied": bool((height_filtered_confidence >= MIN_CONFIDENCE).any()),
        "minimumElbowMinusShoulderBodyY": MIN_LATE_ELBOW_HEIGHT_DELTA,
    }
    return event


def _choose_event(
    *,
    segment: pd.DataFrame,
    metric: pd.Series,
    confidence: pd.Series,
    search_start_frame: float,
    search_end_frame: float,
    metric_name: str,
    unavailable_reason: str,
) -> dict[str, Any]:
    usable_metric = metric.where(confidence >= MIN_CONFIDENCE).replace([np.inf, -np.inf], np.nan).dropna()
    if usable_metric.empty:
        return _unavailable_event(unavailable_reason)

    row_index = int(usable_metric.idxmax())
    return {
        "status": "ready",
        "frame": _frame_value(segment.loc[row_index, "frame_index"]),
        "searchStartFrame": _frame_value(search_start_frame),
        "searchEndFrame": _frame_value(search_end_frame),
        "metricName": metric_name,
        "metricValue": round(float(metric.loc[row_index]), 6),
        "confidence": round(float(confidence.loc[row_index]), 6),
    }


def _segment(table: pd.DataFrame, start_frame: float, end_frame: float) -> pd.DataFrame:
    frame_values = pd.to_numeric(table["frame_index"], errors="coerce")
    frame_floor = math.floor(min(start_frame, end_frame))
    frame_ceil = math.ceil(max(start_frame, end_frame))
    return table[(frame_values >= frame_floor) & (frame_values <= frame_ceil)].sort_values("frame_index")


def _throwing_side_sign(table: pd.DataFrame, *, shoulder: str, elbow: str) -> float:
    side_offsets = _numeric(table[f"{elbow}_body_x"]) - _numeric(table[f"{shoulder}_body_x"])
    valid_offsets = side_offsets.replace([np.inf, -np.inf], np.nan).dropna()
    if valid_offsets.empty:
        return 1.0
    return 1.0 if float(valid_offsets.median()) >= 0 else -1.0


def _joint_confidence(segment: pd.DataFrame, *, shoulder: str, elbow: str) -> pd.Series:
    shoulder_confidence = _numeric(segment[f"{shoulder}_confidence"], fallback=0.0)
    elbow_confidence = _numeric(segment[f"{elbow}_confidence"], fallback=0.0)
    return pd.Series(np.sqrt(shoulder_confidence * elbow_confidence), index=segment.index).fillna(0.0)


def _numeric(values: Any, fallback: float | None = None) -> pd.Series:
    series = pd.to_numeric(values, errors="coerce").interpolate(limit_direction="both")
    if fallback is not None:
        series = series.fillna(fallback)
    return series


def _frame_value(value: Any) -> int | float:
    parsed = float(value)
    if math.isclose(parsed, round(parsed)):
        return int(round(parsed))
    return round(parsed, 4)


def _unavailable(reason: str) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "method": "2d_elbow_based_cocking_proxy_v1",
        "reason": reason,
        "earlyCocking": _unavailable_event(reason),
        "lateCocking": _unavailable_event(reason),
    }


def _unavailable_event(reason: str) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "frame": None,
        "reason": reason,
    }
