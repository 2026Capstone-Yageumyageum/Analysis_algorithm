from __future__ import annotations

import math

import pandas as pd

import numpy as np

from phase import _choose_stride_foot_landing, detect_pitch_phases


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


def test_stride_contact_ignores_in_air_plateau_without_release_event() -> None:
    """릴리즈 검출이 꺼진 기본 경로에서도 공중 평탄부를 착지로 오인하면 안 된다.

    BALL_RELEASE_DETECTION은 기본값이 꺼짐이라 운영에서는 release_event_override가
    없는 이 경로가 돈다. 그런데 같은 신호의 163~167에는 공중 평탄부가 있다 —
    디딤발을 앞으로 뻗는 중이라 수직 속도만 0에 가까울 뿐 아직 땅에 닿지 않았고,
    그 뒤 발은 다시 올라간다(185에서 0.7563). 진짜 착지는 191 근처다.

    수직 속도만 보는 판정은 이 둘을 구분하지 못한다.
    """
    phases = detect_pitch_phases(_y2_like_pose_table())

    stride_frame = phases.representative_frames["stride"]
    assert stride_frame is not None
    assert 188 <= float(stride_frame) <= 194, f"공중 평탄부를 착지로 잡았다: {stride_frame}"


def _forward_reach_pose_table() -> pd.DataFrame:
    """디딤발이 앞으로 뻗으며 착지하는 신호.

    수직 궤적은 포물선 후반부처럼 감속한다(ease-out) — 절반쯤 진행한 시점에
    이미 하강폭의 86%를 넘고 수직 속도도 느려진다. 하지만 발은 그때까지도
    수평으로 계속 앞으로 이동 중이고, 실제 착지는 70프레임이다.

    수직 정보만 보는 판정은 여기서 45 근처를 착지로 잡는다.
    """
    lift, contact, total = 20, 70, 120
    rows = []
    for frame in range(total):
        if frame <= lift:
            foot_y, foot_x = 0.60, 0.30
        elif frame <= contact:
            t = (frame - lift) / (contact - lift)
            foot_y = 0.60 + (0.25 * (1.0 - ((1.0 - t) ** 3)))  # 빠르게 내려왔다가 감속
            foot_x = 0.30 + (0.40 * t)  # 착지까지 일정하게 앞으로 이동
        else:
            foot_y, foot_x = 0.85, 0.70  # 착지 후에는 멈춘다
        rows.append(
            {
                "frame_index": frame,
                "left_foot_index_image_x": foot_x,
                "left_foot_index_image_y": foot_y,
                "left_foot_index_confidence": 0.95,
            }
        )
    return pd.DataFrame(rows)


def test_stride_contact_waits_for_forward_motion_to_stop() -> None:
    """착지는 '앞으로 가던 발이 멈추는 것'이다.

    수직 속도만 보면 포물선 후반부에서 발이 아직 앞으로 뻗는 중인데도 감속만으로
    착지 조건을 통과한다. 실측에서 "착지까지 50% 진행됐을 때 스트라이드가 끝난다"고
    관측된 것이 이 경우다.
    """
    pose_table = _forward_reach_pose_table()
    candidates = np.arange(20, 108)

    landing = _choose_stride_foot_landing(
        pose_table, candidates, "left_foot_index", fallback=90
    )

    assert 68 <= landing <= 74, f"앞으로 뻗는 중을 착지로 잡았다: {landing}"


if __name__ == "__main__":
    test_stride_contact_uses_release_bounded_final_landing()
    test_stride_contact_ignores_in_air_plateau_without_release_event()
    test_stride_contact_waits_for_forward_motion_to_stop()
    print("ok")
