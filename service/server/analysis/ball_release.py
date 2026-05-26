from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pandas as pd


MIN_CONFIDENCE = 0.05
ARM_SPEED_GATE_MAX_RATIO = 0.78
ARM_SPEED_GATE_PERCENTILE = 72


def estimate_ball_release_event(
    *,
    video_path: Path,
    keypoints: pd.DataFrame,
    normalized_pose: pd.DataFrame,
    intervals: dict[str, dict[str, Any]],
    fallback_release_event: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Estimate release as midpoint between the last in-hand frame and first ball-out frame."""
    if keypoints.empty or normalized_pose.empty or "frame_index" not in keypoints.columns:
        return None
    if not video_path.exists():
        return None

    throwing_side = str(normalized_pose["throwing_side"].iloc[0] if "throwing_side" in normalized_pose else "right")
    wrist = f"{throwing_side}_wrist"
    elbow = f"{throwing_side}_elbow"
    required_columns = [
        "frame_index",
        f"{wrist}_x_smooth",
        f"{wrist}_y_smooth",
        f"{wrist}_confidence",
        f"{elbow}_x_smooth",
        f"{elbow}_y_smooth",
        f"{elbow}_confidence",
    ]
    if any(column not in keypoints.columns for column in required_columns):
        return None

    acceleration = intervals.get("acceleration")
    if acceleration is None:
        return None
    search_start = int(math.floor(float(acceleration["startFrame"])))
    fallback_release_frame = _safe_float((fallback_release_event or {}).get("frame"), fallback=float(acceleration["endFrame"]))
    search_end = int(math.ceil(min(_max_frame(keypoints), fallback_release_frame + 12)))
    if search_end <= search_start:
        return None

    keypoint_lookup = keypoints.sort_values("frame_index").set_index(keypoints["frame_index"].astype(int), drop=False)
    candidate_frames = [
        frame
        for frame in range(search_start, search_end + 1)
        if frame in keypoint_lookup.index
    ]
    if len(candidate_frames) < 2:
        return None
    arm_speed_gate = _build_arm_speed_gate(
        normalized_pose=normalized_pose,
        candidate_frames=candidate_frames,
        wrist=wrist,
        elbow=elbow,
    )

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        return None
    try:
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        compact_candidates: dict[int, dict[str, Any]] = {}
        trajectory_candidates: dict[int, dict[str, Any]] = {}
        for frame_index in candidate_frames:
            row = keypoint_lookup.loc[frame_index]
            if isinstance(row, pd.DataFrame):
                row = row.iloc[0]
            previous_row = _previous_keypoint_row(keypoint_lookup, frame_index)
            candidates = _detect_detached_ball_candidates(
                capture=capture,
                frame_index=frame_index,
                row=row,
                previous_row=previous_row,
                width=width,
                height=height,
                wrist=wrist,
                elbow=elbow,
            )
            if candidates.get("compact") is not None and _passes_arm_speed_gate(arm_speed_gate, frame_index):
                compact_candidates[frame_index] = candidates["compact"]
            if candidates.get("trajectory") is not None and _passes_arm_speed_gate(arm_speed_gate, frame_index):
                trajectory_candidates[frame_index] = candidates["trajectory"]
    finally:
        capture.release()

    exit_frame, frame_candidates = _select_release_candidate_map(
        candidate_frames,
        compact_candidates=compact_candidates,
        trajectory_candidates=trajectory_candidates,
    )
    if exit_frame is None:
        return None
    before_frame = _previous_frame(candidate_frames, exit_frame)
    if before_frame is None:
        before_frame = _previous_available_frame(keypoint_lookup, exit_frame)
    if before_frame is None:
        return None

    candidate = frame_candidates[exit_frame]
    return {
        "beforeFrame": before_frame,
        "exitFrame": exit_frame,
        "releaseFrame": round((before_frame + exit_frame) / 2.0, 4),
        "method": "ball_exit_midpoint_v1",
        "source": "bright_or_motion_aligned_ball_blob",
        "detector": {
            "status": "ready",
            "throwingSide": throwing_side,
            "searchStartFrame": search_start,
            "searchEndFrame": search_end,
            "ballFrame": exit_frame,
            "detectorKind": candidate.get("detectorKind"),
            "ballCenter": {
                "x": round(float(candidate["x"]), 2),
                "y": round(float(candidate["y"]), 2),
            },
            "ballWristDistancePx": round(float(candidate["distance"]), 2),
            "confidence": round(float(candidate["confidence"]), 4),
        },
    }


def _build_arm_speed_gate(
    *,
    normalized_pose: pd.DataFrame,
    candidate_frames: list[int],
    wrist: str,
    elbow: str,
) -> dict[int, bool]:
    if normalized_pose.empty or "frame_index" not in normalized_pose.columns:
        return {frame: True for frame in candidate_frames}

    frames = pd.to_numeric(normalized_pose["frame_index"], errors="coerce").to_numpy(dtype=float)
    wrist_speed = pd.to_numeric(
        normalized_pose.get(f"{wrist}_speed_body", pd.Series(np.zeros(len(normalized_pose)))),
        errors="coerce",
    ).fillna(0.0)
    elbow_speed = pd.to_numeric(
        normalized_pose.get(f"{elbow}_speed_body", pd.Series(np.zeros(len(normalized_pose)))),
        errors="coerce",
    ).fillna(0.0)
    arm_speed = ((wrist_speed * 0.72) + (elbow_speed * 0.28)).to_numpy(dtype=float)
    valid = np.isfinite(frames) & np.isfinite(arm_speed)
    if not valid.any():
        return {frame: True for frame in candidate_frames}

    sampled_speeds = []
    for frame in candidate_frames:
        sampled_speeds.append(float(np.interp(float(frame), frames[valid], arm_speed[valid])))
    finite_speeds = np.asarray([speed for speed in sampled_speeds if math.isfinite(speed)], dtype=float)
    if len(finite_speeds) < 3:
        return {frame: True for frame in candidate_frames}

    max_speed = float(np.max(finite_speeds))
    if max_speed <= 1e-9:
        return {frame: True for frame in candidate_frames}
    percentile_speed = float(np.percentile(finite_speeds, ARM_SPEED_GATE_PERCENTILE))
    threshold = max(percentile_speed, max_speed * ARM_SPEED_GATE_MAX_RATIO)
    return {
        frame: speed >= threshold
        for frame, speed in zip(candidate_frames, sampled_speeds)
    }


def _passes_arm_speed_gate(arm_speed_gate: dict[int, bool], frame_index: int) -> bool:
    return bool(arm_speed_gate.get(frame_index, True))


def _detect_detached_ball_candidates(
    *,
    capture: cv2.VideoCapture,
    frame_index: int,
    row: pd.Series,
    previous_row: pd.Series | None,
    width: int,
    height: int,
    wrist: str,
    elbow: str,
) -> dict[str, dict[str, Any] | None]:
    wrist_confidence = _safe_float(row.get(f"{wrist}_confidence"), fallback=0.0)
    elbow_confidence = _safe_float(row.get(f"{elbow}_confidence"), fallback=0.0)
    if min(wrist_confidence, elbow_confidence) < MIN_CONFIDENCE:
        return {"compact": None, "trajectory": None}

    wrist_x = _safe_float(row.get(f"{wrist}_x_smooth"), fallback=0.0) * width
    wrist_y = _safe_float(row.get(f"{wrist}_y_smooth"), fallback=0.0) * height
    elbow_x = _safe_float(row.get(f"{elbow}_x_smooth"), fallback=0.0) * width
    elbow_y = _safe_float(row.get(f"{elbow}_y_smooth"), fallback=0.0) * height
    forearm_px = max(40.0, math.dist((wrist_x, wrist_y), (elbow_x, elbow_y)))
    roi_radius = int(max(220, min(560, forearm_px * 3.6)))
    x0 = max(0, int(wrist_x - roi_radius))
    x1 = min(width, int(wrist_x + roi_radius))
    y0 = max(0, int(wrist_y - roi_radius))
    y1 = min(height, int(wrist_y + roi_radius))
    if x1 <= x0 or y1 <= y0:
        return {"compact": None, "trajectory": None}

    capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
    ok, frame = capture.read()
    if not ok:
        return {"compact": None, "trajectory": None}

    crop = frame[y0:y1, x0:x1]
    mask = _white_ball_mask(crop)
    component_count, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, 8)
    compact_best: dict[str, Any] | None = None
    trajectory_best: dict[str, Any] | None = None
    wrist_velocity = _wrist_velocity_unit(row, previous_row, wrist=wrist, width=width, height=height)
    for component_index in range(1, component_count):
        compact_candidate = _compact_component_candidate(
            component_index=component_index,
            stats=stats,
            centroids=centroids,
            origin_x=x0,
            origin_y=y0,
            wrist_x=wrist_x,
            wrist_y=wrist_y,
            forearm_px=forearm_px,
        )
        if compact_candidate is not None and (
            compact_best is None or compact_candidate["score"] > compact_best["score"]
        ):
            compact_best = compact_candidate

        trajectory_candidate = _trajectory_component_candidate(
            component_index=component_index,
            stats=stats,
            centroids=centroids,
            origin_x=x0,
            origin_y=y0,
            wrist_x=wrist_x,
            wrist_y=wrist_y,
            forearm_px=forearm_px,
            wrist_velocity=wrist_velocity,
        )
        if trajectory_candidate is not None and (
            trajectory_best is None or trajectory_candidate["score"] > trajectory_best["score"]
        ):
            trajectory_best = trajectory_candidate
    return {"compact": compact_best, "trajectory": trajectory_best}


def _detect_detached_ball_candidate(
    *,
    capture: cv2.VideoCapture,
    frame_index: int,
    row: pd.Series,
    width: int,
    height: int,
    wrist: str,
    elbow: str,
) -> dict[str, Any] | None:
    """Compatibility wrapper for diagnostics that expect a single best candidate."""
    candidates = _detect_detached_ball_candidates(
        capture=capture,
        frame_index=frame_index,
        row=row,
        previous_row=None,
        width=width,
        height=height,
        wrist=wrist,
        elbow=elbow,
    )
    return candidates.get("compact") or candidates.get("trajectory")


def _white_ball_mask(crop: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array([0, 0, 155], dtype=np.uint8), np.array([180, 105, 255], dtype=np.uint8))
    mask = cv2.medianBlur(mask, 3)
    return mask


def _compact_component_candidate(
    *,
    component_index: int,
    stats: np.ndarray,
    centroids: np.ndarray,
    origin_x: int,
    origin_y: int,
    wrist_x: float,
    wrist_y: float,
    forearm_px: float,
) -> dict[str, Any] | None:
    area = float(stats[component_index, cv2.CC_STAT_AREA])
    box_w = float(stats[component_index, cv2.CC_STAT_WIDTH])
    box_h = float(stats[component_index, cv2.CC_STAT_HEIGHT])
    if area < 24 or area > 520:
        return None
    if box_w < 3 or box_h < 3 or box_w > 42 or box_h > 42:
        return None
    aspect_ratio = max(box_w, box_h) / max(1.0, min(box_w, box_h))
    if aspect_ratio > 1.9:
        return None

    center_x = float(origin_x + centroids[component_index][0])
    center_y = float(origin_y + centroids[component_index][1])
    distance = math.dist((center_x, center_y), (wrist_x, wrist_y))
    detach_distance = max(58.0, forearm_px * 1.15)
    upward_delta = wrist_y - center_y
    minimum_upward_delta = max(16.0, forearm_px * 0.25)
    if distance < detach_distance or upward_delta < minimum_upward_delta:
        return None

    fill_ratio = area / max(1.0, box_w * box_h)
    if fill_ratio < 0.28:
        return None
    score = area * fill_ratio + upward_delta * 0.35 + distance * 0.12 - (aspect_ratio - 1.0) * 12.0
    confidence = min(1.0, max(0.0, (fill_ratio * 0.5) + min(distance / 220.0, 1.0) * 0.3 + min(upward_delta / 180.0, 1.0) * 0.2))
    return {
        "x": center_x,
        "y": center_y,
        "distance": distance,
        "area": area,
        "score": score,
        "confidence": confidence,
        "detectorKind": "compact_blob",
    }


def _trajectory_component_candidate(
    *,
    component_index: int,
    stats: np.ndarray,
    centroids: np.ndarray,
    origin_x: int,
    origin_y: int,
    wrist_x: float,
    wrist_y: float,
    forearm_px: float,
    wrist_velocity: tuple[float, float, float] | None,
) -> dict[str, Any] | None:
    if wrist_velocity is None:
        return None
    velocity_x, velocity_y, velocity_px = wrist_velocity
    if velocity_px < 12.0:
        return None

    area = float(stats[component_index, cv2.CC_STAT_AREA])
    box_w = float(stats[component_index, cv2.CC_STAT_WIDTH])
    box_h = float(stats[component_index, cv2.CC_STAT_HEIGHT])
    if area < 24 or area > 1200:
        return None
    if box_w < 3 or box_h < 3 or box_w > 90 or box_h > 90:
        return None

    aspect_ratio = max(box_w, box_h) / max(1.0, min(box_w, box_h))
    if aspect_ratio > 6.0:
        return None
    fill_ratio = area / max(1.0, box_w * box_h)
    if fill_ratio < 0.15:
        return None

    center_x = float(origin_x + centroids[component_index][0])
    center_y = float(origin_y + centroids[component_index][1])
    distance = math.dist((center_x, center_y), (wrist_x, wrist_y))
    if distance < max(45.0, forearm_px * 0.75):
        return None
    if distance > max(340.0, forearm_px * 3.8):
        return None

    upward_delta = wrist_y - center_y
    if upward_delta < -max(90.0, forearm_px * 1.4):
        return None

    alignment = ((center_x - wrist_x) * velocity_x + (center_y - wrist_y) * velocity_y) / max(1.0, distance)
    if alignment < 0.42:
        return None

    score = (
        area * fill_ratio
        + min(distance, 360.0) * 0.18
        + max(0.0, upward_delta) * 0.08
        + alignment * 140.0
        - max(0.0, aspect_ratio - 4.0) * 8.0
    )
    confidence = min(
        1.0,
        max(
            0.0,
            fill_ratio * 0.25
            + alignment * 0.35
            + min(distance / 260.0, 1.0) * 0.18
            + min(max(0.0, upward_delta) / 180.0, 1.0) * 0.12
            + min(area / 220.0, 1.0) * 0.10,
        ),
    )
    return {
        "x": center_x,
        "y": center_y,
        "distance": distance,
        "area": area,
        "score": score,
        "confidence": confidence,
        "detectorKind": "motion_aligned_blob",
        "motionAlignment": alignment,
        "wristVelocityPx": velocity_px,
    }


def _select_release_candidate_map(
    candidate_frames: list[int],
    *,
    compact_candidates: dict[int, dict[str, Any]],
    trajectory_candidates: dict[int, dict[str, Any]],
) -> tuple[int | None, dict[int, dict[str, Any]]]:
    compact_exit_frame = _first_stable_detached_frame(candidate_frames, compact_candidates)
    trajectory_exit_frame = _first_stable_detached_frame(candidate_frames, trajectory_candidates)
    if compact_exit_frame is not None and trajectory_exit_frame is not None:
        if compact_exit_frame <= trajectory_exit_frame:
            return compact_exit_frame, compact_candidates
        return trajectory_exit_frame, trajectory_candidates
    if compact_exit_frame is not None:
        return compact_exit_frame, compact_candidates
    if trajectory_exit_frame is not None:
        return trajectory_exit_frame, trajectory_candidates
    return None, {}


def _first_stable_detached_frame(
    candidate_frames: list[int],
    frame_candidates: dict[int, dict[str, Any]],
) -> int | None:
    for index, frame_index in enumerate(candidate_frames):
        candidate = frame_candidates.get(frame_index)
        if candidate is None:
            continue
        next_frame = candidate_frames[index + 1] if index + 1 < len(candidate_frames) else None
        next_candidate = frame_candidates.get(next_frame) if next_frame is not None else None
        if next_candidate is not None and _is_position_consistent_candidate(candidate, next_candidate):
            return frame_index
    return None


def _is_position_consistent_candidate(candidate: dict[str, Any], next_candidate: dict[str, Any]) -> bool:
    x = _safe_float(candidate.get("x"), fallback=float("nan"))
    y = _safe_float(candidate.get("y"), fallback=float("nan"))
    next_x = _safe_float(next_candidate.get("x"), fallback=float("nan"))
    next_y = _safe_float(next_candidate.get("y"), fallback=float("nan"))
    if not all(math.isfinite(value) for value in (x, y, next_x, next_y)):
        return False
    jump = math.dist((x, y), (next_x, next_y))
    distance = max(
        1.0,
        _safe_float(candidate.get("distance"), fallback=1.0),
        _safe_float(next_candidate.get("distance"), fallback=1.0),
    )
    return jump <= max(70.0, min(150.0, distance * 0.55))


def _previous_frame(candidate_frames: list[int], frame_index: int) -> int | None:
    previous = None
    for candidate_frame in candidate_frames:
        if candidate_frame >= frame_index:
            return previous
        previous = candidate_frame
    return previous


def _previous_keypoint_row(keypoint_lookup: pd.DataFrame, frame_index: int) -> pd.Series | None:
    for previous_frame in (frame_index - 2, frame_index - 1):
        if previous_frame not in keypoint_lookup.index:
            continue
        row = keypoint_lookup.loc[previous_frame]
        if isinstance(row, pd.DataFrame):
            return row.iloc[0]
        return row
    return None


def _previous_available_frame(keypoint_lookup: pd.DataFrame, frame_index: int) -> int | None:
    frame_values = pd.to_numeric(keypoint_lookup["frame_index"], errors="coerce").dropna()
    previous_values = frame_values[frame_values < frame_index]
    if previous_values.empty:
        return None
    return int(previous_values.max())


def _wrist_velocity_unit(
    row: pd.Series,
    previous_row: pd.Series | None,
    *,
    wrist: str,
    width: int,
    height: int,
) -> tuple[float, float, float] | None:
    if previous_row is None:
        return None
    wrist_x = _safe_float(row.get(f"{wrist}_x_smooth"), fallback=0.0) * width
    wrist_y = _safe_float(row.get(f"{wrist}_y_smooth"), fallback=0.0) * height
    previous_x = _safe_float(previous_row.get(f"{wrist}_x_smooth"), fallback=wrist_x / max(1, width)) * width
    previous_y = _safe_float(previous_row.get(f"{wrist}_y_smooth"), fallback=wrist_y / max(1, height)) * height
    velocity_x = wrist_x - previous_x
    velocity_y = wrist_y - previous_y
    velocity_px = math.hypot(velocity_x, velocity_y)
    if velocity_px <= 1e-9:
        return None
    return velocity_x / velocity_px, velocity_y / velocity_px, velocity_px


def _max_frame(keypoints: pd.DataFrame) -> int:
    values = pd.to_numeric(keypoints["frame_index"], errors="coerce").dropna()
    if values.empty:
        return 0
    return int(values.max())


def _safe_float(value: Any, *, fallback: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if math.isfinite(parsed) else fallback
