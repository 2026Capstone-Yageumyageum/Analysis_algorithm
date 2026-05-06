from __future__ import annotations

import math
from typing import Any


def compute_tof_speed(payload: dict[str, Any], detected_fps: float | None = None) -> dict[str, Any]:
    """Compute rear-view time-of-flight velocity from manual frame markers."""
    release_frame = _parse_int(payload.get("releaseFrame"))
    arrival_frame = _parse_int(payload.get("arrivalFrame"))
    fps = _parse_float(payload.get("fps"), _positive_fallback(detected_fps, 60.0))
    target_distance_m = _parse_float(payload.get("targetDistanceM"), 16.0)
    release_extension_m = _parse_float(payload.get("releaseExtensionM"), 1.5)

    if release_frame is None or arrival_frame is None:
        return {
            "status": "manual_required",
            "speedKmh": None,
            "message": "releaseFrame과 arrivalFrame이 필요합니다.",
        }
    if arrival_frame <= release_frame:
        return {
            "status": "invalid",
            "speedKmh": None,
            "message": "arrivalFrame은 releaseFrame보다 커야 합니다.",
        }
    if fps <= 0:
        return {
            "status": "invalid",
            "speedKmh": None,
            "message": "fps는 0보다 커야 합니다.",
        }

    effective_distance_m = target_distance_m - release_extension_m
    if effective_distance_m <= 0:
        return {
            "status": "invalid",
            "speedKmh": None,
            "message": "targetDistanceM - releaseExtensionM 값이 0보다 커야 합니다.",
        }

    frame_delta = arrival_frame - release_frame
    flight_time_sec = frame_delta / fps
    speed_mps = effective_distance_m / flight_time_sec
    speed_kmh = speed_mps * 3.6
    return {
        "status": "ready",
        "speedKmh": round(speed_kmh, 2),
        "speedMps": round(speed_mps, 3),
        "releaseFrame": release_frame,
        "arrivalFrame": arrival_frame,
        "frameDelta": frame_delta,
        "fps": fps,
        "targetDistanceM": target_distance_m,
        "releaseExtensionM": release_extension_m,
        "effectiveDistanceM": round(effective_distance_m, 3),
        "flightTimeSec": round(flight_time_sec, 6),
    }


def _parse_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_float(value: Any, fallback: float) -> float:
    fallback_value = _finite_fallback(fallback)
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return fallback_value
    return parsed if math.isfinite(parsed) else fallback_value


def _positive_fallback(value: Any, fallback: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if math.isfinite(parsed) and parsed > 0 else fallback


def _finite_fallback(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    return parsed if math.isfinite(parsed) else 0.0
