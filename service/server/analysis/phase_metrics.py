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

STATUS_GOOD = "good"
STATUS_WARN = "warn"
STATUS_FAVORABLE = "favorable"
STATUS_UNAVAILABLE = "unavailable"


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
    return [_evaluate(rule, user_pose, pro_pose, user_phases, pro_phases, comparison_mode) for rule in AXIS_RULES]


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
