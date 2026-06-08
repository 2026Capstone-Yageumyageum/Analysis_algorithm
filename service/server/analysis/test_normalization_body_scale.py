from __future__ import annotations

import numpy as np
import pandas as pd

from normalization import build_body_frame_pose


def _pose_table_with_changing_camera_scale() -> pd.DataFrame:
    rows = []
    for frame, lower_y in enumerate(np.linspace(2.0, 4.0, 9)):
        rows.append(
            {
                "frame_index": frame,
                "time_sec": frame / 30.0,
                "nose_x_smooth": 0.0,
                "nose_y_smooth": -0.2,
                "left_shoulder_x_smooth": -0.1,
                "left_shoulder_y_smooth": 0.0,
                "right_shoulder_x_smooth": 0.1,
                "right_shoulder_y_smooth": 0.0,
                "left_hip_x_smooth": -0.1,
                "left_hip_y_smooth": 1.0,
                "right_hip_x_smooth": 0.1,
                "right_hip_y_smooth": 1.0,
                "left_ankle_x_smooth": -0.1,
                "left_ankle_y_smooth": lower_y,
                "right_ankle_x_smooth": 0.1,
                "right_ankle_y_smooth": lower_y,
                "left_foot_index_x_smooth": -0.1,
                "left_foot_index_y_smooth": lower_y,
                "right_foot_index_x_smooth": 0.1,
                "right_foot_index_y_smooth": lower_y,
                "left_shoulder_confidence": 0.95,
                "right_shoulder_confidence": 0.95,
                "left_hip_confidence": 0.95,
                "right_hip_confidence": 0.95,
            }
        )
    return pd.DataFrame(rows)


def test_body_scale_stays_fixed_when_raw_scale_changes() -> None:
    # Given: a rear-view pose sequence where apparent body height changes as if
    # the pitcher moved toward the camera during stride.
    keypoints = _pose_table_with_changing_camera_scale()

    # When: body-frame normalization builds the analysis table.
    normalized = build_body_frame_pose(keypoints)

    # Then: raw scale can vary, but the actual body_scale used by normalized
    # coordinates stays fixed for the whole video.
    raw_scale = normalized.table["raw_body_scale"].to_numpy()
    body_scale = normalized.table["body_scale"].to_numpy()
    assert np.ptp(raw_scale) > 0.5
    assert np.ptp(body_scale) == 0.0


if __name__ == "__main__":
    test_body_scale_stays_fixed_when_raw_scale_changes()
    print("ok")
