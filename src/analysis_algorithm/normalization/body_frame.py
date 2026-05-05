from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class StrideDirectionReference:
    unit_x: float
    unit_y: float
    frame_index: int | None


def build_body_frame_axes(
    pelvis_center_x: pd.Series,
    pelvis_center_y: pd.Series,
    shoulder_center_x: pd.Series,
    shoulder_center_y: pd.Series,
) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    torso_dx = shoulder_center_x - pelvis_center_x
    torso_dy = shoulder_center_y - pelvis_center_y
    torso_norm = pd.Series(np.sqrt((torso_dx**2) + (torso_dy**2)), index=pelvis_center_x.index).replace([np.inf, -np.inf], np.nan)
    torso_norm = torso_norm.where(torso_norm > 1e-6)

    unit_y_x = torso_dx / torso_norm
    unit_y_y = torso_dy / torso_norm
    unit_x_x = -unit_y_y
    unit_x_y = unit_y_x
    return unit_x_x, unit_x_y, unit_y_x, unit_y_y


def normalize_point_series_to_body_frame(
    point_x: pd.Series,
    point_y: pd.Series,
    pelvis_center_x: pd.Series,
    pelvis_center_y: pd.Series,
    unit_x_x: pd.Series,
    unit_x_y: pd.Series,
    unit_y_x: pd.Series,
    unit_y_y: pd.Series,
    body_scale_px: pd.Series,
    mirror_x: bool,
) -> tuple[pd.Series, pd.Series]:
    relative_x = point_x - pelvis_center_x
    relative_y = point_y - pelvis_center_y
    body_x = (relative_x * unit_x_x) + (relative_y * unit_x_y)
    body_y = (relative_x * unit_y_x) + (relative_y * unit_y_y)
    if mirror_x:
        body_x = body_x * -1.0
    safe_scale = body_scale_px.replace(0, np.nan)
    return body_x / safe_scale, body_y / safe_scale


def resolve_stride_direction_reference(
    frame_index: pd.Series,
    stride_body_x: pd.Series,
    stride_body_y: pd.Series,
) -> StrideDirectionReference:
    extension = pd.Series(np.sqrt((stride_body_x**2) + (stride_body_y**2)), index=stride_body_x.index).replace([np.inf, -np.inf], np.nan)
    valid_mask = extension.notna() & stride_body_x.notna() & stride_body_y.notna()
    if not valid_mask.any():
        return StrideDirectionReference(unit_x=0.0, unit_y=-1.0, frame_index=None)

    reference_index = int(extension[valid_mask].idxmax())
    reference_x = float(stride_body_x.loc[reference_index])
    reference_y = float(stride_body_y.loc[reference_index])
    magnitude = float(np.sqrt((reference_x**2) + (reference_y**2)))
    if not np.isfinite(magnitude) or magnitude <= 1e-6:
        return StrideDirectionReference(unit_x=0.0, unit_y=-1.0, frame_index=None)

    unit_x = reference_x / magnitude
    unit_y = reference_y / magnitude
    if unit_y > 0:
        unit_x *= -1.0
        unit_y *= -1.0

    reference_frame = int(pd.to_numeric(frame_index, errors="coerce").fillna(reference_index).loc[reference_index])
    return StrideDirectionReference(unit_x=unit_x, unit_y=unit_y, frame_index=reference_frame)


def decompose_body_frame_series(
    body_x: pd.Series,
    body_y: pd.Series,
    reference: StrideDirectionReference,
) -> tuple[pd.Series, pd.Series]:
    forward = (body_x * reference.unit_x) + (body_y * reference.unit_y)
    lateral = (body_x * (-reference.unit_y)) + (body_y * reference.unit_x)
    return forward, lateral


def build_row_body_frame_axes(
    pelvis_center: tuple[float, float],
    shoulder_center: tuple[float, float],
) -> tuple[tuple[float, float], tuple[float, float]] | None:
    torso_dx = float(shoulder_center[0] - pelvis_center[0])
    torso_dy = float(shoulder_center[1] - pelvis_center[1])
    torso_norm = float(np.sqrt((torso_dx**2) + (torso_dy**2)))
    if not np.isfinite(torso_norm) or torso_norm <= 1e-6:
        return None
    unit_y = (torso_dx / torso_norm, torso_dy / torso_norm)
    unit_x = (-unit_y[1], unit_y[0])
    return unit_x, unit_y


def project_row_point_to_body_frame(
    point: tuple[float, float],
    pelvis_center: tuple[float, float],
    unit_x: tuple[float, float],
    unit_y: tuple[float, float],
    body_scale_px: float,
    mirror_x: bool,
) -> tuple[float, float] | None:
    if not np.isfinite(float(body_scale_px)) or float(body_scale_px) <= 1e-6:
        return None

    relative_x = float(point[0] - pelvis_center[0])
    relative_y = float(point[1] - pelvis_center[1])
    body_x = (relative_x * unit_x[0]) + (relative_y * unit_x[1])
    body_y = (relative_x * unit_y[0]) + (relative_y * unit_y[1])
    if mirror_x:
        body_x *= -1.0
    return body_x / float(body_scale_px), body_y / float(body_scale_px)
