from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from analysis_algorithm.normalization.body_frame import (
    build_body_frame_axes,
    decompose_body_frame_series,
    normalize_point_series_to_body_frame,
    resolve_stride_direction_reference,
)
from analysis_algorithm.normalization.body_scale import (
    apply_body_scale_normalization,
    canonicalize_signed_series,
    midpoint,
    normalize_scalar_series,
)
from analysis_algorithm.normalization.height import apply_height_normalization


@dataclass
class FeatureExtractionResult:
    features_df: pd.DataFrame
    metadata: dict[str, Any]
    warnings: list[str]


def extract_motion_features(
    keypoints_df: pd.DataFrame,
    fps: float,
    handedness_override: str | None = None,
    input_height_cm: float | None = None,
) -> FeatureExtractionResult:
    df = keypoints_df.copy()
    warnings: list[str] = []

    throwing_side, handedness_source = infer_throwing_side(df, handedness_override=handedness_override)
    stride_side = "left" if throwing_side == "right" else "right"
    wrist_joint = f"{throwing_side}_wrist"
    elbow_joint = f"{throwing_side}_elbow"
    shoulder_joint = f"{throwing_side}_shoulder"
    stride_knee_joint = f"{stride_side}_knee"

    pelvis_center_x = midpoint(df["left_hip_x_smooth"], df["right_hip_x_smooth"])
    pelvis_center_y = midpoint(df["left_hip_y_smooth"], df["right_hip_y_smooth"])
    shoulder_center_x = midpoint(df["left_shoulder_x_smooth"], df["right_shoulder_x_smooth"])
    shoulder_center_y = midpoint(df["left_shoulder_y_smooth"], df["right_shoulder_y_smooth"])

    body_scale_result = apply_body_scale_normalization(df)
    body_scale_px = body_scale_result.body_scale_px
    warnings.extend(body_scale_result.warnings)

    body_axis_x, body_axis_y, torso_axis_x, torso_axis_y = build_body_frame_axes(
        pelvis_center_x=pelvis_center_x,
        pelvis_center_y=pelvis_center_y,
        shoulder_center_x=shoulder_center_x,
        shoulder_center_y=shoulder_center_y,
    )

    body_trunk_tilt_deg = trunk_tilt_deg(pelvis_center_x, pelvis_center_y, shoulder_center_x, shoulder_center_y)
    shoulder_tilt_deg = line_tilt_deg(
        df["left_shoulder_x_smooth"],
        df["left_shoulder_y_smooth"],
        df["right_shoulder_x_smooth"],
        df["right_shoulder_y_smooth"],
    )
    pelvis_tilt_deg = line_tilt_deg(
        df["left_hip_x_smooth"],
        df["left_hip_y_smooth"],
        df["right_hip_x_smooth"],
        df["right_hip_y_smooth"],
    )

    throwing_elbow_angle_deg = joint_angle_deg(
        df[f"{shoulder_joint}_x_smooth"],
        df[f"{shoulder_joint}_y_smooth"],
        df[f"{elbow_joint}_x_smooth"],
        df[f"{elbow_joint}_y_smooth"],
        df[f"{wrist_joint}_x_smooth"],
        df[f"{wrist_joint}_y_smooth"],
    )
    throwing_arm_orientation_deg = line_tilt_deg(
        df[f"{shoulder_joint}_x_smooth"],
        df[f"{shoulder_joint}_y_smooth"],
        df[f"{wrist_joint}_x_smooth"],
        df[f"{wrist_joint}_y_smooth"],
    )
    left_knee_angle_deg = joint_angle_deg(
        df["left_hip_x_smooth"],
        df["left_hip_y_smooth"],
        df["left_knee_x_smooth"],
        df["left_knee_y_smooth"],
        df["left_ankle_x_smooth"],
        df["left_ankle_y_smooth"],
    )
    right_knee_angle_deg = joint_angle_deg(
        df["right_hip_x_smooth"],
        df["right_hip_y_smooth"],
        df["right_knee_x_smooth"],
        df["right_knee_y_smooth"],
        df["right_ankle_x_smooth"],
        df["right_ankle_y_smooth"],
    )

    throwing_wrist_x = df[f"{wrist_joint}_x_smooth"]
    throwing_wrist_y = df[f"{wrist_joint}_y_smooth"]
    stride_foot_x = choose_stride_foot_series(df, stride_side, axis="x")
    stride_foot_y = choose_stride_foot_series(df, stride_side, axis="y")

    time_step = 1.0 / fps if fps > 0 else 1.0 / 30.0
    throwing_wrist_speed = speed_magnitude(throwing_wrist_x, throwing_wrist_y, time_step)
    pelvis_speed = speed_magnitude(pelvis_center_x, pelvis_center_y, time_step)
    stride_foot_speed = speed_magnitude(stride_foot_x, stride_foot_y, time_step)
    stride_foot_extension = np.sqrt((stride_foot_x - pelvis_center_x) ** 2 + (stride_foot_y - pelvis_center_y) ** 2)
    stride_knee_lift = pelvis_center_y - df[f"{stride_knee_joint}_y_smooth"]
    mirror_x = throwing_side == "left"

    throwing_wrist_body_x, throwing_wrist_body_y = normalize_point_series_to_body_frame(
        throwing_wrist_x,
        throwing_wrist_y,
        pelvis_center_x,
        pelvis_center_y,
        body_axis_x,
        body_axis_y,
        torso_axis_x,
        torso_axis_y,
        body_scale_px,
        mirror_x=mirror_x,
    )
    stride_foot_body_x, stride_foot_body_y = normalize_point_series_to_body_frame(
        stride_foot_x,
        stride_foot_y,
        pelvis_center_x,
        pelvis_center_y,
        body_axis_x,
        body_axis_y,
        torso_axis_x,
        torso_axis_y,
        body_scale_px,
        mirror_x=mirror_x,
    )

    stride_direction_reference = resolve_stride_direction_reference(df["frame_index"], stride_foot_body_x, stride_foot_body_y)
    throwing_wrist_forward_body, throwing_wrist_lateral_body = decompose_body_frame_series(
        throwing_wrist_body_x,
        throwing_wrist_body_y,
        stride_direction_reference,
    )
    stride_foot_forward_body, stride_foot_lateral_body = decompose_body_frame_series(
        stride_foot_body_x,
        stride_foot_body_y,
        stride_direction_reference,
    )

    lead_knee_angle_deg = left_knee_angle_deg if stride_side == "left" else right_knee_angle_deg
    trail_knee_angle_deg = right_knee_angle_deg if throwing_side == "right" else left_knee_angle_deg

    features_df = pd.DataFrame(
        {
            "frame_index": df["frame_index"].astype(int),
            "time_sec": df["time_sec"],
            "body_trunk_tilt_deg": body_trunk_tilt_deg,
            "body_trunk_tilt_canonical_deg": canonicalize_signed_series(body_trunk_tilt_deg, throwing_side),
            "shoulder_tilt_deg": shoulder_tilt_deg,
            "shoulder_tilt_canonical_deg": canonicalize_signed_series(shoulder_tilt_deg, throwing_side),
            "pelvis_tilt_deg": pelvis_tilt_deg,
            "pelvis_tilt_canonical_deg": canonicalize_signed_series(pelvis_tilt_deg, throwing_side),
            "throwing_elbow_angle_deg": throwing_elbow_angle_deg,
            "throwing_arm_orientation_deg": throwing_arm_orientation_deg,
            "throwing_arm_orientation_canonical_deg": canonicalize_signed_series(throwing_arm_orientation_deg, throwing_side),
            "left_knee_angle_deg": left_knee_angle_deg,
            "right_knee_angle_deg": right_knee_angle_deg,
            "lead_knee_angle_deg": lead_knee_angle_deg,
            "trail_knee_angle_deg": trail_knee_angle_deg,
            "throwing_wrist_x": throwing_wrist_x,
            "throwing_wrist_y": throwing_wrist_y,
            "throwing_wrist_body_x": throwing_wrist_body_x,
            "throwing_wrist_body_y": throwing_wrist_body_y,
            "throwing_wrist_forward_body": throwing_wrist_forward_body,
            "throwing_wrist_lateral_body": throwing_wrist_lateral_body,
            "throwing_wrist_speed": throwing_wrist_speed,
            "throwing_wrist_speed_body_scale_per_sec": normalize_scalar_series(throwing_wrist_speed, body_scale_px),
            "pelvis_center_x": pelvis_center_x,
            "pelvis_center_y": pelvis_center_y,
            "pelvis_speed": pelvis_speed,
            "pelvis_speed_body_scale_per_sec": normalize_scalar_series(pelvis_speed, body_scale_px),
            "stride_foot_x": stride_foot_x,
            "stride_foot_y": stride_foot_y,
            "stride_foot_body_x": stride_foot_body_x,
            "stride_foot_body_y": stride_foot_body_y,
            "stride_foot_forward_body": stride_foot_forward_body,
            "stride_foot_lateral_body": stride_foot_lateral_body,
            "stride_foot_speed": stride_foot_speed,
            "stride_foot_speed_body_scale_per_sec": normalize_scalar_series(stride_foot_speed, body_scale_px),
            "stride_foot_extension": stride_foot_extension,
            "stride_foot_extension_body_scale": normalize_scalar_series(stride_foot_extension, body_scale_px),
            "stride_knee_lift": stride_knee_lift,
            "stride_knee_lift_body_scale": normalize_scalar_series(stride_knee_lift, body_scale_px),
            "stride_ankle_y": df[f"{stride_side}_ankle_y_smooth"],
            "body_scale_px": body_scale_px,
        }
    )

    height_normalization_result = apply_height_normalization(df, features_df, input_height_cm)
    features_df = height_normalization_result.features_df
    warnings.extend(height_normalization_result.warnings)
    if features_df["throwing_wrist_speed"].isna().all():
        warnings.append("Throwing wrist speed could not be computed reliably.")
    if features_df["stride_knee_lift"].isna().all():
        warnings.append("Stride-side knee lift could not be computed reliably.")

    metadata = {
        "throwing_side": throwing_side,
        "stride_side": stride_side,
        "handedness_source": handedness_source,
        "handedness_override": handedness_override or "",
        "height_normalization": height_normalization_result.summary,
        "body_scale_normalization": body_scale_result.summary,
        "body_frame_normalization": {
            "enabled": True,
            "frame_axis": "pelvis_centered_body_frame_v1",
            "stride_direction_frame_index": stride_direction_reference.frame_index,
            "stride_direction_unit": {"x": float(stride_direction_reference.unit_x), "y": float(stride_direction_reference.unit_y)},
        },
    }
    return FeatureExtractionResult(features_df=features_df, metadata=metadata, warnings=warnings)


def infer_throwing_side(keypoints_df: pd.DataFrame, handedness_override: str | None = None) -> tuple[str, str]:
    if handedness_override in {"left", "right"}:
        return handedness_override, "manual_override"
    left_score = throwing_arm_position_score(keypoints_df, "left")
    right_score = throwing_arm_position_score(keypoints_df, "right")
    left_activity = throwing_arm_activity_score(keypoints_df, "left")
    right_activity = throwing_arm_activity_score(keypoints_df, "right")
    left_distance = cumulative_path_length(keypoints_df["left_wrist_x_smooth"], keypoints_df["left_wrist_y_smooth"])
    right_distance = cumulative_path_length(keypoints_df["right_wrist_x_smooth"], keypoints_df["right_wrist_y_smooth"])
    votes = [
        "right" if right_score > left_score else "left",
        "right" if right_activity > left_activity else "left",
        "right" if right_distance > left_distance else "left",
    ]
    return ("right", "auto_vote") if votes.count("right") > votes.count("left") else ("left", "auto_vote")


def throwing_arm_position_score(keypoints_df: pd.DataFrame, side: str) -> float:
    if keypoints_df.empty:
        return 0.0
    shoulder_x = keypoints_df[f"{side}_shoulder_x_smooth"]
    shoulder_y = keypoints_df[f"{side}_shoulder_y_smooth"]
    wrist_x = keypoints_df[f"{side}_wrist_x_smooth"]
    wrist_y = keypoints_df[f"{side}_wrist_y_smooth"]
    elbow_x = keypoints_df[f"{side}_elbow_x_smooth"]
    elbow_y = keypoints_df[f"{side}_elbow_y_smooth"]
    pelvis_center_x = midpoint(keypoints_df["left_hip_x_smooth"], keypoints_df["right_hip_x_smooth"])
    pelvis_center_y = midpoint(keypoints_df["left_hip_y_smooth"], keypoints_df["right_hip_y_smooth"])
    confidence = (
        keypoints_df[f"{side}_wrist_confidence"].fillna(0.0)
        * keypoints_df[f"{side}_elbow_confidence"].fillna(0.0)
        * keypoints_df[f"{side}_shoulder_confidence"].fillna(0.0)
    )
    score = (
        np.hypot(wrist_x - shoulder_x, wrist_y - shoulder_y) * 0.45
        + np.hypot(wrist_x - pelvis_center_x, wrist_y - pelvis_center_y) * 0.30
        + np.hypot(wrist_x - elbow_x, wrist_y - elbow_y) * 0.15
        + (wrist_x - pelvis_center_x).abs() * 0.10
    ) * confidence
    focused_score = pd.Series(score, index=keypoints_df.index).iloc[int(len(keypoints_df) * 0.15) : max(1, int(len(keypoints_df) * 0.95))].dropna()
    if focused_score.empty:
        return 0.0
    return float(focused_score.nlargest(max(4, min(10, len(focused_score)))).mean())


def throwing_arm_activity_score(keypoints_df: pd.DataFrame, side: str) -> float:
    if keypoints_df.empty:
        return 0.0
    shoulder_x = keypoints_df[f"{side}_shoulder_x_smooth"]
    shoulder_y = keypoints_df[f"{side}_shoulder_y_smooth"]
    elbow_x = keypoints_df[f"{side}_elbow_x_smooth"]
    elbow_y = keypoints_df[f"{side}_elbow_y_smooth"]
    wrist_x = keypoints_df[f"{side}_wrist_x_smooth"]
    wrist_y = keypoints_df[f"{side}_wrist_y_smooth"]
    confidence = (
        keypoints_df[f"{side}_wrist_confidence"].fillna(0.0)
        * keypoints_df[f"{side}_elbow_confidence"].fillna(0.0)
        * keypoints_df[f"{side}_shoulder_confidence"].fillna(0.0)
    )
    score = ((np.hypot(wrist_x - shoulder_x, wrist_y - shoulder_y) * 0.7) + (np.hypot(wrist_x - elbow_x, wrist_y - elbow_y) * 0.3)) * confidence
    early_score = pd.Series(score, index=keypoints_df.index).iloc[: max(1, int(len(keypoints_df) * 0.7))].dropna()
    if early_score.empty:
        return 0.0
    return float(early_score.nlargest(max(3, min(8, len(early_score)))).mean())


def line_tilt_deg(x1: pd.Series, y1: pd.Series, x2: pd.Series, y2: pd.Series) -> pd.Series:
    return pd.Series(np.degrees(np.arctan2(y2 - y1, x2 - x1)), index=x1.index)


def trunk_tilt_deg(
    pelvis_center_x: pd.Series,
    pelvis_center_y: pd.Series,
    shoulder_center_x: pd.Series,
    shoulder_center_y: pd.Series,
) -> pd.Series:
    dx = shoulder_center_x - pelvis_center_x
    dy = shoulder_center_y - pelvis_center_y
    return pd.Series(np.degrees(np.arctan2(dx, -dy)), index=pelvis_center_x.index)


def joint_angle_deg(ax: pd.Series, ay: pd.Series, bx: pd.Series, by: pd.Series, cx: pd.Series, cy: pd.Series) -> pd.Series:
    ba_x = ax - bx
    ba_y = ay - by
    bc_x = cx - bx
    bc_y = cy - by
    dot = (ba_x * bc_x) + (ba_y * bc_y)
    denom = np.sqrt((ba_x**2) + (ba_y**2)) * np.sqrt((bc_x**2) + (bc_y**2))
    cosine = np.clip(dot / denom.replace(0, np.nan), -1.0, 1.0)
    return pd.Series(np.degrees(np.arccos(cosine)), index=ax.index)


def speed_magnitude(x: pd.Series, y: pd.Series, time_step: float) -> pd.Series:
    x_interp = interpolate_series(x)
    y_interp = interpolate_series(y)
    if x_interp.isna().all() or y_interp.isna().all():
        return pd.Series(np.nan, index=x.index)
    dx = np.gradient(x_interp.to_numpy(dtype=float), time_step)
    dy = np.gradient(y_interp.to_numpy(dtype=float), time_step)
    return pd.Series(np.sqrt(dx**2 + dy**2), index=x.index)


def interpolate_series(series: pd.Series) -> pd.Series:
    if series.notna().sum() < 2:
        return series
    return series.interpolate(limit_direction="both")


def cumulative_path_length(x: pd.Series, y: pd.Series) -> float:
    mask = x.notna() & y.notna()
    if mask.sum() < 2:
        return 0.0
    x_values = x[mask].to_numpy(dtype=float)
    y_values = y[mask].to_numpy(dtype=float)
    return float(np.sum(np.sqrt(np.diff(x_values) ** 2 + np.diff(y_values) ** 2)))


def choose_stride_foot_series(keypoints_df: pd.DataFrame, stride_side: str, axis: str) -> pd.Series:
    foot_index_col = f"{stride_side}_foot_index_{axis}_smooth"
    ankle_col = f"{stride_side}_ankle_{axis}_smooth"
    if foot_index_col in keypoints_df.columns and keypoints_df[foot_index_col].notna().any():
        return keypoints_df[foot_index_col]
    return keypoints_df[ankle_col]
