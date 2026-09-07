from __future__ import annotations

import math

from analysis.coaching_feedback_utils import PosePoint
from analysis.joint_angles import arm_slot_degrees, elbow_flexion_degrees


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
