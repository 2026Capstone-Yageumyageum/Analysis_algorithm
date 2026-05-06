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
    body_scale = _build_body_scale(keypoints_df, pelvis_x, pelvis_y, shoulder_x, shoulder_y)
    throwing_side = infer_throwing_side(keypoints_df)
    stride_side = "left" if throwing_side == "right" else "right"
    mirror_x = throwing_side == "left"

    unit_x_x, unit_x_y, unit_y_x, unit_y_y = _build_body_axes(pelvis_x, pelvis_y, shoulder_x, shoulder_y)
    table["pelvis_center_x"] = pelvis_x
    table["pelvis_center_y"] = pelvis_y
    table["shoulder_center_x"] = shoulder_x
    table["shoulder_center_y"] = shoulder_y
    table["body_scale"] = body_scale
    table["throwing_side"] = throwing_side
    table["stride_side"] = stride_side

    for joint in BODY_JOINTS:
        x_col = f"{joint}_x_smooth"
        y_col = f"{joint}_y_smooth"
        if x_col not in keypoints_df.columns or y_col not in keypoints_df.columns:
            warnings.append(f"{joint} smooth 좌표가 없어 분석 좌표에서 제외했습니다.")
            continue

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
            "method": "pelvis_torso_body_scale_2d_v1",
            "throwingSide": throwing_side,
            "strideSide": stride_side,
            "medianBodyScale": None if valid_scale.empty else round(float(valid_scale.median()), 6),
            "coordinateSystem": "pelvis-centered torso-axis body-scale units",
            "mirrorApplied": mirror_x,
        },
        warnings=warnings,
    )


def infer_throwing_side(keypoints_df: pd.DataFrame) -> str:
    left_motion = _joint_total_motion(keypoints_df, "left_wrist")
    right_motion = _joint_total_motion(keypoints_df, "right_wrist")
    return "left" if left_motion > right_motion else "right"


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
) -> pd.Series:
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
    raw_scale = torso.where(torso > 1e-4, pd.concat([shoulder_width, hip_width], axis=1).max(axis=1))
    valid = raw_scale.replace([np.inf, -np.inf], np.nan).dropna()
    fallback = float(valid.median()) if not valid.empty else 1.0
    return (
        raw_scale.replace([np.inf, -np.inf], np.nan)
        .interpolate(limit_direction="both")
        .rolling(window=7, center=True, min_periods=1)
        .median()
        .clip(lower=fallback * 0.55, upper=fallback * 1.45)
        .fillna(fallback)
    )


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

