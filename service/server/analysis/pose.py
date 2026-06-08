from __future__ import annotations

import csv
import math
from io import StringIO
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from analysis.pose_coordinates import normalize_frame_point


JOINTS = (
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
IMPUTED_JOINTS = (
    "left_elbow",
    "right_elbow",
    "left_wrist",
    "right_wrist",
    "left_knee",
    "right_knee",
    "left_ankle",
    "right_ankle",
    "left_foot_index",
    "right_foot_index",
)


def build_csv_columns() -> list[str]:
    columns = ["frame_index", "time_sec"]
    for joint in JOINTS:
        columns.extend([f"{joint}_x", f"{joint}_y", f"{joint}_confidence"])
    for joint in IMPUTED_JOINTS:
        columns.append(f"{joint}_imputed_flag")
    for joint in JOINTS:
        columns.extend([f"{joint}_x_smooth", f"{joint}_y_smooth"])
    columns.extend(
        [
            "pitcher_com_x_smooth",
            "pitcher_com_y_smooth",
            "pitcher_detected",
            "normalised_frame",
            "no_missing_frames_flag",
            "smooth_com_flag",
        ]
    )
    return columns


CSV_COLUMNS = build_csv_columns()


def extract_skeleton_data_csv_text(
    video_path: Path,
    max_frames: int | None = None,
    *,
    sample_evenly: bool = False,
    start_sec: float | None = None,
    end_sec: float | None = None,
    focus_motion: bool = False,
) -> tuple[str, dict[str, Any]]:
    """Extract MediaPipe pose landmarks and serialize the project CSV schema.

    If MediaPipe is not installed, this returns a deterministic placeholder CSV
    with confidence 0.0 so the API contract is still runnable during integration.
    """
    try:
        return _extract_with_mediapipe(
            video_path,
            max_frames=max_frames,
            sample_evenly=sample_evenly,
            start_sec=start_sec,
            end_sec=end_sec,
            focus_motion=focus_motion,
        )
    except ModuleNotFoundError:
        return _extract_placeholder(
            video_path,
            reason="mediapipe_not_installed",
            max_frames=max_frames,
            sample_evenly=sample_evenly,
            start_sec=start_sec,
            end_sec=end_sec,
            focus_motion=focus_motion,
        )


def _extract_with_mediapipe(
    video_path: Path,
    max_frames: int | None = None,
    *,
    sample_evenly: bool = False,
    start_sec: float | None = None,
    end_sec: float | None = None,
    focus_motion: bool = False,
) -> tuple[str, dict[str, Any]]:
    import mediapipe as mp  # type: ignore[import-not-found]

    pose_module = mp.solutions.pose
    landmark_map = {
        "nose": pose_module.PoseLandmark.NOSE,
        "left_shoulder": pose_module.PoseLandmark.LEFT_SHOULDER,
        "right_shoulder": pose_module.PoseLandmark.RIGHT_SHOULDER,
        "left_elbow": pose_module.PoseLandmark.LEFT_ELBOW,
        "right_elbow": pose_module.PoseLandmark.RIGHT_ELBOW,
        "left_wrist": pose_module.PoseLandmark.LEFT_WRIST,
        "right_wrist": pose_module.PoseLandmark.RIGHT_WRIST,
        "left_hip": pose_module.PoseLandmark.LEFT_HIP,
        "right_hip": pose_module.PoseLandmark.RIGHT_HIP,
        "left_knee": pose_module.PoseLandmark.LEFT_KNEE,
        "right_knee": pose_module.PoseLandmark.RIGHT_KNEE,
        "left_ankle": pose_module.PoseLandmark.LEFT_ANKLE,
        "right_ankle": pose_module.PoseLandmark.RIGHT_ANKLE,
        "left_foot_index": pose_module.PoseLandmark.LEFT_FOOT_INDEX,
        "right_foot_index": pose_module.PoseLandmark.RIGHT_FOOT_INDEX,
    }

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise ValueError(f"영상 파일을 열 수 없습니다: {video_path.name}")

    fps = _safe_positive_float(capture.get(cv2.CAP_PROP_FPS), fallback=30.0)
    source_frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    start_frame, end_frame, trim_meta = _frame_range_from_seconds(
        source_frame_count=source_frame_count,
        fps=fps,
        start_sec=start_sec,
        end_sec=end_sec,
    )
    target_frame_indices = _target_frame_indices(
        source_frame_count=source_frame_count,
        max_frames=max_frames,
        sample_evenly=sample_evenly,
        start_frame=start_frame,
        end_frame=end_frame,
    )
    motion_roi = _estimate_motion_roi(video_path, target_frame_indices) if focus_motion else None
    rows: list[dict[str, Any]] = []
    previous_values = _default_joint_values()

    with pose_module.Pose(
        static_image_mode=False,
        model_complexity=1,
        enable_segmentation=False,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    ) as pose:
        for frame_index in target_frame_indices:
            if sample_evenly:
                capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            ok, frame = capture.read()
            if not ok:
                continue

            frame_height, frame_width = frame.shape[:2]
            roi_frame, roi = _crop_frame(frame, motion_roi)
            roi_x, roi_y, roi_width, roi_height = roi
            rgb = cv2.cvtColor(roi_frame, cv2.COLOR_BGR2RGB)
            result = pose.process(rgb)
            row: dict[str, Any] = {
                "frame_index": frame_index,
                "time_sec": round(frame_index / fps, 6) if fps > 0 else 0.0,
            }
            detected = result.pose_landmarks is not None
            missing_count = 0

            for joint in JOINTS:
                if detected:
                    landmark = result.pose_landmarks.landmark[landmark_map[joint]]
                    previous_x, previous_y = previous_values[joint]
                    local_x = _safe_finite_float(landmark.x, fallback=previous_x)
                    local_y = _safe_finite_float(landmark.y, fallback=previous_y)
                    x, y = normalize_frame_point(
                        roi_x + local_x * roi_width,
                        roi_y + local_y * roi_height,
                        frame_width,
                        frame_height,
                    )
                    confidence = _safe_confidence(landmark.visibility)
                    previous_values[joint] = (x, y)
                else:
                    x, y = previous_values[joint]
                    confidence = 0.0
                    missing_count += 1
                row[f"{joint}_x"] = round(x, 6)
                row[f"{joint}_y"] = round(y, 6)
                row[f"{joint}_confidence"] = round(confidence, 6)

            for joint in IMPUTED_JOINTS:
                row[f"{joint}_imputed_flag"] = not detected

            rows.append(row)

    capture.release()
    _append_smoothed_columns(rows)
    csv_text = _rows_to_csv_text(rows)
    return csv_text, {
        "poseModel": "MediaPipe Pose",
        "status": "ready",
        "frameCount": len(rows),
        "sourceFrameCount": source_frame_count,
        "sampleEvenly": sample_evenly,
        "trim": trim_meta,
        "focusMotion": focus_motion,
        "motionRoi": _roi_meta(motion_roi, source_frame_count=source_frame_count),
        "coordinateNormalization": "pixel_point_divided_by_max_frame_dimension_v1",
        "warning": None,
    }


def _extract_placeholder(
    video_path: Path,
    reason: str,
    max_frames: int | None = None,
    *,
    sample_evenly: bool = False,
    start_sec: float | None = None,
    end_sec: float | None = None,
    focus_motion: bool = False,
) -> tuple[str, dict[str, Any]]:
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise ValueError(f"영상 파일을 열 수 없습니다: {video_path.name}")
    fps = _safe_positive_float(capture.get(cv2.CAP_PROP_FPS), fallback=30.0)
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    capture.release()

    start_frame, end_frame, trim_meta = _frame_range_from_seconds(
        source_frame_count=frame_count,
        fps=fps,
        start_sec=start_sec,
        end_sec=end_sec,
    )
    target_frame_indices = _target_frame_indices(
        source_frame_count=frame_count,
        max_frames=max_frames,
        sample_evenly=sample_evenly,
        start_frame=start_frame,
        end_frame=end_frame,
    )
    rows: list[dict[str, Any]] = []
    for frame_index in target_frame_indices:
        row: dict[str, Any] = {
            "frame_index": frame_index,
            "time_sec": round(frame_index / fps, 6) if fps > 0 else 0.0,
        }
        for joint, (x, y) in _default_joint_values().items():
            row[f"{joint}_x"] = x
            row[f"{joint}_y"] = y
            row[f"{joint}_confidence"] = 0.0
        for joint in IMPUTED_JOINTS:
            row[f"{joint}_imputed_flag"] = True
        rows.append(row)

    _append_smoothed_columns(rows, detected=False)
    csv_text = _rows_to_csv_text(rows)
    return csv_text, {
        "poseModel": "placeholder",
        "status": "fallback",
        "frameCount": len(rows),
        "sourceFrameCount": frame_count,
        "sampleEvenly": sample_evenly,
        "trim": trim_meta,
        "focusMotion": focus_motion,
        "motionRoi": {"enabled": False, "reason": "placeholder"},
        "warning": reason,
    }


def _frame_range_from_seconds(
    *,
    source_frame_count: int,
    fps: float,
    start_sec: float | None,
    end_sec: float | None,
) -> tuple[int, int, dict[str, Any]]:
    start_frame = _seconds_to_start_frame(start_sec, fps)
    end_frame = _seconds_to_end_frame(end_sec, fps, source_frame_count)
    start_frame = max(0, min(start_frame, max(0, source_frame_count)))
    end_frame = max(0, min(end_frame, max(0, source_frame_count)))
    if end_frame <= start_frame:
        raise ValueError("트림 구간이 비어 있습니다. 시작초와 끝초를 다시 확인해 주세요.")

    used_frame_count = max(0, end_frame - start_frame)
    return (
        start_frame,
        end_frame,
        {
            "enabled": start_frame > 0 or end_frame < source_frame_count,
            "startSec": round(start_frame / fps, 6) if fps > 0 else 0.0,
            "endSec": round(end_frame / fps, 6) if fps > 0 else 0.0,
            "startFrame": start_frame,
            "endFrame": max(start_frame, end_frame - 1),
            "usedSourceFrameCount": used_frame_count,
            "sourceFrameCount": source_frame_count,
        },
    )


def _seconds_to_start_frame(value: float | None, fps: float) -> int:
    if value is None:
        return 0
    return int(math.floor(max(0.0, value) * fps))


def _seconds_to_end_frame(value: float | None, fps: float, fallback: int) -> int:
    if value is None:
        return fallback
    return int(math.ceil(max(0.0, value) * fps))


def _target_frame_indices(
    source_frame_count: int,
    max_frames: int | None,
    *,
    sample_evenly: bool,
    start_frame: int = 0,
    end_frame: int | None = None,
) -> list[int]:
    if source_frame_count <= 0:
        return []
    frame_start = max(0, min(start_frame, source_frame_count))
    frame_end = source_frame_count if end_frame is None else max(0, min(end_frame, source_frame_count))
    available_count = max(0, frame_end - frame_start)
    if available_count <= 0:
        return []
    if max_frames is None or max_frames >= available_count:
        return list(range(frame_start, frame_end))
    usable_count = max(1, max_frames)
    if not sample_evenly:
        return list(range(frame_start, min(frame_end, frame_start + usable_count)))
    if usable_count == 1:
        return [frame_start]
    return [
        int(round(frame_start + index * (available_count - 1) / (usable_count - 1)))
        for index in range(usable_count)
    ]


def _estimate_motion_roi(video_path: Path, frame_indices: list[int]) -> tuple[int, int, int, int] | None:
    if len(frame_indices) < 3:
        return None

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        return None

    sample_count = min(80, len(frame_indices))
    sample_positions = np.linspace(0, len(frame_indices) - 1, sample_count).round().astype(int)
    sampled_indices = [frame_indices[index] for index in sample_positions]
    previous_gray: np.ndarray | None = None
    heatmap: np.ndarray | None = None
    source_width = 0
    source_height = 0

    for frame_index in sampled_indices:
        capture.set(cv2.CAP_PROP_POS_FRAMES, int(frame_index))
        ok, frame = capture.read()
        if not ok:
            continue
        source_height, source_width = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, (320, max(1, round(320 * source_height / max(1, source_width)))))
        gray = cv2.GaussianBlur(gray, (5, 5), 0)
        if previous_gray is None:
            previous_gray = gray
            continue
        diff = cv2.absdiff(gray, previous_gray)
        _, mask = cv2.threshold(diff, 18, 255, cv2.THRESH_BINARY)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), dtype=np.uint8))
        heatmap = mask.astype(np.float32) if heatmap is None else heatmap + mask.astype(np.float32)
        previous_gray = gray

    capture.release()
    if heatmap is None or source_width <= 0 or source_height <= 0:
        return None

    heatmap = cv2.GaussianBlur(heatmap, (9, 9), 0)
    nonzero = heatmap[heatmap > 0]
    if nonzero.size == 0:
        return None
    threshold = max(float(np.percentile(nonzero, 70)), float(nonzero.mean()))
    motion_mask = (heatmap >= threshold).astype(np.uint8) * 255
    motion_mask = cv2.morphologyEx(motion_mask, cv2.MORPH_CLOSE, np.ones((7, 7), dtype=np.uint8))
    motion_mask = cv2.dilate(motion_mask, np.ones((9, 9), dtype=np.uint8), iterations=1)

    component_count, labels, stats, centroids = cv2.connectedComponentsWithStats(motion_mask, connectivity=8)
    if component_count <= 1:
        return None

    mask_height, mask_width = motion_mask.shape[:2]
    best: tuple[float, int] | None = None
    for label in range(1, component_count):
        x, y, width, height, area = stats[label]
        if area < max(20, int(mask_width * mask_height * 0.002)):
            continue
        center_x, center_y = centroids[label]
        if center_y < mask_height * 0.22:
            continue
        component_heat = float(heatmap[labels == label].sum())
        lower_weight = 1.0 + 0.45 * (center_y / max(1, mask_height))
        size_weight = 1.0 + min(1.0, height / max(1, mask_height))
        score = component_heat * lower_weight * size_weight
        if best is None or score > best[0]:
            best = (score, label)

    if best is None:
        return None

    x, y, width, height, _ = stats[best[1]]
    scale_x = source_width / max(1, mask_width)
    scale_y = source_height / max(1, mask_height)
    raw_x = int(round(x * scale_x))
    raw_y = int(round(y * scale_y))
    raw_w = int(round(width * scale_x))
    raw_h = int(round(height * scale_y))
    return _expanded_roi(raw_x, raw_y, raw_w, raw_h, source_width, source_height)


def _expanded_roi(x: int, y: int, width: int, height: int, frame_width: int, frame_height: int) -> tuple[int, int, int, int]:
    center_x = x + width / 2
    center_y = y + height / 2
    expanded_width = max(width * 2.4, frame_width * 0.20)
    expanded_height = max(height * 3.0, frame_height * 0.38)
    top_bias = expanded_height * 0.18
    left = int(round(center_x - expanded_width / 2))
    top = int(round(center_y - expanded_height / 2 - top_bias))
    right = int(round(center_x + expanded_width / 2))
    bottom = int(round(center_y + expanded_height / 2))
    left = max(0, left)
    top = max(0, top)
    right = min(frame_width, right)
    bottom = min(frame_height, bottom)
    if right - left < 32 or bottom - top < 32:
        return (0, 0, frame_width, frame_height)
    return (left, top, right, bottom)


def _crop_frame(frame: np.ndarray, roi: tuple[int, int, int, int] | None) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    frame_height, frame_width = frame.shape[:2]
    if roi is None:
        return frame, (0, 0, frame_width, frame_height)
    left, top, right, bottom = roi
    left = max(0, min(left, frame_width - 1))
    top = max(0, min(top, frame_height - 1))
    right = max(left + 1, min(right, frame_width))
    bottom = max(top + 1, min(bottom, frame_height))
    return frame[top:bottom, left:right], (left, top, right - left, bottom - top)


def _roi_meta(roi: tuple[int, int, int, int] | None, *, source_frame_count: int) -> dict[str, Any]:
    if roi is None:
        return {"enabled": False, "sourceFrameCount": source_frame_count}
    left, top, right, bottom = roi
    return {
        "enabled": True,
        "x": left,
        "y": top,
        "width": max(0, right - left),
        "height": max(0, bottom - top),
        "sourceFrameCount": source_frame_count,
    }


def _default_joint_values() -> dict[str, tuple[float, float]]:
    return {
        "nose": (0.5, 0.18),
        "left_shoulder": (0.43, 0.32),
        "right_shoulder": (0.57, 0.32),
        "left_elbow": (0.38, 0.45),
        "right_elbow": (0.62, 0.45),
        "left_wrist": (0.35, 0.58),
        "right_wrist": (0.65, 0.58),
        "left_hip": (0.45, 0.55),
        "right_hip": (0.55, 0.55),
        "left_knee": (0.43, 0.72),
        "right_knee": (0.57, 0.72),
        "left_ankle": (0.42, 0.9),
        "right_ankle": (0.58, 0.9),
        "left_foot_index": (0.41, 0.93),
        "right_foot_index": (0.59, 0.93),
    }


def _append_smoothed_columns(rows: list[dict[str, Any]], detected: bool = True) -> None:
    if not rows:
        return

    for joint in JOINTS:
        xs = [_safe_finite_float(row[f"{joint}_x"], fallback=0.0) for row in rows]
        ys = [_safe_finite_float(row[f"{joint}_y"], fallback=0.0) for row in rows]
        x_smooth = _moving_average(xs, radius=2)
        y_smooth = _moving_average(ys, radius=2)
        for row, x_value, y_value in zip(rows, x_smooth, y_smooth, strict=False):
            row[f"{joint}_x_smooth"] = round(x_value, 6)
            row[f"{joint}_y_smooth"] = round(y_value, 6)

    for normalised_frame, row in enumerate(rows):
        left_hip = (
            _safe_finite_float(row["left_hip_x_smooth"], fallback=0.0),
            _safe_finite_float(row["left_hip_y_smooth"], fallback=0.0),
        )
        right_hip = (
            _safe_finite_float(row["right_hip_x_smooth"], fallback=0.0),
            _safe_finite_float(row["right_hip_y_smooth"], fallback=0.0),
        )
        left_shoulder = (
            _safe_finite_float(row["left_shoulder_x_smooth"], fallback=0.0),
            _safe_finite_float(row["left_shoulder_y_smooth"], fallback=0.0),
        )
        right_shoulder = (
            _safe_finite_float(row["right_shoulder_x_smooth"], fallback=0.0),
            _safe_finite_float(row["right_shoulder_y_smooth"], fallback=0.0),
        )
        row["pitcher_com_x_smooth"] = round((left_hip[0] + right_hip[0] + left_shoulder[0] + right_shoulder[0]) / 4, 6)
        row["pitcher_com_y_smooth"] = round((left_hip[1] + right_hip[1] + left_shoulder[1] + right_shoulder[1]) / 4, 6)
        row["pitcher_detected"] = detected and any(_safe_confidence(row[f"{joint}_confidence"]) > 0 for joint in JOINTS)
        row["normalised_frame"] = normalised_frame
        row["no_missing_frames_flag"] = all(_safe_confidence(row[f"{joint}_confidence"]) > 0 for joint in JOINTS)
        row["smooth_com_flag"] = True


def _moving_average(values: list[float], radius: int) -> list[float]:
    output: list[float] = []
    for index in range(len(values)):
        start = max(0, index - radius)
        end = min(len(values), index + radius + 1)
        output.append(sum(values[start:end]) / max(1, end - start))
    return output


def _rows_to_csv_text(rows: list[dict[str, Any]]) -> str:
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue()


def _safe_positive_float(value: Any, fallback: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if math.isfinite(parsed) and parsed > 0 else fallback


def _safe_finite_float(value: Any, fallback: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if math.isfinite(parsed) else fallback


def _safe_confidence(value: Any) -> float:
    parsed = _safe_finite_float(value, fallback=0.0)
    return min(1.0, max(0.0, parsed))
