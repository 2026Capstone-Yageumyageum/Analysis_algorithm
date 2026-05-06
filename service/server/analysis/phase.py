from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class PhaseDetection:
    representative_frames: dict[str, int | None]
    intervals: dict[str, dict[str, int | str]]
    warnings: list[str]


def detect_pitch_phases(normalized_pose: pd.DataFrame) -> PhaseDetection:
    """Detect rear-view pitching phases from normalized body-frame keypoints."""
    warnings: list[str] = []
    if normalized_pose.empty:
        return PhaseDetection(
            representative_frames=_empty_representatives(),
            intervals={},
            warnings=["정규화된 keypoints가 없어 phase를 탐지하지 못했습니다."],
        )

    frame_count = len(normalized_pose)
    indices = np.arange(frame_count)
    throwing_side = str(normalized_pose["throwing_side"].iloc[0] if "throwing_side" in normalized_pose else "right")
    stride_side = "left" if throwing_side == "right" else "right"
    throwing_wrist = f"{throwing_side}_wrist"
    throwing_elbow = f"{throwing_side}_elbow"
    stride_knee = f"{stride_side}_knee"
    stride_foot = f"{stride_side}_foot_index"

    setup_limit = max(1, int(frame_count * 0.16))
    setup_candidates = indices[:setup_limit]
    setup_score = _series(normalized_pose, f"{throwing_wrist}_speed_body").iloc[setup_candidates]
    setup_idx = _choose(setup_candidates, setup_score, mode="min", fallback=0)

    leg_lift_end = max(setup_idx + 1, int(frame_count * 0.68))
    leg_lift_candidates = indices[setup_idx:leg_lift_end]
    baseline_knee_y = _value_at(normalized_pose, f"{stride_knee}_body_y", setup_idx)
    knee_lift = (baseline_knee_y - _series(normalized_pose, f"{stride_knee}_body_y").iloc[leg_lift_candidates]).clip(lower=0.0)
    knee_motion = _series(normalized_pose, f"{stride_knee}_speed_body").iloc[leg_lift_candidates]
    leg_lift_score = (0.72 * _normalize(knee_lift)) + (0.28 * _normalize(knee_motion))
    leg_lift_idx = _choose(leg_lift_candidates, leg_lift_score, mode="max", fallback=setup_idx)

    release_start = max(setup_idx, leg_lift_idx)
    release_end = max(release_start + 1, int(frame_count * 0.95))
    release_candidates = indices[release_start:release_end]
    wrist_speed = _series(normalized_pose, f"{throwing_wrist}_speed_body").iloc[release_candidates]
    elbow_speed = _series(normalized_pose, f"{throwing_elbow}_speed_body").iloc[release_candidates]
    release_score = (0.78 * _normalize(wrist_speed)) + (0.22 * _normalize(elbow_speed))
    release_idx = _choose(release_candidates, release_score, mode="max", fallback=leg_lift_idx)

    stride_candidates = indices[leg_lift_idx : max(leg_lift_idx + 1, release_idx + 1)]
    stride_distance = _point_distance_from_pelvis(normalized_pose, stride_foot).iloc[stride_candidates]
    stride_speed = _series(normalized_pose, f"{stride_foot}_speed_body").iloc[stride_candidates]
    stride_score = (0.70 * _normalize(stride_distance)) + (0.30 * (1.0 - _normalize(stride_speed)))
    stride_idx = _choose(stride_candidates, stride_score, mode="max", fallback=int((leg_lift_idx + release_idx) / 2))

    minimum_release_gap = max(2, int(frame_count * 0.025))
    if release_idx - stride_idx < minimum_release_gap:
        release_idx = min(frame_count - 1, stride_idx + minimum_release_gap)
        warnings.append("릴리즈 구간이 너무 짧아 최소 길이 기준으로 확장했습니다.")

    follow_candidates = indices[min(frame_count - 1, release_idx + 1) :]
    follow_score = (
        _normalize(_series(normalized_pose, f"{throwing_wrist}_speed_body").iloc[follow_candidates])
        + _normalize(_point_distance_from_pelvis(normalized_pose, throwing_wrist).iloc[follow_candidates])
    )
    follow_idx = _choose(
        follow_candidates,
        follow_score,
        mode="max",
        fallback=min(frame_count - 1, release_idx + max(1, int(frame_count * 0.12))),
    )

    representatives = {
        "setup": int(_frame_at(normalized_pose, setup_idx)),
        "leg_lift": int(_frame_at(normalized_pose, leg_lift_idx)),
        "stride": int(_frame_at(normalized_pose, stride_idx)),
        "release": int(_frame_at(normalized_pose, release_idx)),
        "follow_through": int(_frame_at(normalized_pose, follow_idx)),
    }
    intervals = _build_intervals(representatives, last_frame=int(_frame_at(normalized_pose, frame_count - 1)))
    return PhaseDetection(representative_frames=representatives, intervals=intervals, warnings=warnings)


def _build_intervals(representatives: dict[str, int | None], last_frame: int) -> dict[str, dict[str, int | str]]:
    setup = int(representatives.get("setup") or 0)
    leg_lift = int(representatives.get("leg_lift") or setup)
    stride = int(representatives.get("stride") or leg_lift)
    release = int(representatives.get("release") or stride)
    follow = int(representatives.get("follow_through") or last_frame)
    return {
        "leg_lift": {"phase": "leg_lift", "label": "레그 리프트", "startFrame": setup, "endFrame": max(setup, leg_lift)},
        "stride": {"phase": "stride", "label": "스트라이드", "startFrame": leg_lift, "endFrame": max(leg_lift, stride)},
        "release": {"phase": "release", "label": "릴리즈", "startFrame": stride, "endFrame": max(stride, release)},
        "follow_through": {"phase": "follow_through", "label": "팔로우 스루", "startFrame": release, "endFrame": max(release, follow)},
    }


def _empty_representatives() -> dict[str, int | None]:
    return {"setup": None, "leg_lift": None, "stride": None, "release": None, "follow_through": None}


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

