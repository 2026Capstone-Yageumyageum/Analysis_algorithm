"""관절 각도.

기존 구간 지표는 전부 "관절 한 점의 좌표"에서 나온다. 각도는 세 점이 필요해
AxisRule 구조로는 만들 수 없어 별도 모듈로 둔다.

body-frame 정규화는 골반 중심 이동 + 몸통축 직교 회전 + 단일 스칼라(body_scale)
나눗셈이다. 회전은 직교 변환이고 스케일은 등방이므로 각도는 보존된다. 그래서
좌표값과 달리 도(°) 자체가 의미를 갖는다.
"""

from __future__ import annotations

import math

from analysis.coaching_feedback_utils import PosePoint

# 벡터 길이가 이보다 짧으면 각도가 정의되지 않는다(관절이 겹쳐 보이는 경우).
DEGENERATE = 1e-9


def elbow_flexion_degrees(shoulder: PosePoint, elbow: PosePoint, wrist: PosePoint) -> float | None:
    """어깨·팔꿈치·손목이 이루는 사이각(0~180°). 180°면 팔이 곧게 편 상태."""
    upper_x, upper_y = shoulder.x - elbow.x, shoulder.y - elbow.y
    fore_x, fore_y = wrist.x - elbow.x, wrist.y - elbow.y
    if math.hypot(upper_x, upper_y) < DEGENERATE or math.hypot(fore_x, fore_y) < DEGENERATE:
        return None
    # acos(dot / |a||b|)는 두 벡터가 거의 나란할 때 수치적으로 불안정하다.
    cross = (upper_x * fore_y) - (upper_y * fore_x)
    dot = (upper_x * fore_x) + (upper_y * fore_y)
    return math.degrees(math.atan2(abs(cross), dot))


def arm_slot_degrees(shoulder: PosePoint, elbow: PosePoint) -> float | None:
    """상완(어깨→팔꿈치)이 몸통축에서 벌어진 각(0~180°).

    0°는 몸통축 방향, 90°는 몸통과 직각(사이드암), 180°는 아래로 내린 상태.

    수평이 아니라 몸통축을 기준으로 잡는 것이 핵심이다. 정규화 좌표계의 y축이 이미
    골반 중심 → 어깨 중심이므로 상체가 기울어도 자동으로 보정된다. 수평 기준으로 재면
    상체를 많이 숙이는 투수는 실제 암슬롯이 같아도 매번 다른 값이 나온다.

    x에 절댓값을 쓰는 이유는 좌완/우완에 따라, 그리고 정규화 단계의 mirror_x에 따라
    부호가 뒤집히기 때문이다.
    """
    upper_x, upper_y = elbow.x - shoulder.x, elbow.y - shoulder.y
    if math.hypot(upper_x, upper_y) < DEGENERATE:
        return None
    return math.degrees(math.atan2(abs(upper_x), upper_y))
