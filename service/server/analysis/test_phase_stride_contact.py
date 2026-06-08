from __future__ import annotations

import math

import pandas as pd

from phase import detect_pitch_phases


def _smoothstep(value: float) -> float:
    clamped = max(0.0, min(1.0, value))
    return clamped * clamped * (3.0 - (2.0 * clamped))


def _y2_like_pose_table() -> pd.DataFrame:
    frames = list(range(241))
    observed_stride_foot_y = {
        135: 0.5967,
        136: 0.5915,
        137: 0.5890,
        138: 0.5890,
        139: 0.5890,
        140: 0.5903,
        141: 0.5925,
        142: 0.5962,
        143: 0.6040,
        144: 0.6149,
        145: 0.6295,
        146: 0.6446,
        147: 0.6611,
        148: 0.6785,
        149: 0.6953,
        150: 0.7100,
        151: 0.7293,
        152: 0.7469,
        153: 0.7621,
        154: 0.7772,
        155: 0.7924,
        156: 0.8042,
        157: 0.8153,
        158: 0.8249,
        159: 0.8334,
        160: 0.8408,
        161: 0.8469,
        162: 0.8516,
        163: 0.8550,
        164: 0.8573,
        165: 0.8588,
        166: 0.8588,
        167: 0.8588,
        168: 0.8575,
        169: 0.8557,
        170: 0.8520,
        171: 0.8468,
        172: 0.8409,
        173: 0.8338,
        174: 0.8259,
        175: 0.8194,
        176: 0.8141,
        177: 0.8091,
        178: 0.8043,
        179: 0.7997,
        180: 0.7971,
        181: 0.7943,
        182: 0.7880,
        183: 0.7832,
        184: 0.7732,
        185: 0.7563,
        186: 0.7563,
        187: 0.7563,
        188: 0.7875,
        189: 0.8252,
        190: 0.8607,
        191: 0.8976,
        192: 0.8976,
        193: 0.8976,
    }
    rows = []
    for frame in frames:
        foot_y = observed_stride_foot_y.get(frame, 0.59)
        if frame > 193:
            foot_y = 0.88 + (0.20 * _smoothstep((frame - 215) / 10.0))
        knee_y = 0.72 - (0.30 * math.exp(-0.5 * ((frame - 140) / 8.0) ** 2))
        rows.append(
            {
                "frame_index": frame,
                "throwing_side": "right",
                "left_foot_index_image_y": foot_y,
                "left_foot_index_confidence": 0.90,
                "left_knee_image_y": knee_y,
                "left_knee_confidence": 0.95,
                "right_wrist_speed_body": 0.1 + (2.0 * math.exp(-0.5 * ((frame - 204) / 7.0) ** 2)),
                "right_elbow_speed_body": 0.1 + (1.0 * math.exp(-0.5 * ((frame - 204) / 9.0) ** 2)),
                "right_wrist_body_x": 0.1,
                "right_wrist_body_y": 0.1,
                "left_shoulder_confidence": 0.95,
                "right_shoulder_confidence": 0.95,
                "left_hip_confidence": 0.95,
                "right_hip_confidence": 0.95,
                "right_knee_confidence": 0.95,
            }
        )
    return pd.DataFrame(rows)


def test_stride_contact_uses_release_bounded_final_landing() -> None:
    # Given: a y2-like stride foot signal with an early local low point around
    # 163 and the actual foot contact around 191, plus a lower follow-through
    # foot point after release that must not be selected.
    pose_table = _y2_like_pose_table()
    release_event = {
        "beforeFrame": 204,
        "exitFrame": 205,
        "releaseFrame": 204.5,
        "method": "ball_exit_midpoint_v1",
    }

    # When: phase detection receives the release event available in the final
    # service/preview pass.
    phases = detect_pitch_phases(pose_table, release_event_override=release_event)

    # Then: stride ends at the release-bounded foot contact, not the earlier
    # in-air local low point and not a post-release follow-through point.
    stride_frame = phases.representative_frames["stride"]
    assert stride_frame is not None
    assert 190 <= float(stride_frame) <= 193


if __name__ == "__main__":
    test_stride_contact_uses_release_bounded_final_landing()
    print("ok")
