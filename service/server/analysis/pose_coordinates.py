from __future__ import annotations


def normalize_frame_point(pixel_x: float, pixel_y: float, frame_width: int, frame_height: int) -> tuple[float, float]:
    scale = max(1.0, float(frame_width), float(frame_height))
    return pixel_x / scale, pixel_y / scale
