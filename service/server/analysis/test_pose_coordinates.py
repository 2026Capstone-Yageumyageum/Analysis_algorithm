from __future__ import annotations

from pose_coordinates import normalize_frame_point


def test_normalize_frame_point_uses_same_axis_scale_for_portrait_video() -> None:
    x, y = normalize_frame_point(540.0, 960.0, 1080, 1920)

    assert x == 0.28125
    assert y == 0.5


def test_normalize_frame_point_uses_same_axis_scale_for_landscape_video() -> None:
    x, y = normalize_frame_point(960.0, 540.0, 1920, 1080)

    assert x == 0.5
    assert y == 0.28125
