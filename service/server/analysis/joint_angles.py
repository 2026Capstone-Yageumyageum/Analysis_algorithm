"""관절 각도.

기존 구간 지표는 전부 "관절 한 점의 좌표"에서 나온다. 각도는 세 점이 필요해
AxisRule 구조로는 만들 수 없어 별도 모듈로 둔다.

body-frame 정규화는 골반 중심 이동 + 몸통축 직교 회전 + 단일 스칼라(body_scale)
나눗셈이다. 회전은 직교 변환이고 스케일은 등방이므로 각도는 보존된다. 그래서
좌표값과 달리 도(°) 자체가 의미를 갖는다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

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


@dataclass(frozen=True)
class AngleRule:
    """각도 지표 한 개의 규칙.

    관절 역할은 kind가 정한다 — 굽힘각은 어깨·팔꿈치·손목, 암슬롯은 어깨·팔꿈치.
    percent는 전부 기존 AXIS_RULES가 이미 쓰는 시점이다. 새 시점을 만들면 같은
    구간 안에서도 "이 순간 보기"가 지표마다 다른 프레임으로 튄다.
    """

    phase: str
    kind: str  # "elbow_flexion" | "arm_slot"
    percent: float
    threshold: float
    category: str
    metric_label: str
    why: str


ELBOW_FLEXION = "elbow_flexion"
ARM_SLOT = "arm_slot"

# 임계값 15°/10°는 코칭 통념에 기반한 판단값이다. 기존 축 지표의 임계값과 마찬가지로
# 라벨링된 데이터셋에서 나온 값이 아니므로, 실기기에서 보면서 여기서 조정한다.
ANGLE_RULES = (
    AngleRule(
        "leg_lift", ELBOW_FLEXION, 100.0, 15.0, "leg_lift_elbow_flexion", "팔꿈치 굽힘각",
        "레그 리프트 시점의 팔 접힘은 이후 팔 스윙의 출발 자세를 정합니다.",
    ),
    AngleRule(
        "leg_lift", ARM_SLOT, 100.0, 10.0, "leg_lift_arm_slot", "암슬롯(상완 기울기)",
        "이 시점의 팔 높이가 흔들리면 이후 동작 전체가 따라 흔들립니다.",
    ),
    AngleRule(
        "stride", ELBOW_FLEXION, 100.0, 15.0, "stride_elbow_flexion", "팔꿈치 굽힘각",
        "디딤발이 닿는 순간의 팔 접힘은 팔 스윙이 늦지 않았는지 보여줍니다.",
    ),
    AngleRule(
        "stride", ARM_SLOT, 100.0, 10.0, "stride_arm_slot", "암슬롯(상완 기울기)",
        "디딤발 착지 때 팔이 올라와 있어야 합니다. 늦으면 어깨에 부담이 몰립니다.",
    ),
    AngleRule(
        "acceleration", ELBOW_FLEXION, 85.0, 15.0, "acceleration_elbow_flexion", "팔꿈치 굽힘각",
        "릴리즈 직전 팔꿈치 각도는 공에 실리는 힘과 팔꿈치 부하를 함께 좌우합니다.",
    ),
    AngleRule(
        "acceleration", ARM_SLOT, 85.0, 10.0, "acceleration_arm_slot", "암슬롯(상완 기울기)",
        "암슬롯이 투구마다 흔들리면 릴리즈 포인트가 달라져 제구가 무너집니다.",
    ),
    AngleRule(
        "follow_through", ELBOW_FLEXION, 80.0, 15.0, "follow_through_elbow_flexion", "팔꿈치 굽힘각",
        "던진 뒤 팔이 자연스럽게 펴지는지는 감속이 제대로 되는지를 보여줍니다.",
    ),
    AngleRule(
        "follow_through", ARM_SLOT, 80.0, 10.0, "follow_through_arm_slot", "암슬롯(상완 기울기)",
        "마무리 팔 경로가 일정해야 어깨·팔꿈치 부담이 분산됩니다.",
    ),
)
