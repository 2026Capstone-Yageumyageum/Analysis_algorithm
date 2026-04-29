from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from analysis_algorithm.schema import PHASE_ORDER


DTW_FEATURE_CANDIDATES = (
    "body_trunk_tilt_canonical_deg",
    "shoulder_tilt_canonical_deg",
    "pelvis_tilt_canonical_deg",
    "throwing_elbow_angle_deg",
    "throwing_arm_orientation_canonical_deg",
    "lead_knee_angle_deg",
    "trail_knee_angle_deg",
    "throwing_wrist_forward_body",
    "throwing_wrist_lateral_body",
    "stride_foot_forward_body",
    "stride_foot_lateral_body",
    "stride_foot_extension_body_scale",
    "stride_knee_lift_body_scale",
    "throwing_wrist_speed_body_scale_per_sec",
    "pelvis_speed_body_scale_per_sec",
)


def align_feature_sequences(
    left_features_df: pd.DataFrame,
    right_features_df: pd.DataFrame,
    left_phase_frames: dict[str, int | None],
    right_phase_frames: dict[str, int | None],
) -> dict[str, Any]:
    left_df = left_features_df.sort_values("frame_index").reset_index(drop=True)
    right_df = right_features_df.sort_values("frame_index").reset_index(drop=True)
    feature_columns = [column for column in DTW_FEATURE_CANDIDATES if column in left_df.columns and column in right_df.columns]
    if len(feature_columns) < 3:
        return unavailable_alignment(feature_columns, ["DTW needs at least three common normalized feature columns."])

    left_segments = build_phase_segments(left_df, left_phase_frames)
    right_segments = build_phase_segments(right_df, right_phase_frames)
    aligned_pairs: list[list[int]] = []
    phase_alignments: list[dict[str, Any]] = []

    for phase_name in PHASE_ORDER:
        left_segment = left_segments.get(phase_name)
        right_segment = right_segments.get(phase_name)
        if left_segment is None or right_segment is None:
            phase_alignments.append(
                {
                    "phase": phase_name,
                    "status": "missing_segment",
                    "left_frame_count": 0 if left_segment is None else int(len(left_segment)),
                    "right_frame_count": 0 if right_segment is None else int(len(right_segment)),
                    "aligned_pair_count": 0,
                }
            )
            continue

        left_matrix = feature_matrix(left_segment, feature_columns)
        right_matrix = feature_matrix(right_segment, feature_columns)
        if left_matrix is None or right_matrix is None:
            phase_alignments.append(build_phase_info(phase_name, left_segment, right_segment, "insufficient_features", 0))
            continue

        path_indices, band, fallback_used = constrained_dtw_path(left_matrix, right_matrix)
        left_frames = left_segment["frame_index"].astype(int).to_numpy()
        right_frames = right_segment["frame_index"].astype(int).to_numpy()
        if not path_indices:
            info = build_phase_info(phase_name, left_segment, right_segment, "failed", 0)
            info["band"] = int(band)
            info["fallback_used"] = fallback_used
            phase_alignments.append(info)
            continue

        phase_pairs = [[int(left_frames[i]), int(right_frames[j])] for i, j in path_indices]
        if aligned_pairs and phase_pairs and aligned_pairs[-1] == phase_pairs[0]:
            phase_pairs = phase_pairs[1:]
        aligned_pairs.extend(phase_pairs)

        info = build_phase_info(phase_name, left_segment, right_segment, "ready", len(path_indices))
        info["band"] = int(band)
        info["fallback_used"] = fallback_used
        phase_alignments.append(info)

    if not aligned_pairs:
        return unavailable_alignment(feature_columns, ["No phase segment produced a usable DTW alignment."], phase_alignments)

    ready_phase_count = sum(1 for segment in phase_alignments if segment.get("status") == "ready")
    return {
        "status": "ready" if ready_phase_count == len(PHASE_ORDER) else "partial",
        "method": "phase-aware DTW on normalized feature sequences",
        "feature_columns": feature_columns,
        "aligned_pair_count": int(len(aligned_pairs)),
        "phase_alignments": phase_alignments,
        "aligned_pairs": aligned_pairs,
        "notes": [
            "DTW is applied after spatial/body normalization, not on raw pixel coordinates.",
            "Each pitching phase is aligned independently to avoid matching unrelated motion ranges.",
        ],
    }


def unavailable_alignment(
    feature_columns: list[str],
    notes: list[str],
    phase_alignments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "method": "phase-aware DTW on normalized feature sequences",
        "feature_columns": feature_columns,
        "aligned_pair_count": 0,
        "phase_alignments": phase_alignments or [],
        "aligned_pairs": [],
        "notes": notes,
    }


def build_phase_segments(features_df: pd.DataFrame, phase_frames: dict[str, int | None]) -> dict[str, pd.DataFrame]:
    frame_indices = features_df["frame_index"].astype(int).to_numpy()
    if len(frame_indices) == 0:
        return {}

    start_frame = int(frame_indices[0])
    end_frame = int(frame_indices[-1])
    leg_lift = coerce_phase_frame(phase_frames.get("leg_lift"), start_frame, end_frame)
    stride = coerce_phase_frame(phase_frames.get("stride"), leg_lift, end_frame)
    release = coerce_phase_frame(phase_frames.get("release"), stride, end_frame)
    follow_through = coerce_phase_frame(phase_frames.get("follow_through"), release, end_frame)
    boundaries = {
        "setup": (start_frame, leg_lift),
        "leg_lift": (leg_lift, stride),
        "stride": (stride, release),
        "release": (release, follow_through),
        "follow_through": (follow_through, end_frame),
    }

    segments: dict[str, pd.DataFrame] = {}
    for phase_name, (segment_start, segment_end) in boundaries.items():
        segment_df = features_df[(features_df["frame_index"] >= segment_start) & (features_df["frame_index"] <= segment_end)].copy()
        if len(segment_df) >= 2:
            segments[phase_name] = segment_df.reset_index(drop=True)
    return segments


def coerce_phase_frame(value: int | None, minimum: int, maximum: int) -> int:
    if value is None:
        return int(minimum)
    return int(np.clip(int(value), minimum, maximum))


def feature_matrix(segment_df: pd.DataFrame, feature_columns: list[str]) -> np.ndarray | None:
    matrix = segment_df[feature_columns].apply(pd.to_numeric, errors="coerce")
    matrix = matrix.interpolate(limit_direction="both")
    matrix = matrix.fillna(matrix.median(numeric_only=True)).fillna(0.0)
    values = matrix.to_numpy(dtype=float)
    if values.ndim != 2 or values.shape[0] < 2:
        return None
    means = np.nanmean(values, axis=0)
    stds = np.nanstd(values, axis=0)
    stds = np.where(stds < 1e-6, 1.0, stds)
    return (values - means) / stds


def constrained_dtw_path(left_matrix: np.ndarray, right_matrix: np.ndarray) -> tuple[list[tuple[int, int]], int, bool]:
    left_count = left_matrix.shape[0]
    right_count = right_matrix.shape[0]
    if left_count == 0 or right_count == 0:
        return [], 0, False
    max_count = max(left_count, right_count)
    min_count = max(1, min(left_count, right_count))
    gap_ratio = abs(left_count - right_count) / float(max_count)
    band = max(5, int(max_count * max(0.20, gap_ratio + 0.10)))
    path = constrained_dtw_path_with_band(left_matrix, right_matrix, band)
    if path:
        return path, band, False
    relaxed_band = max(5, int(max_count * 0.85))
    relaxed_path = constrained_dtw_path_with_band(left_matrix, right_matrix, relaxed_band)
    if relaxed_path:
        return relaxed_path, relaxed_band, True
    if gap_ratio >= 0.45 or max_count / float(min_count) >= 1.8:
        unconstrained_path = constrained_dtw_path_with_band(left_matrix, right_matrix, max_count)
        if unconstrained_path:
            return unconstrained_path, max_count, True
    return [], band, True


def constrained_dtw_path_with_band(left_matrix: np.ndarray, right_matrix: np.ndarray, band: int) -> list[tuple[int, int]]:
    left_count = left_matrix.shape[0]
    right_count = right_matrix.shape[0]
    cost = np.full((left_count + 1, right_count + 1), np.inf, dtype=float)
    backtrack = np.full((left_count + 1, right_count + 1), -1, dtype=int)
    cost[0, 0] = 0.0

    for i in range(1, left_count + 1):
        for j in range(max(1, i - band), min(right_count, i + band) + 1):
            distance = float(np.linalg.norm(left_matrix[i - 1] - right_matrix[j - 1]))
            candidates = (cost[i - 1, j], cost[i, j - 1], cost[i - 1, j - 1])
            move = int(np.argmin(candidates))
            cost[i, j] = distance + candidates[move]
            backtrack[i, j] = move

    if not np.isfinite(cost[left_count, right_count]):
        return []

    path: list[tuple[int, int]] = []
    i = left_count
    j = right_count
    while i > 0 and j > 0:
        path.append((i - 1, j - 1))
        move = backtrack[i, j]
        if move == 0:
            i -= 1
        elif move == 1:
            j -= 1
        else:
            i -= 1
            j -= 1
    path.reverse()
    return path


def sample_aligned_pairs(aligned_pairs: list[list[int]] | list[tuple[int, int]], max_output_frames: int = 120) -> list[tuple[int, int]]:
    if not aligned_pairs:
        return []
    normalized_pairs = [(int(left), int(right)) for left, right in aligned_pairs]
    if len(normalized_pairs) <= max_output_frames:
        return normalized_pairs
    sample_positions = np.linspace(0, len(normalized_pairs) - 1, max_output_frames)
    return [normalized_pairs[int(round(position))] for position in sample_positions]


def build_phase_info(
    phase_name: str,
    left_segment: pd.DataFrame,
    right_segment: pd.DataFrame,
    status: str,
    aligned_pair_count: int,
) -> dict[str, Any]:
    return {
        "phase": phase_name,
        "status": status,
        "left_start_frame": int(left_segment["frame_index"].iloc[0]),
        "left_end_frame": int(left_segment["frame_index"].iloc[-1]),
        "right_start_frame": int(right_segment["frame_index"].iloc[0]),
        "right_end_frame": int(right_segment["frame_index"].iloc[-1]),
        "left_frame_count": int(len(left_segment)),
        "right_frame_count": int(len(right_segment)),
        "aligned_pair_count": int(aligned_pair_count),
    }
