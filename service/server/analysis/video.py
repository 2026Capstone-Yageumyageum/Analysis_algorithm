from __future__ import annotations

import math
from pathlib import Path

import cv2


def inspect_video(video_path: Path) -> dict[str, float | int]:
    """Read basic video metadata with OpenCV."""
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise ValueError(f"영상 파일을 열 수 없습니다: {video_path.name}")

    frame_count = _safe_non_negative_int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = _safe_positive_float(capture.get(cv2.CAP_PROP_FPS), fallback=0.0)
    width = _safe_non_negative_int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = _safe_non_negative_int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    capture.release()

    duration_sec = frame_count / fps if frame_count > 0 and fps > 0 else 0.0
    return {
        "frameCount": frame_count,
        "fps": round(fps, 3),
        "width": width,
        "height": height,
        "durationSec": round(duration_sec, 3),
    }


def _safe_positive_float(value, fallback: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if math.isfinite(parsed) and parsed > 0 else fallback


def _safe_non_negative_int(value) -> int:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0
    if not math.isfinite(parsed) or parsed < 0:
        return 0
    return int(parsed)
