"""구간별 상세 지표.

기존 coaching_feedback은 "임계를 넘은 것"만 문장으로 만든다. 그래서 정상 범위인
지표는 앱까지 도달하지 못하고, 사용자는 "이 구간에 아무것도 안 뜬다"가 잘한 것인지
측정을 못 한 것인지 알 수 없었다.

여기서는 같은 AXIS_RULES를 임계 초과 여부와 무관하게 전부 평가해, 값·임계·판정을
구조화된 형태로 내보낸다. 문장 생성 로직은 건드리지 않는다.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from analysis.coaching_feedback import AXIS_RULES
from analysis.coaching_feedback_utils import (
    AxisRule,
    is_favorable,
    joint_name,
    metric_value,
    point_at_phase,
)
from analysis.joint_angles import (
    ANGLE_RULES,
    ARM_SLOT,
    AngleRule,
    arm_slot_degrees,
    elbow_flexion_degrees,
)

STATUS_GOOD = "good"
STATUS_WARN = "warn"
STATUS_FAVORABLE = "favorable"
STATUS_UNAVAILABLE = "unavailable"

ANGLE_UNIT = "degree"
# 각도는 소수 첫째 자리까지만 의미가 있다. MediaPipe 2D 추정치에 그 아래 정밀도는 없다.
ANGLE_DECIMALS = 1


def build_phase_metrics(
    user_pose: pd.DataFrame,
    pro_pose: pd.DataFrame,
    user_phases: Any,
    pro_phases: Any,
    comparison_mode: str = "pro",
) -> list[dict[str, Any]]:
    """AXIS_RULES 전부를 평가해 구간별 지표 목록을 만든다.

    임계를 넘지 않은 지표도 반드시 포함한다. 측정하지 못한 지표는 감추지 않고
    status="unavailable"로 남긴다 — 값이 없는 것과 문제가 없는 것은 다른 의미다.
    """
    return [
        _evaluate(rule, user_pose, pro_pose, user_phases, pro_phases, comparison_mode)
        for rule in AXIS_RULES
    ] + [
        _evaluate_angle(rule, user_pose, pro_pose, user_phases, pro_phases)
        for rule in ANGLE_RULES
    ]


def _evaluate(
    rule: AxisRule,
    user_pose: pd.DataFrame,
    pro_pose: pd.DataFrame,
    user_phases: Any,
    pro_phases: Any,
    comparison_mode: str,
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "phase": rule.phase,
        "key": rule.category,
        "label": rule.metric_label,
        # 축 지표는 body-frame 정규화 좌표라 단위가 없다. 각도 지표와 구분하는 값이다.
        "unit": None,
        "threshold": round(rule.threshold, 4),
        "favorableDirection": rule.favorable_direction,
        "why": rule.why,
    }

    user_point = point_at_phase(user_pose, user_phases, rule.phase, joint_name(user_pose, rule.joint_role), rule.percent)
    pro_point = point_at_phase(pro_pose, pro_phases, rule.phase, joint_name(pro_pose, rule.joint_role), rule.percent)

    if user_point is None or pro_point is None:
        return {
            **base,
            "userValue": None,
            "proValue": None,
            "difference": None,
            "status": STATUS_UNAVAILABLE,
            "userFrame": None,
            "proFrame": None,
        }

    user_value = metric_value(user_point, rule.axis)
    pro_value = metric_value(pro_point, rule.axis)
    diff = user_value - pro_value

    return {
        **base,
        "userValue": round(user_value, 4),
        "proValue": round(pro_value, 4),
        "difference": round(diff, 4),
        "status": _status(rule, diff, comparison_mode),
        "userFrame": user_point.frame,
        "proFrame": pro_point.frame,
    }


def _status(rule: AxisRule, diff: float, comparison_mode: str) -> str:
    if abs(diff) <= rule.threshold:
        return STATUS_GOOD
    # 프로 비교에서는 유리한 방향의 차이도 "프로와 다른 점"으로 다루는 것이 기존 동작이다
    # (_axis_metric_tips(skip_favorable=is_best_pitch)). 판정을 두 곳에서 다르게 두면
    # 같은 화면에서 앞뒤가 맞지 않는다.
    if comparison_mode == "best_pitch" and is_favorable(rule, diff):
        return STATUS_FAVORABLE
    return STATUS_WARN


def _evaluate_angle(
    rule: AngleRule,
    user_pose: pd.DataFrame,
    pro_pose: pd.DataFrame,
    user_phases: Any,
    pro_phases: Any,
) -> dict[str, Any]:
    """각도 지표 한 개를 평가한다.

    축 지표와 분기로 섞지 않고 별도 함수로 두는 이유는 규칙 타입이 다르고 status
    규칙도 다르기 때문이다. 각도에는 유리한 방향이 없어 is_favorable을 부르지 않는다 —
    불러도 favorable_direction이 없어 항상 False지만, 부르지 않는 편이 그 사실을
    코드에 남긴다.
    """
    threshold = round(rule.threshold, ANGLE_DECIMALS)
    base: dict[str, Any] = {
        "phase": rule.phase,
        "key": rule.category,
        "label": rule.metric_label,
        "unit": ANGLE_UNIT,
        "threshold": threshold,
        "favorableDirection": None,
        "why": rule.why,
    }

    user_angle, user_frame = _angle_at_phase(rule, user_pose, user_phases)
    pro_angle, pro_frame = _angle_at_phase(rule, pro_pose, pro_phases)

    if user_angle is None or pro_angle is None:
        return {
            **base,
            "userValue": None,
            "proValue": None,
            "difference": None,
            "status": STATUS_UNAVAILABLE,
            "userFrame": None,
            "proFrame": None,
        }

    user_value = round(user_angle, ANGLE_DECIMALS)
    pro_value = round(pro_angle, ANGLE_DECIMALS)
    # 판정은 내보내는 값으로 한다. 원값으로 판정하면 화면에 실린 숫자로는 양호인데
    # 뱃지는 주의인 구간이 생긴다.
    diff = round(user_value - pro_value, ANGLE_DECIMALS)

    return {
        **base,
        "userValue": user_value,
        "proValue": pro_value,
        "difference": diff,
        "status": STATUS_GOOD if abs(diff) <= threshold else STATUS_WARN,
        "userFrame": user_frame,
        "proFrame": pro_frame,
    }


def _angle_at_phase(
    rule: AngleRule, pose: pd.DataFrame, phases: Any
) -> tuple[float | None, Any]:
    """규칙이 요구하는 관절을 모두 같은 프레임에서 뽑아 각도를 계산한다.

    신뢰도 게이팅은 point_at_frame이 관절마다 이미 한다. 가려진 관절이 하나라도
    있으면 그 점이 None으로 돌아와 자연스럽게 unavailable이 된다.
    """
    shoulder = point_at_phase(
        pose, phases, rule.phase, joint_name(pose, "throwing_shoulder"), rule.percent
    )
    elbow = point_at_phase(
        pose, phases, rule.phase, joint_name(pose, "throwing_elbow"), rule.percent
    )
    if shoulder is None or elbow is None:
        return None, None

    if rule.kind == ARM_SLOT:
        return arm_slot_degrees(shoulder, elbow), elbow.frame

    wrist = point_at_phase(
        pose, phases, rule.phase, joint_name(pose, "throwing_wrist"), rule.percent
    )
    if wrist is None:
        return None, None
    return elbow_flexion_degrees(shoulder, elbow, wrist), elbow.frame
