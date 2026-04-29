from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pandas as pd

from analysis_algorithm.alignment.phase_dtw import sample_aligned_pairs
from analysis_algorithm.normalization.body_frame import build_body_frame_axes, normalize_point_series_to_body_frame
from analysis_algorithm.normalization.body_scale import apply_body_scale_normalization, midpoint
from analysis_algorithm.schema import JOINT_NAMES, SKELETON_EDGES


CANONICAL_FPS = 60.0
DISPLAY_PRE_ROLL_FRAMES = 100
DISPLAY_POST_ROLL_FRAMES = 120
CONFIDENCE_THRESHOLD = 0.25


def build_motion_table(
    label: str,
    keypoints_df: pd.DataFrame,
    features_df: pd.DataFrame,
    metadata: dict[str, object],
    phase_frames: dict[str, int | None],
    fps: float,
) -> pd.DataFrame:
    df = keypoints_df.copy()
    body_scale_result = apply_body_scale_normalization(df)
    pelvis_center_x = midpoint(df["left_hip_x_smooth"], df["right_hip_x_smooth"])
    pelvis_center_y = midpoint(df["left_hip_y_smooth"], df["right_hip_y_smooth"])
    shoulder_center_x = midpoint(df["left_shoulder_x_smooth"], df["right_shoulder_x_smooth"])
    shoulder_center_y = midpoint(df["left_shoulder_y_smooth"], df["right_shoulder_y_smooth"])
    unit_x_x, unit_x_y, unit_y_x, unit_y_y = build_body_frame_axes(
        pelvis_center_x=pelvis_center_x,
        pelvis_center_y=pelvis_center_y,
        shoulder_center_x=shoulder_center_x,
        shoulder_center_y=shoulder_center_y,
    )
    mirror_x = str(metadata.get("throwing_side")) == "left"
    leg_lift_frame = int(phase_frames.get("leg_lift") or 0)
    leg_lift_time = frame_time_for_index(df, leg_lift_frame, fps)
    normalised_frame = ((df["time_sec"] - leg_lift_time) * CANONICAL_FPS).round().astype(int)

    table = pd.DataFrame(
        {
            "source_label": label,
            "frame_index": df["frame_index"].astype(int),
            "time_sec": df["time_sec"],
            "normalised_frame": normalised_frame,
            "normalised_time_sec": normalised_frame / CANONICAL_FPS,
            "phase": assign_phase_labels(df["frame_index"].astype(int), phase_frames),
            "display_window_flag": normalised_frame.between(-DISPLAY_PRE_ROLL_FRAMES, DISPLAY_POST_ROLL_FRAMES).astype(int),
            "leg_lift_frame": leg_lift_frame,
            "throwing_side": str(metadata.get("throwing_side") or ""),
            "stride_side": str(metadata.get("stride_side") or ""),
            "body_scale_px": body_scale_result.body_scale_px,
            "pelvis_center_x_px": pelvis_center_x,
            "pelvis_center_y_px": pelvis_center_y,
        }
    )

    for joint_name in JOINT_NAMES:
        body_x, body_y = normalize_point_series_to_body_frame(
            df[f"{joint_name}_x_smooth"],
            df[f"{joint_name}_y_smooth"],
            pelvis_center_x,
            pelvis_center_y,
            unit_x_x,
            unit_x_y,
            unit_y_x,
            unit_y_y,
            body_scale_result.body_scale_px,
            mirror_x=mirror_x,
        )
        table[f"{joint_name}_body_x"] = body_x
        table[f"{joint_name}_body_y"] = body_y
        table[f"{joint_name}_confidence"] = pd.to_numeric(df[f"{joint_name}_confidence"], errors="coerce").fillna(0.0)

    for column in (
        "throwing_wrist_body_x",
        "throwing_wrist_body_y",
        "throwing_wrist_forward_body",
        "throwing_wrist_lateral_body",
        "stride_foot_forward_body",
        "stride_foot_lateral_body",
        "stride_knee_lift_body_scale",
        "throwing_elbow_angle_deg",
        "body_trunk_tilt_canonical_deg",
        "shoulder_tilt_canonical_deg",
        "pelvis_tilt_canonical_deg",
        "throwing_wrist_speed_body_scale_per_sec",
    ):
        if column in features_df.columns:
            table[column] = features_df[column]

    return table.sort_values("normalised_frame").reset_index(drop=True)


def render_normalized_overlay_video(
    left_table: pd.DataFrame,
    right_table: pd.DataFrame,
    output_path: Path,
    left_label: str = "pro",
    right_label: str = "user",
) -> bool:
    frame_size = (960, 720)
    common_frames = resolve_common_normalised_frames([left_table, right_table])
    if not common_frames:
        return False

    writer = open_video_writer(output_path, fps=CANONICAL_FPS, frame_size=frame_size)
    colors = [(55, 125, 235), (235, 120, 55)]
    try:
        for normalised_frame in common_frames:
            canvas = np.full((frame_size[1], frame_size[0], 3), 248, dtype=np.uint8)
            put_text(canvas, "Normalized 2D Skeleton Overlay", (34, 48), 0.9)
            put_text(canvas, f"normalised_frame {normalised_frame} | leg_lift = 0", (34, 84), 0.58, color=(75, 75, 75))
            draw_legend(canvas, [left_label, right_label], colors)
            for table, color in zip((left_table, right_table), colors):
                row = row_for_normalised_frame(table, normalised_frame)
                if row is not None:
                    draw_skeleton_row(canvas, row, center=(480, 420), scale=155.0, color=color)
            writer.write(canvas)
    finally:
        writer.release()
    return output_path.exists()


def render_dtw_overlay_video(
    left_table: pd.DataFrame,
    right_table: pd.DataFrame,
    aligned_pairs: list[list[int]] | list[tuple[int, int]],
    output_path: Path,
    left_label: str = "A",
    right_label: str = "B",
    max_output_frames: int = 180,
) -> bool:
    selected_pairs = sample_aligned_pairs(aligned_pairs, max_output_frames=max_output_frames)
    if not selected_pairs:
        return False

    frame_size = (960, 720)
    left_lookup = build_frame_row_lookup(left_table)
    right_lookup = build_frame_row_lookup(right_table)
    writer = open_video_writer(output_path, fps=18.0, frame_size=frame_size)
    colors = [(55, 125, 235), (235, 120, 55)]
    try:
        for pair_index, (left_frame, right_frame) in enumerate(selected_pairs, start=1):
            left_row = left_lookup.get(int(left_frame))
            right_row = right_lookup.get(int(right_frame))
            if left_row is None or right_row is None:
                continue
            canvas = np.full((frame_size[1], frame_size[0], 3), 248, dtype=np.uint8)
            put_text(canvas, "Phase-DTW Normalized Overlay", (34, 48), 0.9)
            put_text(
                canvas,
                f"A frame {left_frame} ({int(left_row['normalised_frame']):+d}) | B frame {right_frame} ({int(right_row['normalised_frame']):+d})",
                (34, 84),
                0.56,
                color=(75, 75, 75),
            )
            put_text(canvas, f"DTW pair {pair_index}/{len(selected_pairs)}", (34, 118), 0.52, color=(95, 95, 95))
            draw_legend(canvas, [left_label, right_label], colors, y=154)
            draw_skeleton_row(canvas, left_row, center=(480, 420), scale=155.0, color=colors[0])
            draw_skeleton_row(canvas, right_row, center=(480, 420), scale=155.0, color=colors[1])
            writer.write(canvas)
    finally:
        writer.release()
    return output_path.exists()


def open_video_writer(output_path: Path, fps: float, frame_size: tuple[int, int]) -> cv2.VideoWriter:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(output_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, frame_size)
    if not writer.isOpened():
        raise RuntimeError(f"Could not open video writer: {output_path}")
    return writer


def frame_time_for_index(keypoints_df: pd.DataFrame, frame_index: int, fps: float) -> float:
    rows = keypoints_df[keypoints_df["frame_index"].astype(int) == int(frame_index)]
    if not rows.empty and "time_sec" in rows.columns:
        value = pd.to_numeric(rows.iloc[0]["time_sec"], errors="coerce")
        if pd.notna(value):
            return float(value)
    return float(frame_index / fps)


def assign_phase_labels(frame_index: pd.Series, phase_frames: dict[str, int | None]) -> pd.Series:
    leg_lift = int(phase_frames.get("leg_lift") or 0)
    stride = int(phase_frames.get("stride") or leg_lift)
    release = int(phase_frames.get("release") or stride)
    follow = int(phase_frames.get("follow_through") or release)
    labels: list[str] = []
    for value in frame_index.astype(int):
        if value < leg_lift:
            labels.append("setup")
        elif value < stride:
            labels.append("leg_lift_to_stride")
        elif value < release:
            labels.append("stride_to_release")
        elif value < follow:
            labels.append("release_to_follow")
        else:
            labels.append("follow_through")
    return pd.Series(labels, index=frame_index.index)


def resolve_common_normalised_frames(tables: list[pd.DataFrame]) -> list[int]:
    ranges: list[tuple[int, int]] = []
    for table in tables:
        values = table["normalised_frame"].dropna().astype(int)
        if values.empty:
            continue
        ranges.append((int(values.min()), int(values.max())))
    if len(ranges) != len(tables):
        return []
    start = max(max(frame_range[0] for frame_range in ranges), -DISPLAY_PRE_ROLL_FRAMES)
    end = min(min(frame_range[1] for frame_range in ranges), DISPLAY_POST_ROLL_FRAMES)
    return [] if end < start else list(range(start, end + 1))


def row_for_normalised_frame(motion_table: pd.DataFrame, normalised_frame: int) -> pd.Series | None:
    if motion_table.empty:
        return None
    offsets = (motion_table["normalised_frame"].astype(int) - int(normalised_frame)).abs()
    if offsets.empty:
        return None
    return motion_table.loc[int(offsets.idxmin())]


def build_frame_row_lookup(motion_table: pd.DataFrame) -> dict[int, pd.Series]:
    if motion_table.empty or "frame_index" not in motion_table.columns:
        return {}
    deduped = motion_table.drop_duplicates(subset=["frame_index"], keep="first").copy()
    return {int(frame_index): row for frame_index, row in deduped.set_index("frame_index").iterrows()}


def draw_skeleton_row(
    canvas: np.ndarray,
    row: pd.Series,
    center: tuple[int, int],
    scale: float,
    color: tuple[int, int, int],
) -> None:
    for start_name, end_name in SKELETON_EDGES:
        start_point = projected_joint(row, start_name, center, scale)
        end_point = projected_joint(row, end_name, center, scale)
        if start_point is not None and end_point is not None:
            cv2.line(canvas, start_point, end_point, color, 4, cv2.LINE_AA)
    for joint_name in JOINT_NAMES:
        point = projected_joint(row, joint_name, center, scale)
        if point is None:
            continue
        confidence = float(row.get(f"{joint_name}_confidence", 0.0) or 0.0)
        joint_color = (25, 25, 25) if confidence >= CONFIDENCE_THRESHOLD else (185, 185, 185)
        cv2.circle(canvas, point, 6, joint_color, -1, cv2.LINE_AA)


def projected_joint(row: pd.Series, joint_name: str, center: tuple[int, int], scale: float) -> tuple[int, int] | None:
    x_value = row.get(f"{joint_name}_body_x")
    y_value = row.get(f"{joint_name}_body_y")
    confidence = float(row.get(f"{joint_name}_confidence", 0.0) or 0.0)
    if confidence < 0.05 or pd.isna(x_value) or pd.isna(y_value):
        return None
    return (int(round(center[0] + float(x_value) * scale)), int(round(center[1] - float(y_value) * scale)))


def draw_legend(
    canvas: np.ndarray,
    labels: list[str],
    colors: list[tuple[int, int, int]],
    y: int = 124,
) -> None:
    x = 38
    for label, color in zip(labels, colors):
        cv2.circle(canvas, (x, y), 7, color, -1, cv2.LINE_AA)
        put_text(canvas, label, (x + 14, y + 7), 0.55, color=(45, 45, 45))
        x += 150


def put_text(
    canvas: np.ndarray,
    text: str,
    position: tuple[int, int],
    scale: float,
    color: tuple[int, int, int] = (25, 25, 25),
) -> None:
    cv2.putText(canvas, text, position, cv2.FONT_HERSHEY_SIMPLEX, scale, color, 2, cv2.LINE_AA)
