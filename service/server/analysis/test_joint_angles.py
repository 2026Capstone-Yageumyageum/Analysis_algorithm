from __future__ import annotations

import math
from types import SimpleNamespace

import pandas as pd

from analysis.coaching_feedback_utils import PosePoint
from analysis.joint_angles import ANGLE_RULES, arm_slot_degrees, elbow_flexion_degrees
from analysis.phase_metrics import build_phase_metrics


def _p(x: float, y: float) -> PosePoint:
    return PosePoint(x=x, y=y, frame=0)


def test_elbow_flexion_right_angle() -> None:
    # 팔꿈치를 원점에 두고 어깨는 위로, 손목은 옆으로 → 직각
    assert abs(elbow_flexion_degrees(_p(0.0, 3.0), _p(0.0, 0.0), _p(4.0, 0.0)) - 90.0) < 1e-9


def test_elbow_flexion_straight_arm_is_180() -> None:
    # 어깨-팔꿈치-손목이 일직선이면 180°(곧게 편 팔)
    assert abs(elbow_flexion_degrees(_p(0.0, 2.0), _p(0.0, 1.0), _p(0.0, 0.0)) - 180.0) < 1e-9


def test_arm_slot_along_torso_axis_is_zero() -> None:
    # 상완이 몸통축(+y) 방향이면 0°
    assert abs(arm_slot_degrees(_p(0.0, 0.0), _p(0.0, 1.0)) - 0.0) < 1e-9


def test_arm_slot_perpendicular_is_90() -> None:
    assert abs(arm_slot_degrees(_p(0.0, 0.0), _p(1.0, 0.0)) - 90.0) < 1e-9


def test_arm_slot_hanging_down_is_180() -> None:
    assert abs(arm_slot_degrees(_p(0.0, 0.0), _p(0.0, -1.0)) - 180.0) < 1e-9


def test_arm_slot_is_mirror_invariant() -> None:
    # 좌완/우완과 정규화 단계의 mirror_x에 무관해야 한다
    right = arm_slot_degrees(_p(0.0, 0.0), _p(1.0, 1.0))
    left = arm_slot_degrees(_p(0.0, 0.0), _p(-1.0, 1.0))
    assert abs(right - left) < 1e-9


def _rotate_scale(point: PosePoint, theta: float, scale: float) -> PosePoint:
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    return PosePoint(
        x=scale * ((point.x * cos_t) - (point.y * sin_t)),
        y=scale * ((point.x * sin_t) + (point.y * cos_t)),
        frame=point.frame,
    )


def test_elbow_flexion_survives_rotation_and_scale() -> None:
    """정규화가 각도를 보존한다는 것이 이 설계의 근거다. 반드시 검증한다.

    body-frame 정규화는 골반 중심 이동 + 몸통축 직교 회전 + 단일 스칼라 나눗셈이다.
    회전은 직교 변환이고 스케일은 등방이므로 각도는 바뀌지 않아야 한다.
    """
    shoulder, elbow, wrist = _p(0.0, 3.0), _p(0.0, 0.0), _p(4.0, 0.0)
    before = elbow_flexion_degrees(shoulder, elbow, wrist)
    after = elbow_flexion_degrees(
        _rotate_scale(shoulder, 0.7, 2.5),
        _rotate_scale(elbow, 0.7, 2.5),
        _rotate_scale(wrist, 0.7, 2.5),
    )
    assert abs(before - after) < 1e-9


def test_elbow_flexion_is_mirror_invariant() -> None:
    # 정규화 단계의 mirror_x는 x 부호를 뒤집는다. 사이각은 그대로여야 한다.
    normal = elbow_flexion_degrees(_p(0.0, 3.0), _p(0.0, 0.0), _p(4.0, 0.0))
    mirrored = elbow_flexion_degrees(_p(0.0, 3.0), _p(0.0, 0.0), _p(-4.0, 0.0))
    assert abs(normal - mirrored) < 1e-9


def test_degenerate_points_yield_none() -> None:
    # 관절이 겹쳐 보이면 각도가 정의되지 않는다
    assert elbow_flexion_degrees(_p(0.0, 0.0), _p(0.0, 0.0), _p(1.0, 0.0)) is None
    assert elbow_flexion_degrees(_p(1.0, 0.0), _p(0.0, 0.0), _p(0.0, 0.0)) is None
    assert arm_slot_degrees(_p(0.0, 0.0), _p(0.0, 0.0)) is None


def _phases() -> SimpleNamespace:
    # phase_frame()은 intervals[phase]의 startFrame/endFrame만 본다.
    return SimpleNamespace(
        intervals={
            "windup": {"startFrame": 0, "endFrame": 10, "label": "와인드업"},
            "leg_lift": {"startFrame": 10, "endFrame": 20, "label": "레그 리프트"},
            "stride": {"startFrame": 20, "endFrame": 30, "label": "스트라이드"},
            "acceleration": {"startFrame": 30, "endFrame": 40, "label": "가속"},
            "follow_through": {"startFrame": 40, "endFrame": 50, "label": "팔로스루"},
        }
    )


def _arm_pose(slot_deg: float, flex_deg: float = 90.0) -> pd.DataFrame:
    """암슬롯과 굽힘각이 정확히 지정한 값이 되도록 만든 포즈 테이블.

    모든 프레임이 같은 자세라 어느 시점을 재도 같은 값이 나온다.
    joint_name()의 throwing_side 기본값이 right이므로 right_* 컬럼을 채운다.
    confidence 컬럼을 두지 않으면 point_at_frame이 신뢰도 게이팅을 건너뛴다.
    """
    slot = math.radians(slot_deg)
    elbow_x, elbow_y = math.sin(slot), math.cos(slot)
    # 팔꿈치 → 어깨 방향에서 flex_deg만큼 돌린 곳에 손목을 둔다.
    to_shoulder = math.atan2(-elbow_y, -elbow_x)
    wrist_dir = to_shoulder + math.radians(flex_deg)
    wrist_x, wrist_y = elbow_x + math.cos(wrist_dir), elbow_y + math.sin(wrist_dir)
    return pd.DataFrame(
        [
            {
                "frame_index": float(f),
                "right_shoulder_body_x": 0.0,
                "right_shoulder_body_y": 0.0,
                "right_elbow_body_x": elbow_x,
                "right_elbow_body_y": elbow_y,
                "right_wrist_body_x": wrist_x,
                "right_wrist_body_y": wrist_y,
            }
            for f in range(0, 51)
        ]
    )


def _metric(metrics: list, key: str) -> dict:
    return next(m for m in metrics if m["key"] == key)


def test_angle_rules_cover_four_phases_with_two_metrics_each() -> None:
    assert len(ANGLE_RULES) == 8
    assert {r.phase for r in ANGLE_RULES} == {
        "leg_lift",
        "stride",
        "acceleration",
        "follow_through",
    }
    assert len({r.category for r in ANGLE_RULES}) == 8


def test_build_phase_metrics_returns_axis_and_angle_metrics() -> None:
    metrics = build_phase_metrics(_arm_pose(70.0), _arm_pose(70.0), _phases(), _phases())
    assert len(metrics) == 16
    degrees = [m for m in metrics if m["unit"] == "degree"]
    assert len(degrees) == 8
    # key는 앱이 리스트 렌더 key로 쓴다. 16개 전부 고유해야 한다.
    assert len({m["key"] for m in metrics}) == 16


def test_angle_metrics_never_report_favorable() -> None:
    """각도에는 유리한 방향이 없다. 굽힘각도 암슬롯도 '클수록 유리'가 성립하지 않는다."""
    metrics = build_phase_metrics(
        _arm_pose(50.0), _arm_pose(90.0), _phases(), _phases(), comparison_mode="best_pitch"
    )
    for metric in metrics:
        if metric["unit"] == "degree":
            assert metric["favorableDirection"] is None
            assert metric["status"] != "favorable"


def test_arm_slot_difference_at_threshold_is_good() -> None:
    # 암슬롯 허용은 10.0° — 정확히 10° 차이는 good
    metrics = build_phase_metrics(_arm_pose(80.0), _arm_pose(70.0), _phases(), _phases())
    slot = _metric(metrics, "acceleration_arm_slot")
    assert slot["unit"] == "degree"
    assert abs(slot["difference"] - 10.0) < 1e-9
    assert slot["status"] == "good"


def test_arm_slot_difference_past_threshold_is_warn() -> None:
    metrics = build_phase_metrics(_arm_pose(80.1), _arm_pose(70.0), _phases(), _phases())
    slot = _metric(metrics, "acceleration_arm_slot")
    assert slot["status"] == "warn"


def test_status_uses_rounded_value_not_raw() -> None:
    """원값으로 판정하면 화면의 숫자와 뱃지가 어긋난다.

    원 차이 10.04°는 보내는 값(소수 첫째 자리)으로는 10.0°이고 허용도 10.0°이므로
    good이어야 한다. 원값으로 판정하면 warn이 나와, 사용자는 '10.0 / 허용 10.0'인데
    주의라고 적힌 화면을 보게 된다.
    """
    metrics = build_phase_metrics(_arm_pose(80.04), _arm_pose(70.0), _phases(), _phases())
    slot = _metric(metrics, "acceleration_arm_slot")
    assert slot["difference"] == 10.0
    assert slot["status"] == "good"


def test_angle_values_are_rounded_to_one_decimal() -> None:
    metrics = build_phase_metrics(_arm_pose(70.0), _arm_pose(70.0), _phases(), _phases())
    for metric in metrics:
        if metric["unit"] == "degree" and metric["userValue"] is not None:
            assert metric["userValue"] == round(metric["userValue"], 1)
            assert metric["threshold"] == round(metric["threshold"], 1)


def test_missing_arm_joints_yield_unavailable_angles() -> None:
    empty = pd.DataFrame([{"frame_index": float(f)} for f in range(0, 51)])
    metrics = build_phase_metrics(empty, empty, _phases(), _phases())
    degrees = [m for m in metrics if m["unit"] == "degree"]
    assert len(degrees) == 8
    assert all(m["status"] == "unavailable" for m in degrees)
    assert all(m["userValue"] is None and m["difference"] is None for m in degrees)


def test_angle_metric_carries_label_why_and_frame() -> None:
    metrics = build_phase_metrics(_arm_pose(70.0), _arm_pose(70.0), _phases(), _phases())
    slot = _metric(metrics, "stride_arm_slot")
    assert slot["phase"] == "stride"
    assert slot["label"]
    assert slot["why"]
    assert slot["userFrame"] == 30  # stride 20~30의 100% 지점
