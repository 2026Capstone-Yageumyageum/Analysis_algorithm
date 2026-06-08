from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd


FrameValue = int | float


@dataclass(frozen=True)
class PhaseDetection:
    representative_frames: dict[str, FrameValue | None]
    intervals: dict[str, dict[str, FrameValue | str]]
    warnings: list[str]
    events: dict[str, dict[str, Any]] = field(default_factory=dict)


def detect_pitch_phases(
    normalized_pose: pd.DataFrame,
    *,
    release_event_override: dict[str, Any] | None = None,
) -> PhaseDetection:
    """Detect rear-view pitching phases from normalized body-frame keypoints."""
    warnings: list[str] = []
    if normalized_pose.empty:
        return PhaseDetection(
            representative_frames=_empty_representatives(),
            intervals={},
            warnings=["정규화된 keypoints가 없어 phase를 탐지하지 못했습니다."],
        )

    frame_count = len(normalized_pose)
    first_valid_idx, last_valid_idx = _valid_pose_span(normalized_pose)
    active_frame_count = max(1, last_valid_idx - first_valid_idx + 1)
    if first_valid_idx > 0 or last_valid_idx < frame_count - 1:
        warnings.append("confidence가 낮은 앞/뒤 프레임을 제외하고 phase를 탐지했습니다.")
    throwing_side = str(normalized_pose["throwing_side"].iloc[0] if "throwing_side" in normalized_pose else "right")
    stride_side = "left" if throwing_side == "right" else "right"
    throwing_wrist = f"{throwing_side}_wrist"
    throwing_elbow = f"{throwing_side}_elbow"
    stride_knee = f"{stride_side}_knee"
    stride_foot = f"{stride_side}_foot_index"

    setup_limit = min(last_valid_idx + 1, first_valid_idx + max(1, int(active_frame_count * 0.16)))
    setup_candidates = np.arange(first_valid_idx, setup_limit)
    setup_score = _series(normalized_pose, f"{throwing_wrist}_speed_body").iloc[setup_candidates]
    setup_idx = _choose(setup_candidates, setup_score, mode="min", fallback=first_valid_idx)

    leg_lift_end = min(last_valid_idx + 1, max(setup_idx + 1, first_valid_idx + int(active_frame_count * 0.68)))
    leg_lift_candidates = np.arange(setup_idx, leg_lift_end)
    leg_lift_idx = _choose_highest_joint(
        normalized_pose,
        leg_lift_candidates,
        stride_knee,
        fallback=setup_idx,
    )

    minimum_phase_gap = max(3, int(active_frame_count * 0.025))
    minimum_stride_gap = max(minimum_phase_gap, int(active_frame_count * 0.07))
    stride_search_end = min(last_valid_idx + 1, max(leg_lift_idx + 1, first_valid_idx + int(active_frame_count * 0.90)))
    release_override_idx = _release_override_index(normalized_pose, release_event_override, fallback=last_valid_idx)
    use_release_bounded_stride = release_override_idx is not None and release_override_idx > leg_lift_idx
    if use_release_bounded_stride:
        stride_search_end = min(stride_search_end, max(leg_lift_idx + 1, release_override_idx + 1))
    stride_candidates = np.arange(leg_lift_idx, stride_search_end)
    stride_idx = _choose_stride_foot_landing(
        normalized_pose,
        stride_candidates,
        stride_foot,
        fallback=min(last_valid_idx, leg_lift_idx + max(minimum_stride_gap, int(active_frame_count * 0.20))),
        prefer_release_bounded_landing=use_release_bounded_stride,
    )

    stride_was_expanded = False
    stride_expansion_warning = "스트라이드 구간이 너무 짧아 최소 길이 기준으로 확장했습니다."
    if stride_idx - leg_lift_idx < minimum_stride_gap and last_valid_idx > leg_lift_idx:
        stride_idx = min(last_valid_idx, leg_lift_idx + minimum_stride_gap)
        stride_was_expanded = True
        warnings.append(stride_expansion_warning)

    release_search_gap = 1
    release_start = min(last_valid_idx, max(stride_idx + release_search_gap, leg_lift_idx + minimum_phase_gap))
    release_end = min(last_valid_idx + 1, max(release_start + 1, first_valid_idx + int(active_frame_count * 0.98)))
    release_candidates = np.arange(release_start, release_end)
    wrist_speed = _series(normalized_pose, f"{throwing_wrist}_speed_body").iloc[release_candidates]
    elbow_speed = _series(normalized_pose, f"{throwing_elbow}_speed_body").iloc[release_candidates]
    release_score = (0.78 * _normalize(wrist_speed)) + (0.22 * _normalize(elbow_speed))
    release_idx = _choose(release_candidates, release_score, mode="max", fallback=min(last_valid_idx, stride_idx + minimum_phase_gap))

    release_event = _build_release_event(
        normalized_pose,
        release_idx=release_idx,
        first_valid_idx=first_valid_idx,
        override=release_event_override,
    )
    if release_event.get("status") == "fallback":
        warnings.append("공 탐지에 실패해 릴리즈는 손목 기반 proxy midpoint를 사용합니다.")
    override_exit_frame = _optional_frame_value(_first_present(release_event, "exitFrame", "frame"))
    if release_event_override is not None and override_exit_frame is not None:
        release_idx = _index_at_or_before_frame(
            normalized_pose,
            float(override_exit_frame),
            fallback=release_idx,
        )

    follow_candidates = np.arange(min(last_valid_idx, release_idx + 1), last_valid_idx + 1)
    follow_score = (
        _normalize(_series(normalized_pose, f"{throwing_wrist}_speed_body").iloc[follow_candidates])
        + _normalize(_point_distance_from_pelvis(normalized_pose, throwing_wrist).iloc[follow_candidates])
    )
    follow_idx = _choose(
        follow_candidates,
        follow_score,
        mode="max",
        fallback=min(last_valid_idx, release_idx + max(1, int(active_frame_count * 0.12))),
    )
    minimum_follow_gap = max(3, int(active_frame_count * 0.03))
    if follow_idx - release_idx < minimum_follow_gap:
        follow_idx = min(last_valid_idx, release_idx + minimum_follow_gap)
        warnings.append("팔로스루 구간이 너무 짧아 최소 길이 기준으로 확장했습니다.")

    representatives = {
        "setup": int(_frame_at(normalized_pose, setup_idx)),
        "leg_lift": int(_frame_at(normalized_pose, leg_lift_idx)),
        "stride": int(_frame_at(normalized_pose, stride_idx)),
        "release": _frame_value(release_event["frame"]),
        "follow_through": int(_frame_at(normalized_pose, follow_idx)),
    }
    intervals = _build_intervals(
        representatives,
        first_frame=int(_frame_at(normalized_pose, first_valid_idx)),
        last_frame=int(_frame_at(normalized_pose, last_valid_idx)),
    )
    return PhaseDetection(
        representative_frames=representatives,
        intervals=intervals,
        warnings=warnings,
        events={"release": release_event},
    )


def _build_intervals(
    representatives: dict[str, FrameValue | None],
    first_frame: int,
    last_frame: int,
) -> dict[str, dict[str, FrameValue | str]]:
    start = int(first_frame)
    setup = _frame_value(representatives.get("setup") or start)
    leg_lift = _frame_value(representatives.get("leg_lift") or setup)
    stride = _frame_value(representatives.get("stride") or leg_lift)
    release = _frame_value(representatives.get("release") or stride)
    follow = _frame_value(representatives.get("follow_through") or last_frame)
    minimum_windup_span = max(1, int((int(last_frame) - start) * 0.06))
    if setup - start < minimum_windup_span and leg_lift > start:
        leg_lift_span = max(1, leg_lift - start)
        fallback_span = min(minimum_windup_span, max(1, int(leg_lift_span * 0.35)))
        setup = min(leg_lift - 1, max(setup, start + fallback_span))
    return {
        "windup": {"phase": "windup", "label": "와인드업", "startFrame": start, "endFrame": max(start, setup)},
        "leg_lift": {"phase": "leg_lift", "label": "레그 리프트", "startFrame": setup, "endFrame": max(setup, leg_lift)},
        "stride": {"phase": "stride", "label": "스트라이드", "startFrame": leg_lift, "endFrame": max(leg_lift, stride)},
        "acceleration": {"phase": "acceleration", "label": "가속", "startFrame": stride, "endFrame": max(stride, release)},
        "follow_through": {"phase": "follow_through", "label": "팔로스루", "startFrame": release, "endFrame": max(release, follow)},
    }


def _build_release_event(
    df: pd.DataFrame,
    *,
    release_idx: int,
    first_valid_idx: int,
    override: dict[str, Any] | None,
) -> dict[str, Any]:
    before_idx = max(first_valid_idx, release_idx - 1)
    fallback_before_frame = _frame_value(_frame_at(df, before_idx))
    fallback_exit_frame = _frame_value(_frame_at(df, release_idx))

    if override:
        before_frame = _optional_frame_value(
            _first_present(
                override,
                "beforeFrame",
                "preReleaseFrame",
                "lastAttachedFrame",
                "lastBallInHandFrame",
            )
        )
        exit_frame = _optional_frame_value(
            _first_present(
                override,
                "exitFrame",
                "afterFrame",
                "firstDetachedFrame",
                "firstBallOutFrame",
            )
        )
        if before_frame is not None and exit_frame is not None and before_frame <= exit_frame:
            release_frame = _optional_frame_value(override.get("releaseFrame"))
            if release_frame is None:
                release_frame = (before_frame + exit_frame) / 2.0
            return {
                "frame": _frame_value(release_frame),
                "beforeFrame": _frame_value(before_frame),
                "exitFrame": _frame_value(exit_frame),
                "method": str(override.get("method") or "ball_exit_midpoint_v1"),
                "status": "ready",
                "source": str(override.get("source") or "ball_tracking"),
                "subFrameCorrection": {
                    "applied": bool(override.get("subFrameCorrected") or False),
                    "plannedMethod": "wrist_ball_distance_threshold_crossing",
                },
            }

    return {
        "frame": _frame_value((fallback_before_frame + fallback_exit_frame) / 2.0),
        "beforeFrame": fallback_before_frame,
        "exitFrame": fallback_exit_frame,
        "method": "pose_proxy_midpoint_v1",
        "status": "fallback",
        "source": "throwing_wrist_speed_body",
        "subFrameCorrection": {
            "applied": False,
            "plannedMethod": "wrist_ball_distance_threshold_crossing",
        },
    }


def _fallback_between(start_idx: int, end_idx: int, minimum_gap: int, frame_count: int) -> int:
    """Choose a stable interior boundary when a detected phase collapses."""
    if end_idx <= start_idx:
        return min(frame_count - 1, start_idx + minimum_gap)
    midpoint = start_idx + max(1, int((end_idx - start_idx) * 0.5))
    expanded = start_idx + minimum_gap
    fallback = max(midpoint, expanded)
    if fallback >= end_idx:
        fallback = max(start_idx + 1, end_idx - max(1, minimum_gap // 2))
    return max(0, min(frame_count - 1, fallback))


def _valid_pose_span(df: pd.DataFrame) -> tuple[int, int]:
    confidence_columns = [
        column
        for column in (
            "left_shoulder_confidence",
            "right_shoulder_confidence",
            "left_hip_confidence",
            "right_hip_confidence",
            "left_knee_confidence",
            "right_knee_confidence",
        )
        if column in df.columns
    ]
    if not confidence_columns:
        return 0, len(df) - 1
    confidence = df[confidence_columns].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    valid_mask = confidence.mean(axis=1) >= 0.05
    valid_indices = np.flatnonzero(valid_mask.to_numpy())
    if len(valid_indices) == 0:
        return 0, len(df) - 1
    return int(valid_indices[0]), int(valid_indices[-1])


def _choose_highest_joint(df: pd.DataFrame, candidate_indices: np.ndarray, joint: str, fallback: int) -> int:
    candidates = _confident_candidates(df, candidate_indices, joint)
    if len(candidates) == 0:
        return int(fallback)
    image_y = _joint_image_y(df, joint).iloc[candidates]
    return _choose(candidates, image_y, mode="min", fallback=fallback)


def _choose_stride_foot_landing(
    df: pd.DataFrame,
    candidate_indices: np.ndarray,
    joint: str,
    fallback: int,
    *,
    prefer_release_bounded_landing: bool = False,
) -> int:
    candidates = _confident_candidates(df, candidate_indices, joint)
    if len(candidates) == 0:
        return int(fallback)

    foot_y_series = _joint_image_y(df, joint).astype(float).rolling(window=5, center=True, min_periods=1).median()
    foot_y = foot_y_series.iloc[candidates]
    if prefer_release_bounded_landing:
        return _choose(candidates, foot_y, mode="max", fallback=fallback)

    valid_y = foot_y.replace([np.inf, -np.inf], np.nan).dropna()
    if valid_y.empty:
        return int(fallback)

    # Foot contact should be the first settled landing point, not the latest
    # frame where the stride foot happens to be lowest during acceleration.
    start_y = float(valid_y.iloc[0])
    landing_y = float(valid_y.max())
    descent_range = landing_y - start_y
    if descent_range <= 0.015:
        return _choose(candidates, foot_y, mode="max", fallback=fallback)

    landing_threshold = start_y + (descent_range * 0.86)
    velocity = foot_y_series.diff().rolling(window=5, center=True, min_periods=1).median().abs().iloc[candidates]
    valid_velocity = velocity.replace([np.inf, -np.inf], np.nan).dropna()
    velocity_threshold = 0.008
    if not valid_velocity.empty:
        velocity_threshold = max(0.006, min(0.018, float(valid_velocity.quantile(0.35)) * 1.35))

    candidate_array = np.asarray(candidates)
    y_values = foot_y.to_numpy(dtype=float)
    velocity_values = velocity.to_numpy(dtype=float)
    settled = candidate_array[
        np.isfinite(y_values)
        & np.isfinite(velocity_values)
        & (y_values >= landing_threshold)
        & (velocity_values <= velocity_threshold)
    ]
    if len(settled):
        return int(settled[0])

    landed = candidate_array[np.isfinite(y_values) & (y_values >= landing_threshold)]
    if len(landed):
        return int(landed[0])

    return _choose(candidates, foot_y, mode="max", fallback=fallback)


def _release_override_index(df: pd.DataFrame, override: dict[str, Any] | None, fallback: int) -> int | None:
    if override is None:
        return None
    release_frame = _optional_frame_value(
        _first_present(
            override,
            "releaseFrame",
            "frame",
            "exitFrame",
            "afterFrame",
            "firstDetachedFrame",
            "firstBallOutFrame",
        )
    )
    if release_frame is None:
        return None
    return _index_at_or_before_frame(df, float(release_frame), fallback=fallback)


def _choose_highest_release_wrist(df: pd.DataFrame, candidate_indices: np.ndarray, joint: str, fallback: int) -> int:
    candidates = _confident_candidates(df, candidate_indices, joint)
    if len(candidates) == 0:
        return int(fallback)

    wrist_y = _joint_image_y(df, joint).astype(float).rolling(window=5, center=True, min_periods=1).median().iloc[candidates]
    valid_y = wrist_y.replace([np.inf, -np.inf], np.nan).dropna()
    if valid_y.empty:
        return int(fallback)

    height_tolerance = 0.025
    highest_y = float(valid_y.min())
    candidate_array = np.asarray(candidates)
    near_highest = candidate_array[wrist_y.to_numpy(dtype=float) <= highest_y + height_tolerance]
    if len(near_highest):
        return int(near_highest[0])
    return _choose(candidates, wrist_y, mode="min", fallback=fallback)


def _confident_candidates(df: pd.DataFrame, candidate_indices: np.ndarray, joint: str) -> np.ndarray:
    if len(candidate_indices) == 0:
        return candidate_indices
    confidence_column = f"{joint}_confidence"
    if confidence_column not in df.columns:
        return candidate_indices
    confidence = pd.to_numeric(df[confidence_column], errors="coerce").fillna(0.0).iloc[candidate_indices]
    filtered = candidate_indices[confidence.to_numpy(dtype=float) >= 0.05]
    return filtered if len(filtered) else candidate_indices


def _joint_image_y(df: pd.DataFrame, joint: str) -> pd.Series:
    image_column = f"{joint}_image_y"
    if image_column in df.columns:
        return _series(df, image_column)
    return _series(df, f"{joint}_body_y")


def _empty_representatives() -> dict[str, int | None]:
    return {"setup": None, "leg_lift": None, "stride": None, "release": None, "follow_through": None}


def _optional_frame_value(value: Any) -> FrameValue | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(parsed):
        return None
    return _frame_value(parsed)


def _index_at_or_before_frame(df: pd.DataFrame, frame_value: float, fallback: int) -> int:
    if "frame_index" not in df.columns:
        return int(fallback)
    frames = pd.to_numeric(df["frame_index"], errors="coerce")
    candidates = frames[frames <= frame_value].dropna()
    if candidates.empty:
        return int(fallback)
    return int(candidates.index[-1])


def _first_present(values: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in values and values[key] is not None:
            return values[key]
    return None


def _frame_value(value: Any) -> FrameValue:
    parsed = float(value)
    if np.isclose(parsed, round(parsed)):
        return int(round(parsed))
    return round(parsed, 4)


def _series(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series(np.zeros(len(df)), index=df.index, dtype=float)
    return pd.to_numeric(df[column], errors="coerce").interpolate(limit_direction="both").fillna(0.0)


def _normalize(series: pd.Series) -> pd.Series:
    if series.empty:
        return series
    valid = series.replace([np.inf, -np.inf], np.nan).dropna()
    if valid.empty:
        return pd.Series(np.zeros(len(series)), index=series.index, dtype=float)
    min_value = float(valid.min())
    max_value = float(valid.max())
    if np.isclose(min_value, max_value):
        return pd.Series(np.zeros(len(series)), index=series.index, dtype=float)
    return ((series - min_value) / (max_value - min_value)).fillna(0.0)


def _choose(candidate_indices: np.ndarray, values: pd.Series, mode: str, fallback: int) -> int:
    if len(candidate_indices) == 0 or values.empty:
        return int(fallback)
    numeric = values.to_numpy(dtype=float)
    if not np.isfinite(numeric).any():
        return int(fallback)
    offset = int(np.nanargmax(numeric)) if mode == "max" else int(np.nanargmin(numeric))
    return int(candidate_indices[min(offset, len(candidate_indices) - 1)])


def _point_distance_from_pelvis(df: pd.DataFrame, joint: str) -> pd.Series:
    x = _series(df, f"{joint}_body_x")
    y = _series(df, f"{joint}_body_y")
    return pd.Series(np.sqrt((x**2) + (y**2)), index=df.index)


def _frame_at(df: pd.DataFrame, row_index: int) -> int:
    row_index = max(0, min(len(df) - 1, row_index))
    return int(df.iloc[row_index]["frame_index"])


def _value_at(df: pd.DataFrame, column: str, row_index: int) -> float:
    if column not in df.columns:
        return 0.0
    row_index = max(0, min(len(df) - 1, row_index))
    value = pd.to_numeric(df[column], errors="coerce").iloc[row_index]
    return 0.0 if pd.isna(value) else float(value)
