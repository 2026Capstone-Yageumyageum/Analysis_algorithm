from __future__ import annotations

from analysis.resampling_preview import POSE_DISTANCE_SIGMA


def test_pose_distance_sigma_uses_strict_pro_similarity_scale() -> None:
    assert POSE_DISTANCE_SIGMA == 0.25
