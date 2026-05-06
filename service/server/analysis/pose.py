from __future__ import annotations

import csv
import math
from io import StringIO
from pathlib import Path
from typing import Any

import cv2


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


def extract_keypoints_csv_text(video_path: Path, max_frames: int | None = None) -> tuple[str, dict[str, Any]]:
    """Extract MediaPipe pose landmarks and serialize the project CSV schema.

    If MediaPipe is not installed, this returns a deterministic placeholder CSV
    with confidence 0.0 so the API contract is still runnable during integration.
    """
    try:
        return _extract_with_mediapipe(video_path, max_frames=max_frames)
    except ModuleNotFoundError:
        return _extract_placeholder(video_path, reason="mediapipe_not_installed", max_frames=max_frames)


def _extract_with_mediapipe(video_path: Path, max_frames: int | None = None) -> tuple[str, dict[str, Any]]:
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
    rows: list[dict[str, Any]] = []
    previous_values = _default_joint_values()

    with pose_module.Pose(
        static_image_mode=False,
        model_complexity=1,
        enable_segmentation=False,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    ) as pose:
        frame_index = 0
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            if max_frames is not None and frame_index >= max_frames:
                break

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
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
                    x = _safe_finite_float(landmark.x, fallback=previous_x)
                    y = _safe_finite_float(landmark.y, fallback=previous_y)
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
            frame_index += 1

    capture.release()
    _append_smoothed_columns(rows)
    csv_text = _rows_to_csv_text(rows)
    return csv_text, {
        "poseModel": "MediaPipe Pose",
        "status": "ready",
        "frameCount": len(rows),
        "warning": None,
    }


def _extract_placeholder(
    video_path: Path,
    reason: str,
    max_frames: int | None = None,
) -> tuple[str, dict[str, Any]]:
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise ValueError(f"영상 파일을 열 수 없습니다: {video_path.name}")
    fps = _safe_positive_float(capture.get(cv2.CAP_PROP_FPS), fallback=30.0)
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    capture.release()

    usable_count = min(frame_count, max_frames) if max_frames is not None else frame_count
    rows: list[dict[str, Any]] = []
    for frame_index in range(max(0, usable_count)):
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
        "warning": reason,
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
