from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class PhaseDetectionResult:
    representative_frames: dict[str, int | None]
    estimated_release_frame: int | None
    warnings: list[str]


def detect_pitching_phases(
    keypoints_df: pd.DataFrame,
    features_df: pd.DataFrame,
    metadata: dict[str, Any],
) -> PhaseDetectionResult:
    warnings: list[str] = []
    frame_count = len(features_df)
    if frame_count == 0:
        warnings.append("No frames available for phase detection.")
        return PhaseDetectionResult(
            representative_frames={"setup": None, "leg_lift": None, "stride": None, "release": None, "follow_through": None},
            estimated_release_frame=None,
            warnings=warnings,
        )

    all_indices = np.arange(frame_count)
    early_end = max(1, int(frame_count * 0.15))
    setup_candidates = all_indices[:early_end]
    setup_score = (
        normalize_series(features_df["throwing_wrist_speed"].iloc[setup_candidates])
        + normalize_series(features_df["pelvis_speed"].iloc[setup_candidates])
        + 0.25 * normalize_series(features_df["body_trunk_tilt_deg"].iloc[setup_candidates].abs())
    )
    setup_idx = choose_candidate(setup_candidates, setup_score, mode="min", fallback=0)

    stride_side = str(metadata.get("stride_side") or "").lower()
    stride_knee_angle_col = f"{stride_side}_knee_angle_deg" if stride_side in {"left", "right"} else ""
    stride_knee_y_col = f"{stride_side}_knee_y_smooth" if stride_side in {"left", "right"} else ""

    leg_lift_candidates = all_indices[setup_idx : max(setup_idx + 1, int(frame_count * 0.65))]
    leg_lift_height_score = pd.Series(np.zeros(len(leg_lift_candidates), dtype=float), index=leg_lift_candidates)
    if stride_knee_y_col and stride_knee_y_col in keypoints_df.columns:
        baseline_stride_knee_y = keypoints_df.iloc[setup_idx][stride_knee_y_col]
        if pd.notna(baseline_stride_knee_y):
            stride_knee_y = keypoints_df[stride_knee_y_col].iloc[leg_lift_candidates]
            leg_lift_height_score = (baseline_stride_knee_y - stride_knee_y).clip(lower=0.0).fillna(0.0)
    if leg_lift_height_score.eq(0.0).all():
        raw_stride_lift = features_df["stride_knee_lift"].iloc[leg_lift_candidates].fillna(0.0)
        leg_lift_height_score = raw_stride_lift - float(raw_stride_lift.min())

    leg_lift_angle_score = pd.Series(np.zeros(len(leg_lift_candidates), dtype=float), index=leg_lift_candidates)
    if stride_knee_angle_col and stride_knee_angle_col in features_df.columns:
        stride_knee_angle = features_df[stride_knee_angle_col].iloc[leg_lift_candidates]
        leg_lift_angle_score = (180.0 - stride_knee_angle).clip(lower=0.0).fillna(0.0)
    leg_lift_score = (0.6 * normalize_series(leg_lift_height_score)) + (0.4 * normalize_series(leg_lift_angle_score))
    leg_lift_idx = choose_candidate(leg_lift_candidates, leg_lift_score, mode="max", fallback=setup_idx)

    release_search_start = min(leg_lift_idx, frame_count - 1)
    release_search_end = max(release_search_start + 1, int(frame_count * 0.95))
    release_candidates = all_indices[release_search_start:release_search_end]
    release_idx = choose_candidate(
        release_candidates,
        features_df["throwing_wrist_speed"].iloc[release_candidates],
        mode="max",
        fallback=leg_lift_idx,
    )

    stride_candidates = all_indices[leg_lift_idx : max(leg_lift_idx + 1, release_idx + 1)]
    stride_idx = detect_foot_contact_index(
        candidate_indices=stride_candidates,
        stride_foot_extension=features_df["stride_foot_extension"].iloc[stride_candidates],
        stride_ankle_y=features_df["stride_ankle_y"].iloc[stride_candidates],
        stride_foot_speed=features_df["stride_foot_speed"].iloc[stride_candidates],
        fallback=int((leg_lift_idx + release_idx) / 2),
    )

    follow_start = min(frame_count - 1, release_idx + 1)
    follow_candidates = all_indices[follow_start:]
    follow_score = (
        normalize_series(features_df["body_trunk_tilt_deg"].iloc[follow_candidates].abs())
        + normalize_series(features_df["pelvis_speed"].iloc[follow_candidates])
        + 0.25 * normalize_series(features_df["throwing_arm_orientation_deg"].iloc[follow_candidates].abs())
    )
    follow_idx = choose_candidate(
        follow_candidates,
        follow_score,
        mode="max",
        fallback=min(frame_count - 1, release_idx + max(1, int(frame_count * 0.1))),
    )

    stride_idx = min(max(stride_idx, leg_lift_idx), release_idx)
    release_idx = max(release_idx, stride_idx)
    follow_idx = max(follow_idx, min(frame_count - 1, release_idx + 1))

    if release_idx == leg_lift_idx:
        warnings.append("Release frame overlapped with leg_lift heuristic; review this video manually.")
    if stride_idx == leg_lift_idx:
        warnings.append("Foot contact heuristic fell back close to leg_lift; review stride-foot visibility.")

    representative_frames = {
        "setup": int(setup_idx),
        "leg_lift": int(leg_lift_idx),
        "stride": int(stride_idx),
        "release": int(release_idx),
        "follow_through": int(follow_idx),
    }
    return PhaseDetectionResult(representative_frames=representative_frames, estimated_release_frame=int(release_idx), warnings=warnings)


def normalize_series(series: pd.Series) -> pd.Series:
    if series.empty:
        return series
    valid = series.dropna()
    if valid.empty:
        return pd.Series(np.zeros(len(series), dtype=float), index=series.index)
    min_value = valid.min()
    max_value = valid.max()
    if np.isclose(min_value, max_value):
        return pd.Series(np.zeros(len(series), dtype=float), index=series.index)
    return ((series - min_value) / (max_value - min_value)).fillna(0.0)


def choose_candidate(candidate_indices: np.ndarray, values: pd.Series, mode: str, fallback: int) -> int:
    if len(candidate_indices) == 0 or values.empty:
        return int(fallback)
    numeric_values = values.to_numpy(dtype=float)
    if np.all(np.isnan(numeric_values)):
        return int(fallback)
    offset = int(np.nanargmax(numeric_values)) if mode == "max" else int(np.nanargmin(numeric_values))
    return int(candidate_indices[offset])


def detect_foot_contact_index(
    candidate_indices: np.ndarray,
    stride_foot_extension: pd.Series,
    stride_ankle_y: pd.Series,
    stride_foot_speed: pd.Series,
    fallback: int,
) -> int:
    if len(candidate_indices) == 0:
        return int(fallback)
    extension_score = normalize_series(stride_foot_extension.ffill().bfill().fillna(0.0))
    ground_score = normalize_series(stride_ankle_y.ffill().bfill().fillna(0.0))
    speed_score = normalize_series(stride_foot_speed.ffill().bfill().fillna(0.0))

    extension_values = extension_score.to_numpy(dtype=float)
    ground_values = ground_score.to_numpy(dtype=float)
    speed_values = speed_score.to_numpy(dtype=float)
    contact_score = (0.45 * extension_values) + (0.35 * ground_values) + (0.20 * (1.0 - speed_values))
    if not np.isfinite(contact_score).any():
        return int(fallback)

    peak_speed_offset = int(np.nanargmax(speed_values)) if np.isfinite(speed_values).any() else 0
    score_threshold = max(0.68, float(np.nanmax(contact_score)) * 0.82)
    trigger_mask = (
        (np.arange(len(candidate_indices)) >= peak_speed_offset)
        & (contact_score >= score_threshold)
        & (extension_values >= 0.55)
        & (ground_values >= 0.55)
        & (speed_values <= 0.70)
    )
    if trigger_mask.any():
        return int(candidate_indices[int(np.argmax(trigger_mask))])
    return int(candidate_indices[int(np.nanargmax(contact_score))])
