from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from analysis.coaching_feedback import build_coaching_feedback


def _phases() -> SimpleNamespace:
    intervals = {
        "windup": {"phase": "windup", "label": "와인드업", "startFrame": 0, "endFrame": 10},
        "leg_lift": {"phase": "leg_lift", "label": "레그 리프트", "startFrame": 10, "endFrame": 20},
        "stride": {"phase": "stride", "label": "스트라이드", "startFrame": 20, "endFrame": 30},
        "acceleration": {"phase": "acceleration", "label": "가속", "startFrame": 30, "endFrame": 40},
        "follow_through": {"phase": "follow_through", "label": "팔로스루", "startFrame": 40, "endFrame": 50},
    }
    return SimpleNamespace(intervals=intervals, warnings=[])


def _pose_table(*, knee_y: float, foot_x: float, elbow_y: float, wrist_y: float) -> pd.DataFrame:
    rows = []
    for frame in (0, 10, 20, 30, 40, 50):
        rows.append(
            {
                "frame_index": frame,
                "throwing_side": "right",
                "stride_side": "left",
                "right_wrist_body_x": 0.10,
                "right_wrist_body_y": wrist_y,
                "right_wrist_confidence": 0.95,
                "right_elbow_body_x": 0.08,
                "right_elbow_body_y": elbow_y,
                "right_elbow_confidence": 0.95,
                "left_knee_body_x": 0.10,
                "left_knee_body_y": knee_y,
                "left_knee_confidence": 0.95,
                "left_foot_index_body_x": foot_x,
                "left_foot_index_body_y": -0.90,
                "left_foot_index_confidence": 0.95,
            }
        )
    return pd.DataFrame(rows)


def test_build_coaching_feedback_adds_metric_specific_tips() -> None:
    user_pose = _pose_table(knee_y=0.55, foot_x=0.55, elbow_y=0.20, wrist_y=0.12)
    pro_pose = _pose_table(knee_y=0.85, foot_x=0.25, elbow_y=0.45, wrist_y=0.45)
    phase_scores = [
        {"phase": "acceleration", "label": "가속", "score": 55},
        {"phase": "stride", "label": "스트라이드", "score": 72},
    ]
    release = {
        "timing": {"differencePercent": 22},
        "point": {"difference": 0.31, "message": "릴리즈 포인트가 선수보다 낮게 형성됩니다."},
    }

    feedback = build_coaching_feedback(
        user_pose=user_pose,
        pro_pose=pro_pose,
        user_phases=_phases(),
        pro_phases=_phases(),
        phase_scores=phase_scores,
        release=release,
    )

    bad_messages = [item["message"] for item in feedback["bad"]]
    assert set(feedback) == {"good", "bad"}
    # good은 선수와 '일치한 지표'에만 생성되므로, 차이가 큰 이 지표들은 good에 없어야 한다.
    good_messages = [item["message"] for item in feedback["good"]]
    assert not any("디딤 무릎 높이" in m for m in good_messages)
    assert not any("투구 팔꿈치" in m for m in good_messages)
    assert any("발 착지 이후 릴리즈" in message for message in bad_messages)
    assert any("디딤 무릎 높이" in message for message in bad_messages)
    assert any("투구 팔꿈치" in message for message in bad_messages)
    # 정밀화: 측정 근거(나 vs 선수 값)가 메시지에 포함된다.
    assert any("측정값" in message and "선수" in message for message in bad_messages)
    assert len(feedback["bad"]) <= 8
    assert set(feedback["bad"][0]["evidence"]) == {
        "proFrame",
        "userFrame",
        "proPhasePercent",
        "userPhasePercent",
        "differencePercent",
        "difference",
    }


def test_build_coaching_feedback_emits_good_for_matched() -> None:
    # 사용자와 선수 자세가 거의 일치하고 구간 점수가 높으면 '잘된 점'이 생성된다.
    pose = _pose_table(knee_y=0.85, foot_x=0.25, elbow_y=0.45, wrist_y=0.45)
    phase_scores = [{"phase": "acceleration", "label": "가속", "score": 88}]
    release = {
        "timing": {"differencePercent": 2},
        "point": {"difference": 0.05, "message": "릴리즈 포인트가 안정적입니다."},
    }

    feedback = build_coaching_feedback(
        user_pose=pose,
        pro_pose=pose,
        user_phases=_phases(),
        pro_phases=_phases(),
        phase_scores=phase_scores,
        release=release,
    )

    good_messages = [item["message"] for item in feedback["good"]]
    assert feedback["good"]
    assert len(feedback["good"]) <= 4
    assert any(("매우 유사" in m) or ("거의 일치" in m) for m in good_messages)


if __name__ == "__main__":
    test_build_coaching_feedback_adds_metric_specific_tips()
    test_build_coaching_feedback_emits_good_for_matched()
    print("ok")
