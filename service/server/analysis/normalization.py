from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


BODY_JOINTS = (
    "nose",
    "left_shoulder",
    "right_shoulder",
    "left_elbow",
    "right_elbow",
    "left_wrist",
    "right_wrist",
    "left_hip",
    "right_hip",
    "left_knee",
    "right_knee",
    "left_ankle",
    "right_ankle",
    "left_foot_index",
    "right_foot_index",
)


@dataclass(frozen=True)
class NormalizedPose:
    table: pd.DataFrame
    summary: dict[str, Any]
    warnings: list[str]


def build_body_frame_pose(keypoints_df: pd.DataFrame) -> NormalizedPose:
    """Build pelvis-centered, torso-axis, body-scale normalized coordinates."""
    warnings: list[str] = []
    if keypoints_df.empty:
        return NormalizedPose(table=pd.DataFrame(), summary={"status": "empty"}, warnings=["keypoints가 비어 있습니다."])

    required_columns = [
        "left_hip_x_smooth",
        "left_hip_y_smooth",
        "right_hip_x_smooth",
        "right_hip_y_smooth",
        "left_shoulder_x_smooth",
        "left_shoulder_y_smooth",
        "right_shoulder_x_smooth",
        "right_shoulder_y_smooth",
    ]
    missing = [column for column in required_columns if column not in keypoints_df.columns]
    if missing:
        return NormalizedPose(
            table=pd.DataFrame(),
            summary={"status": "missing_columns", "missingColumns": missing},
            warnings=[f"정규화에 필요한 컬럼이 없습니다: {', '.join(missing)}"],
        )

    table = pd.DataFrame()
    table["frame_index"] = keypoints_df["frame_index"].astype(int)
    table["time_sec"] = keypoints_df.get("time_sec", pd.Series(np.arange(len(keypoints_df)), index=keypoints_df.index))

    pelvis_x = _midpoint(keypoints_df["left_hip_x_smooth"], keypoints_df["right_hip_x_smooth"])
    pelvis_y = _midpoint(keypoints_df["left_hip_y_smooth"], keypoints_df["right_hip_y_smooth"])
    shoulder_x = _midpoint(keypoints_df["left_shoulder_x_smooth"], keypoints_df["right_shoulder_x_smooth"])
    shoulder_y = _midpoint(keypoints_df["left_shoulder_y_smooth"], keypoints_df["right_shoulder_y_smooth"])
    raw_body_scale, body_scale, scale_summary = _build_body_scale(keypoints_df, pelvis_x, pelvis_y, shoulder_x, shoulder_y)
    throwing_side = infer_throwing_side(keypoints_df)
    stride_side = "left" if throwing_side == "right" else "right"
    mirror_x = throwing_side == "left"

    unit_x_x, unit_x_y, unit_y_x, unit_y_y = _build_body_axes(pelvis_x, pelvis_y, shoulder_x, shoulder_y)
    table["pelvis_center_x"] = pelvis_x
    table["pelvis_center_y"] = pelvis_y
    table["shoulder_center_x"] = shoulder_x
    table["shoulder_center_y"] = shoulder_y
    table["raw_body_scale"] = raw_body_scale
    table["body_scale"] = body_scale
    table["throwing_side"] = throwing_side
    table["stride_side"] = stride_side

    for joint in BODY_JOINTS:
        x_col = f"{joint}_x_smooth"
        y_col = f"{joint}_y_smooth"
        if x_col not in keypoints_df.columns or y_col not in keypoints_df.columns:
            warnings.append(f"{joint} smooth 좌표가 없어 분석 좌표에서 제외했습니다.")
            continue

        table[f"{joint}_image_x"] = pd.to_numeric(keypoints_df[x_col], errors="coerce").interpolate(limit_direction="both")
        table[f"{joint}_image_y"] = pd.to_numeric(keypoints_df[y_col], errors="coerce").interpolate(limit_direction="both")
        body_x, body_y = _project_to_body_frame(
            point_x=keypoints_df[x_col],
            point_y=keypoints_df[y_col],
            pelvis_x=pelvis_x,
            pelvis_y=pelvis_y,
            unit_x_x=unit_x_x,
            unit_x_y=unit_x_y,
            unit_y_x=unit_y_x,
            unit_y_y=unit_y_y,
            body_scale=body_scale,
            mirror_x=mirror_x,
        )
        table[f"{joint}_body_x"] = body_x
        table[f"{joint}_body_y"] = body_y
        confidence_col = f"{joint}_confidence"
        table[f"{joint}_confidence"] = (
            pd.to_numeric(keypoints_df[confidence_col], errors="coerce").fillna(0.0)
            if confidence_col in keypoints_df.columns
            else 1.0
        )
        table[f"{joint}_speed_body"] = _point_speed(body_x, body_y, table["time_sec"])

    valid_scale = body_scale.replace([np.inf, -np.inf], np.nan).dropna()
    if valid_scale.empty:
        warnings.append("body-scale을 안정적으로 계산하지 못해 1.0 fallback을 사용했습니다.")

    return NormalizedPose(
        table=table,
        summary={
            "status": "ready",
            "method": "pelvis_stable_body_scale_2d_v2",
            "throwingSide": throwing_side,
            "strideSide": stride_side,
            "medianBodyScale": scale_summary.get("stableScale"),
            "scalePolicy": scale_summary,
            "coordinateSystem": "pelvis-centered torso-axis body-scale units",
            "mirrorApplied": mirror_x,
        },
        warnings=warnings,
    )


def infer_throwing_side(keypoints_df: pd.DataFrame) -> str:
    left_activity = _throwing_arm_activity_score(keypoints_df, "left")
    right_activity = _throwing_arm_activity_score(keypoints_df, "right")
    left_position = _throwing_arm_position_score(keypoints_df, "left")
    right_position = _throwing_arm_position_score(keypoints_df, "right")
    left_motion = _joint_total_motion(keypoints_df, "left_wrist")
    right_motion = _joint_total_motion(keypoints_df, "right_wrist")

    left_score = (
        0.55 * _relative_score(left_activity, left_activity, right_activity)
        + 0.25 * _relative_score(left_position, left_position, right_position)
        + 0.20 * _relative_score(left_motion, left_motion, right_motion)
    )
    right_score = (
        0.55 * _relative_score(right_activity, left_activity, right_activity)
        + 0.25 * _relative_score(right_position, left_position, right_position)
        + 0.20 * _relative_score(right_motion, left_motion, right_motion)
    )
    return "left" if left_score > right_score else "right"


def _throwing_arm_position_score(keypoints_df: pd.DataFrame, side: str) -> float:
    required_columns = [
        f"{side}_shoulder_x_smooth",
        f"{side}_shoulder_y_smooth",
        f"{side}_elbow_x_smooth",
        f"{side}_elbow_y_smooth",
        f"{side}_wrist_x_smooth",
        f"{side}_wrist_y_smooth",
        f"{side}_shoulder_confidence",
        f"{side}_elbow_confidence",
        f"{side}_wrist_confidence",
        "left_hip_x_smooth",
        "left_hip_y_smooth",
        "right_hip_x_smooth",
        "right_hip_y_smooth",
    ]
    if keypoints_df.empty or any(column not in keypoints_df.columns for column in required_columns):
        return 0.0

    shoulder_x = _numeric_column(keypoints_df, f"{side}_shoulder_x_smooth")
    shoulder_y = _numeric_column(keypoints_df, f"{side}_shoulder_y_smooth")
    elbow_x = _numeric_column(keypoints_df, f"{side}_elbow_x_smooth")
    elbow_y = _numeric_column(keypoints_df, f"{side}_elbow_y_smooth")
    wrist_x = _numeric_column(keypoints_df, f"{side}_wrist_x_smooth")
    wrist_y = _numeric_column(keypoints_df, f"{side}_wrist_y_smooth")
    pelvis_x = _midpoint(keypoints_df["left_hip_x_smooth"], keypoints_df["right_hip_x_smooth"])
    pelvis_y = _midpoint(keypoints_df["left_hip_y_smooth"], keypoints_df["right_hip_y_smooth"])
    confidence = _joint_chain_confidence(keypoints_df, side)

    score = (
        np.hypot(wrist_x - shoulder_x, wrist_y - shoulder_y) * 0.45
        + np.hypot(wrist_x - pelvis_x, wrist_y - pelvis_y) * 0.30
        + np.hypot(wrist_x - elbow_x, wrist_y - elbow_y) * 0.15
        + (wrist_x - pelvis_x).abs() * 0.10
    ) * confidence
    focused = pd.Series(score, index=keypoints_df.index).iloc[
        int(len(keypoints_df) * 0.15) : max(1, int(len(keypoints_df) * 0.95))
    ].dropna()
    if focused.empty:
        return 0.0
    return float(focused.nlargest(max(4, min(10, len(focused)))).mean())


def _throwing_arm_activity_score(keypoints_df: pd.DataFrame, side: str) -> float:
    required_columns = [
        f"{side}_shoulder_x_smooth",
        f"{side}_shoulder_y_smooth",
        f"{side}_elbow_x_smooth",
        f"{side}_elbow_y_smooth",
        f"{side}_wrist_x_smooth",
        f"{side}_wrist_y_smooth",
        f"{side}_shoulder_confidence",
        f"{side}_elbow_confidence",
        f"{side}_wrist_confidence",
    ]
    if keypoints_df.empty or any(column not in keypoints_df.columns for column in required_columns):
        return 0.0

    shoulder_x = _numeric_column(keypoints_df, f"{side}_shoulder_x_smooth")
    shoulder_y = _numeric_column(keypoints_df, f"{side}_shoulder_y_smooth")
    elbow_x = _numeric_column(keypoints_df, f"{side}_elbow_x_smooth")
    elbow_y = _numeric_column(keypoints_df, f"{side}_elbow_y_smooth")
    wrist_x = _numeric_column(keypoints_df, f"{side}_wrist_x_smooth")
    wrist_y = _numeric_column(keypoints_df, f"{side}_wrist_y_smooth")
    confidence = _joint_chain_confidence(keypoints_df, side)

    score = (
        np.hypot(wrist_x - shoulder_x, wrist_y - shoulder_y) * 0.70
        + np.hypot(wrist_x - elbow_x, wrist_y - elbow_y) * 0.30
    ) * confidence
    early_score = pd.Series(score, index=keypoints_df.index).iloc[: max(1, int(len(keypoints_df) * 0.70))].dropna()
    if early_score.empty:
        return 0.0
    return float(early_score.nlargest(max(3, min(8, len(early_score)))).mean())


def _joint_chain_confidence(keypoints_df: pd.DataFrame, side: str) -> pd.Series:
    return (
        _numeric_column(keypoints_df, f"{side}_wrist_confidence", fallback=0.0)
        * _numeric_column(keypoints_df, f"{side}_elbow_confidence", fallback=0.0)
        * _numeric_column(keypoints_df, f"{side}_shoulder_confidence", fallback=0.0)
    ).fillna(0.0)


def _numeric_column(keypoints_df: pd.DataFrame, column: str, fallback: float | None = None) -> pd.Series:
    series = pd.to_numeric(keypoints_df[column], errors="coerce")
    if fallback is not None:
        return series.fillna(fallback)
    return series.interpolate(limit_direction="both")


def _relative_score(value: float, left_value: float, right_value: float) -> float:
    denominator = max(abs(left_value), abs(right_value), 1e-9)
    return float(value / denominator)


def _joint_total_motion(keypoints_df: pd.DataFrame, joint: str) -> float:
    x_col = f"{joint}_x_smooth"
    y_col = f"{joint}_y_smooth"
    if x_col not in keypoints_df.columns or y_col not in keypoints_df.columns:
        return 0.0
    x_values = pd.to_numeric(keypoints_df[x_col], errors="coerce").interpolate(limit_direction="both")
    y_values = pd.to_numeric(keypoints_df[y_col], errors="coerce").interpolate(limit_direction="both")
    dx = x_values.diff().fillna(0.0)
    dy = y_values.diff().fillna(0.0)
    return float(np.sqrt((dx**2) + (dy**2)).sum())


def _build_body_scale(
    keypoints_df: pd.DataFrame,
    pelvis_x: pd.Series,
    pelvis_y: pd.Series,
    shoulder_x: pd.Series,
    shoulder_y: pd.Series,
) -> tuple[pd.Series, pd.Series, dict[str, Any]]:
    torso = _distance(shoulder_x, shoulder_y, pelvis_x, pelvis_y)
    shoulder_width = _distance(
        keypoints_df["left_shoulder_x_smooth"],
        keypoints_df["left_shoulder_y_smooth"],
        keypoints_df["right_shoulder_x_smooth"],
        keypoints_df["right_shoulder_y_smooth"],
    )
    hip_width = _distance(
        keypoints_df["left_hip_x_smooth"],
        keypoints_df["left_hip_y_smooth"],
        keypoints_df["right_hip_x_smooth"],
        keypoints_df["right_hip_y_smooth"],
    )
    body_height = _body_height_proxy(keypoints_df)
    raw_scale = pd.concat(
        [
            torso,
            shoulder_width * 3.0,
            hip_width * 2.4,
            body_height * 0.55,
        ],
        axis=1,
    ).max(axis=1)
    valid_mask = _valid_scale_confidence(keypoints_df)
    valid_scale = raw_scale.where(valid_mask).replace([np.inf, -np.inf], np.nan).dropna()
    if valid_scale.empty:
        valid_scale = raw_scale.replace([np.inf, -np.inf], np.nan).dropna()
    stable_scale = float(valid_scale.median()) if not valid_scale.empty else 1.0
    if not np.isfinite(stable_scale) or abs(stable_scale) <= 1e-9:
        stable_scale = 1.0
    cleaned_raw_scale = raw_scale.replace([np.inf, -np.inf], np.nan).interpolate(limit_direction="both").fillna(stable_scale)
    body_scale = pd.Series(stable_scale, index=keypoints_df.index, dtype=float)
    return (
        cleaned_raw_scale,
        body_scale,
        {
            "version": "pelvis_fixed_height_body_scale_2d_v5",
            "rawScale": "max(torso, shoulder_width * 3.0, hip_width * 2.4, body_height * 0.55)",
            "stableScale": round(stable_scale, 6),
            "stableScaleStatistic": "median(rawScale over valid frames), reused for every frame",
            "origin": "pelvis_center",
            "mirror": "left_handed_pitchers",
            "validFrameCount": int(len(valid_scale)),
        },
    )


def _body_height_proxy(keypoints_df: pd.DataFrame) -> pd.Series:
    head_y = _numeric_column(keypoints_df, "nose_y_smooth")
    left_shoulder_y = _numeric_column(keypoints_df, "left_shoulder_y_smooth")
    right_shoulder_y = _numeric_column(keypoints_df, "right_shoulder_y_smooth")
    top_y = pd.concat([head_y, left_shoulder_y, right_shoulder_y], axis=1).min(axis=1)
    lower_y = pd.concat(
        [
            _numeric_column(keypoints_df, "left_ankle_y_smooth"),
            _numeric_column(keypoints_df, "right_ankle_y_smooth"),
            _numeric_column(keypoints_df, "left_foot_index_y_smooth"),
            _numeric_column(keypoints_df, "right_foot_index_y_smooth"),
        ],
        axis=1,
    ).max(axis=1)
    return (lower_y - top_y).abs()


def _valid_scale_confidence(keypoints_df: pd.DataFrame) -> pd.Series:
    confidence_columns = [
        column
        for column in (
            "left_shoulder_confidence",
            "right_shoulder_confidence",
            "left_hip_confidence",
            "right_hip_confidence",
        )
        if column in keypoints_df.columns
    ]
    if not confidence_columns:
        return pd.Series(True, index=keypoints_df.index)
    confidence = keypoints_df[confidence_columns].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    return confidence.mean(axis=1) >= 0.05


def _build_body_axes(
    pelvis_x: pd.Series,
    pelvis_y: pd.Series,
    shoulder_x: pd.Series,
    shoulder_y: pd.Series,
) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    torso_dx = shoulder_x - pelvis_x
    torso_dy = shoulder_y - pelvis_y
    torso_norm = np.sqrt((torso_dx**2) + (torso_dy**2)).replace(0, np.nan)
    unit_y_x = (torso_dx / torso_norm).interpolate(limit_direction="both").fillna(0.0)
    unit_y_y = (torso_dy / torso_norm).interpolate(limit_direction="both").fillna(-1.0)
    return -unit_y_y, unit_y_x, unit_y_x, unit_y_y


def _project_to_body_frame(
    point_x: pd.Series,
    point_y: pd.Series,
    pelvis_x: pd.Series,
    pelvis_y: pd.Series,
    unit_x_x: pd.Series,
    unit_x_y: pd.Series,
    unit_y_x: pd.Series,
    unit_y_y: pd.Series,
    body_scale: pd.Series,
    mirror_x: bool,
) -> tuple[pd.Series, pd.Series]:
    relative_x = point_x - pelvis_x
    relative_y = point_y - pelvis_y
    body_x = ((relative_x * unit_x_x) + (relative_y * unit_x_y)) / body_scale.replace(0, np.nan)
    body_y = ((relative_x * unit_y_x) + (relative_y * unit_y_y)) / body_scale.replace(0, np.nan)
    if mirror_x:
        body_x = body_x * -1.0
    return body_x.replace([np.inf, -np.inf], np.nan), body_y.replace([np.inf, -np.inf], np.nan)


def _point_speed(body_x: pd.Series, body_y: pd.Series, time_sec: pd.Series) -> pd.Series:
    dt = pd.to_numeric(time_sec, errors="coerce").diff().replace(0, np.nan)
    dx = body_x.diff()
    dy = body_y.diff()
    speed = np.sqrt((dx**2) + (dy**2)) / dt
    return speed.replace([np.inf, -np.inf], np.nan).fillna(0.0)


def _midpoint(a: pd.Series, b: pd.Series) -> pd.Series:
    return (pd.to_numeric(a, errors="coerce") + pd.to_numeric(b, errors="coerce")) / 2.0


def _distance(x1: pd.Series, y1: pd.Series, x2: pd.Series, y2: pd.Series) -> pd.Series:
    return np.sqrt(((pd.to_numeric(x2, errors="coerce") - pd.to_numeric(x1, errors="coerce")) ** 2) + ((pd.to_numeric(y2, errors="coerce") - pd.to_numeric(y1, errors="coerce")) ** 2))
