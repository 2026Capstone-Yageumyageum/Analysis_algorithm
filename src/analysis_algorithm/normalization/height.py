from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


HEAD_JOINTS = ("nose", "left_shoulder", "right_shoulder")
FOOT_JOINTS = ("left_foot_index", "right_foot_index", "left_ankle", "right_ankle")


@dataclass
class HeightNormalizationResult:
    features_df: pd.DataFrame
    summary: dict[str, Any] | None
    warnings: list[str]


def apply_height_normalization(
    keypoints_df: pd.DataFrame,
    features_df: pd.DataFrame,
    input_height_cm: float | None,
) -> HeightNormalizationResult:
    if input_height_cm is None:
        return HeightNormalizationResult(features_df=features_df, summary=None, warnings=[])
    if input_height_cm <= 0:
        return HeightNormalizationResult(
            features_df=features_df,
            summary={"enabled": False, "input_height_cm": None, "estimated_body_height_px": None, "cm_per_pixel": None},
            warnings=["Height normalization was skipped because the provided height was not positive."],
        )

    estimated_body_height_px, frame_samples = estimate_body_height_px(keypoints_df)
    if estimated_body_height_px is None or estimated_body_height_px <= 1.0:
        return HeightNormalizationResult(
            features_df=features_df,
            summary={
                "enabled": False,
                "input_height_cm": float(input_height_cm),
                "estimated_body_height_px": None,
                "cm_per_pixel": None,
                "frame_samples": frame_samples,
                "reason": "body_height_not_detected",
            },
            warnings=["Height normalization could not estimate body height reliably from the current keypoints."],
        )

    cm_per_pixel = float(input_height_cm) / float(estimated_body_height_px)
    normalized_df = features_df.copy()
    length_columns = ("stride_foot_extension", "stride_knee_lift")
    speed_columns = ("throwing_wrist_speed", "pelvis_speed", "stride_foot_speed")

    for column in length_columns:
        if column in normalized_df.columns:
            normalized_df[f"{column}_cm"] = normalized_df[column] * cm_per_pixel
            normalized_df[f"{column}_height_pct"] = (normalized_df[column] / estimated_body_height_px) * 100.0

    for column in speed_columns:
        if column in normalized_df.columns:
            normalized_df[f"{column}_cm_per_sec"] = normalized_df[column] * cm_per_pixel
            normalized_df[f"{column}_height_per_sec"] = normalized_df[column] / estimated_body_height_px

    return HeightNormalizationResult(
        features_df=normalized_df,
        summary={
            "enabled": True,
            "input_height_cm": float(input_height_cm),
            "estimated_body_height_px": float(estimated_body_height_px),
            "cm_per_pixel": float(cm_per_pixel),
            "frame_samples": int(frame_samples),
        },
        warnings=[],
    )


def estimate_body_height_px(keypoints_df: pd.DataFrame) -> tuple[float | None, int]:
    head_y = aggregate_joint_edge(keypoints_df, HEAD_JOINTS, edge="min")
    foot_y = aggregate_joint_edge(keypoints_df, FOOT_JOINTS, edge="max")
    if head_y is None or foot_y is None:
        return None, 0

    body_height = (foot_y - head_y).replace([np.inf, -np.inf], np.nan).dropna()
    body_height = body_height[body_height > 40.0]
    if body_height.empty:
        return None, 0
    upright_candidates = body_height[body_height >= float(body_height.quantile(0.75))]
    if upright_candidates.empty:
        upright_candidates = body_height
    return float(upright_candidates.median()), int(len(body_height))


def aggregate_joint_edge(
    keypoints_df: pd.DataFrame,
    joints: tuple[str, ...],
    edge: str,
    confidence_threshold: float = 0.15,
) -> pd.Series | None:
    candidate_series: list[pd.Series] = []
    for joint_name in joints:
        y_col = f"{joint_name}_y_smooth"
        conf_col = f"{joint_name}_confidence"
        if y_col not in keypoints_df.columns:
            continue
        series = pd.to_numeric(keypoints_df[y_col], errors="coerce")
        if conf_col in keypoints_df.columns:
            confidence = pd.to_numeric(keypoints_df[conf_col], errors="coerce").fillna(0.0)
            series = series.where(confidence >= confidence_threshold)
        candidate_series.append(series)

    if not candidate_series:
        return None
    candidate_df = pd.concat(candidate_series, axis=1)
    return candidate_df.min(axis=1, skipna=True) if edge == "min" else candidate_df.max(axis=1, skipna=True)
