from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class BodyScaleNormalizationResult:
    body_scale_px: pd.Series
    summary: dict[str, Any]
    warnings: list[str]


def apply_body_scale_normalization(keypoints_df: pd.DataFrame) -> BodyScaleNormalizationResult:
    pelvis_center_x = midpoint(keypoints_df["left_hip_x_smooth"], keypoints_df["right_hip_x_smooth"])
    pelvis_center_y = midpoint(keypoints_df["left_hip_y_smooth"], keypoints_df["right_hip_y_smooth"])
    shoulder_center_x = midpoint(keypoints_df["left_shoulder_x_smooth"], keypoints_df["right_shoulder_x_smooth"])
    shoulder_center_y = midpoint(keypoints_df["left_shoulder_y_smooth"], keypoints_df["right_shoulder_y_smooth"])

    torso_scale = sanitize_scale_series(euclidean_distance(shoulder_center_x, shoulder_center_y, pelvis_center_x, pelvis_center_y))
    shoulder_scale = sanitize_scale_series(
        euclidean_distance(
            keypoints_df["left_shoulder_x_smooth"],
            keypoints_df["left_shoulder_y_smooth"],
            keypoints_df["right_shoulder_x_smooth"],
            keypoints_df["right_shoulder_y_smooth"],
        )
    )
    hip_scale = sanitize_scale_series(
        euclidean_distance(
            keypoints_df["left_hip_x_smooth"],
            keypoints_df["left_hip_y_smooth"],
            keypoints_df["right_hip_x_smooth"],
            keypoints_df["right_hip_y_smooth"],
        )
    )

    width_fallback_scale = pd.concat([shoulder_scale, hip_scale], axis=1).max(axis=1, skipna=True)
    raw_body_scale_px = torso_scale.where(torso_scale.notna(), width_fallback_scale).replace([np.inf, -np.inf], np.nan)
    warnings: list[str] = []
    valid_scale = raw_body_scale_px.dropna()
    if valid_scale.empty:
        fallback_scale = 100.0
        body_scale_px = pd.Series(fallback_scale, index=keypoints_df.index, dtype=float)
        warnings.append("Body-scale normalization used a constant fallback because no reliable body scale was available.")
        return BodyScaleNormalizationResult(
            body_scale_px=body_scale_px,
            summary={
                "enabled": False,
                "reason": "no_valid_body_scale",
                "median_body_scale_px": None,
                "frame_samples": 0,
                "scale_method": "constant_fallback",
            },
            warnings=warnings,
        )

    median_body_scale_px = float(valid_scale.median())
    body_scale_px = raw_body_scale_px.interpolate(limit_direction="both")
    body_scale_px = body_scale_px.rolling(window=7, center=True, min_periods=1).median()
    lower_bound_px = median_body_scale_px * 0.55
    upper_bound_px = median_body_scale_px * 1.45
    body_scale_px = body_scale_px.clip(lower=lower_bound_px, upper=upper_bound_px).fillna(median_body_scale_px)

    return BodyScaleNormalizationResult(
        body_scale_px=body_scale_px.astype(float),
        summary={
            "enabled": True,
            "scale_method": "torso_primary_with_width_fallback_v2",
            "median_body_scale_px": median_body_scale_px,
            "frame_samples": int(len(valid_scale)),
            "clamp_bounds_px": {"lower": float(lower_bound_px), "upper": float(upper_bound_px)},
            "components": {
                "torso_length_px": _safe_median(torso_scale),
                "shoulder_width_px": _safe_median(shoulder_scale),
                "hip_width_px": _safe_median(hip_scale),
            },
        },
        warnings=warnings,
    )


def normalize_scalar_series(value_series: pd.Series, body_scale_px: pd.Series) -> pd.Series:
    return value_series / body_scale_px.replace(0, np.nan)


def canonicalize_signed_series(series: pd.Series, throwing_side: str) -> pd.Series:
    sign = -1.0 if throwing_side == "left" else 1.0
    return series * sign


def resolve_row_body_scale(row: pd.Series, fallback_scale: float | None = None) -> float | None:
    left_shoulder = row_joint_point(row, "left_shoulder")
    right_shoulder = row_joint_point(row, "right_shoulder")
    left_hip = row_joint_point(row, "left_hip")
    right_hip = row_joint_point(row, "right_hip")

    candidate = None
    if left_shoulder and right_shoulder and left_hip and right_hip:
        shoulder_center = ((left_shoulder[0] + right_shoulder[0]) / 2.0, (left_shoulder[1] + right_shoulder[1]) / 2.0)
        pelvis_center = ((left_hip[0] + right_hip[0]) / 2.0, (left_hip[1] + right_hip[1]) / 2.0)
        candidate = point_distance(shoulder_center, pelvis_center)

    if candidate is None or not np.isfinite(candidate) or candidate <= 5.0:
        width_candidates = []
        if left_shoulder and right_shoulder:
            width_candidates.append(point_distance(left_shoulder, right_shoulder))
        if left_hip and right_hip:
            width_candidates.append(point_distance(left_hip, right_hip))
        width_candidates = [value for value in width_candidates if np.isfinite(value) and value > 5.0]
        candidate = max(width_candidates) if width_candidates else None

    if candidate is not None:
        if fallback_scale is not None and np.isfinite(float(fallback_scale)) and float(fallback_scale) > 5.0:
            return float(np.clip(candidate, float(fallback_scale) * 0.55, float(fallback_scale) * 1.45))
        return float(candidate)
    if fallback_scale is not None and np.isfinite(float(fallback_scale)) and float(fallback_scale) > 1.0:
        return float(fallback_scale)
    return None


def midpoint(series_a: pd.Series, series_b: pd.Series) -> pd.Series:
    return (series_a + series_b) / 2.0


def euclidean_distance(x1: pd.Series, y1: pd.Series, x2: pd.Series, y2: pd.Series) -> pd.Series:
    return pd.Series(np.sqrt(((x2 - x1) ** 2) + ((y2 - y1) ** 2)), index=x1.index)


def sanitize_scale_series(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan)
    return numeric.where(numeric > 5.0)


def row_joint_point(row: pd.Series, joint_name: str) -> tuple[float, float] | None:
    x_value = row.get(f"{joint_name}_x_smooth")
    y_value = row.get(f"{joint_name}_y_smooth")
    if pd.isna(x_value) or pd.isna(y_value):
        return None
    return float(x_value), float(y_value)


def point_distance(point_a: tuple[float, float], point_b: tuple[float, float]) -> float:
    return float(np.sqrt(((point_b[0] - point_a[0]) ** 2) + ((point_b[1] - point_a[1]) ** 2)))


def _safe_median(series: pd.Series) -> float | None:
    valid = series.dropna()
    return None if valid.empty else float(valid.median())
