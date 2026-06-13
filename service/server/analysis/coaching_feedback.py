from __future__ import annotations

from typing import Any

import pandas as pd

from analysis.coaching_feedback_utils import (
    PHASE_ORDER,
    SEVERITY_WEIGHT,
    AxisRule,
    CoachingTip,
    joint_name,
    make_tip,
    metric_value,
    phase_duration_ratio,
    phase_label,
    point_at_phase,
    safe_float,
    unique_tips,
)


MAX_DETAILED_BAD_ITEMS = 8
LOW_PHASE_SCORE = 75.0
HIGH_PRIORITY_PHASE_SCORE = 60.0
AXIS_RULES = (
    AxisRule("leg_lift", "stride_knee", "y", 100.0, 0.12, "leg_lift_knee_height", "디딤 무릎 높이", "레그 리프트에서 디딤 무릎이 선수보다 높게 올라갑니다. 중심이 뒤로 남지 않는지 확인하세요.", "레그 리프트에서 디딤 무릎 높이가 선수보다 낮습니다. 무릎을 끌어올리는 크기와 균형을 확인하세요."),
    AxisRule("leg_lift", "stride_knee", "abs_x", 100.0, 0.12, "leg_lift_knee_direction", "디딤 무릎 좌우 벌어짐", "레그 리프트에서 디딤 무릎이 몸 중심에서 선수보다 더 크게 벌어집니다. 무릎 방향이 옆으로 새는지 확인하세요.", "레그 리프트에서 디딤 무릎이 선수보다 몸 중심에 가깝게 머뭅니다. 하체가 충분히 열리는지 확인하세요."),
    AxisRule("stride", "stride_foot", "abs_x", 100.0, 0.15, "stride_foot_width", "디딤발 착지 폭", "스트라이드에서 디딤발 착지 폭이 선수보다 넓습니다. 골반 회전이 막히지 않는지 확인하세요.", "스트라이드에서 디딤발 착지 폭이 선수보다 좁습니다. 하체가 앞으로 충분히 나가는지 확인하세요."),
    AxisRule("acceleration", "throwing_elbow", "y", 65.0, 0.12, "throwing_elbow_height", "투구 팔꿈치 높이", "가속 구간에서 투구 팔꿈치가 선수보다 높게 형성됩니다. 어깨선과 팔꿈치 위치를 함께 확인하세요.", "가속 구간에서 투구 팔꿈치가 선수보다 낮게 형성됩니다. 팔이 처지는 패턴이 있는지 확인하세요."),
    AxisRule("acceleration", "throwing_wrist", "y", 85.0, 0.16, "throwing_wrist_height", "릴리즈 직전 손목 높이", "릴리즈 직전 투구 손목이 선수보다 높게 지나갑니다. 릴리즈 포인트와 팔 각도를 함께 확인하세요.", "릴리즈 직전 투구 손목이 선수보다 낮게 지나갑니다. 공을 끌고 나오는 높이가 낮아지는지 확인하세요."),
    AxisRule("follow_through", "throwing_wrist", "y", 80.0, 0.18, "follow_through_finish_height", "팔로스루 손목 높이", "팔로스루에서 투구 손목이 선수보다 높게 남습니다. 끝까지 몸 앞쪽으로 내려오는지 확인하세요.", "팔로스루에서 투구 손목이 선수보다 낮게 떨어집니다. 상체가 과하게 숙여지는지 확인하세요."),
    AxisRule("windup", "throwing_wrist", "distance", 50.0, 0.18, "windup_hand_distance", "준비 동작 손목 거리", "와인드업에서 투구 손목이 몸 중심에서 선수보다 멀게 시작합니다. 시작 자세의 팔 위치를 확인하세요.", "와인드업에서 투구 손목이 선수보다 몸에 가깝게 시작합니다. 팔을 꺼내는 준비 동작을 확인하세요."),
    AxisRule("follow_through", "throwing_wrist", "distance", 85.0, 0.20, "follow_through_extension", "팔로스루 손목 이동 크기", "팔로스루에서 투구 손목이 선수보다 몸 중심에서 멀리 이동합니다. 마무리 균형을 확인하세요.", "팔로스루에서 투구 손목 이동이 선수보다 작습니다. 공을 던진 뒤 팔이 충분히 따라 나오는지 확인하세요."),
)


def build_coaching_feedback(
    *,
    user_pose: pd.DataFrame,
    pro_pose: pd.DataFrame,
    user_phases: Any,
    pro_phases: Any,
    phase_scores: list[dict[str, Any]],
    release: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    tips = [
        *_release_tips(release),
        *_phase_score_tips(phase_scores),
        *_axis_metric_tips(user_pose, pro_pose, user_phases, pro_phases),
        *_duration_tips(user_phases, pro_phases),
    ]
    ordered = sorted(
        unique_tips(tips),
        key=lambda tip: (
            -SEVERITY_WEIGHT.get(tip.severity, 0.0),
            -tip.magnitude,
            PHASE_ORDER.get(str(tip.phase), 99),
        ),
    )
    return {"good": [], "bad": [tip.feedback_item() for tip in ordered[:MAX_DETAILED_BAD_ITEMS]]}


def _release_tips(release: dict[str, Any]) -> list[CoachingTip]:
    tips: list[CoachingTip] = []
    timing = release.get("timing") if isinstance(release.get("timing"), dict) else {}
    timing_diff = safe_float(timing.get("differencePercent"), fallback=None)
    if timing_diff is not None and abs(timing_diff) > 7.0:
        direction = "늦게" if timing_diff > 0 else "빠르게"
        tips.append(
            make_tip(
                "acceleration",
                "release_timing",
                "high" if abs(timing_diff) >= 14.0 else "medium",
                f"릴리즈 타이밍이 선수보다 {direction} 나타납니다. 스트라이드 이후 공을 놓는 시점을 함께 확인하세요.",
                abs(timing_diff),
                timing,
            )
        )
    point = release.get("point") if isinstance(release.get("point"), dict) else {}
    point_diff = safe_float(point.get("difference"), fallback=None)
    if point_diff is not None and point_diff > 0.22:
        message = str(point.get("message") or "릴리즈 포인트 차이가 큽니다.")
        tips.append(make_tip("acceleration", "release_point", "high", message, point_diff, point))
    return tips


def _phase_score_tips(phase_scores: list[dict[str, Any]]) -> list[CoachingTip]:
    ready = [(phase, safe_float(phase.get("score"), fallback=None)) for phase in phase_scores]
    low = sorted([(phase, score) for phase, score in ready if score is not None and score <= LOW_PHASE_SCORE], key=lambda item: item[1])
    tips: list[CoachingTip] = []
    for phase, score in low[:3]:
        severity = "high" if score <= HIGH_PRIORITY_PHASE_SCORE else "medium"
        name = str(phase.get("label") or "해당")
        tips.append(
            make_tip(
                str(phase.get("phase") or ""),
                "phase_similarity",
                severity,
                f"{name} 구간은 같은 진행률의 자세 차이가 커서 우선 점검하면 좋습니다.",
                100.0 - score,
                {"score": round(score, 2), "difference": round((100.0 - score) / 100.0, 4)},
            )
        )
    return tips


def _axis_metric_tips(user_pose: pd.DataFrame, pro_pose: pd.DataFrame, user_phases: Any, pro_phases: Any) -> list[CoachingTip]:
    tips: list[CoachingTip] = []
    for rule in AXIS_RULES:
        user_point = point_at_phase(user_pose, user_phases, rule.phase, joint_name(user_pose, rule.joint_role), rule.percent)
        pro_point = point_at_phase(pro_pose, pro_phases, rule.phase, joint_name(pro_pose, rule.joint_role), rule.percent)
        if user_point is None or pro_point is None:
            continue
        user_value = metric_value(user_point, rule.axis)
        pro_value = metric_value(pro_point, rule.axis)
        diff = user_value - pro_value
        if abs(diff) < rule.threshold:
            continue
        tips.append(
            make_tip(
                rule.phase,
                rule.category,
                "high" if abs(diff) >= rule.threshold * 1.8 else "medium",
                rule.positive_message if diff > 0 else rule.negative_message,
                abs(diff),
                {
                    "metric": rule.metric_label,
                    "userFrame": user_point.frame,
                    "proFrame": pro_point.frame,
                    "userPhasePercent": round(rule.percent),
                    "proPhasePercent": round(rule.percent),
                    "userValue": round(user_value, 4),
                    "proValue": round(pro_value, 4),
                    "difference": round(diff, 4),
                    "threshold": rule.threshold,
                },
            )
        )
    return tips


def _duration_tips(user_phases: Any, pro_phases: Any) -> list[CoachingTip]:
    tips: list[CoachingTip] = []
    for phase in ("leg_lift", "stride", "acceleration", "follow_through"):
        user_ratio = phase_duration_ratio(user_phases, phase)
        pro_ratio = phase_duration_ratio(pro_phases, phase)
        if user_ratio is None or pro_ratio is None:
            continue
        diff = user_ratio - pro_ratio
        if abs(diff) < 0.08:
            continue
        label = phase_label(user_phases, phase)
        direction = "길게" if diff > 0 else "짧게"
        tips.append(
            make_tip(
                phase,
                "phase_timing_balance",
                "medium",
                f"{label} 구간을 선수보다 {direction} 사용합니다. 구간 전환 타이밍을 확인하세요.",
                abs(diff),
                {"userPhasePercent": round(user_ratio * 100.0), "proPhasePercent": round(pro_ratio * 100.0), "differencePercent": round(diff * 100.0), "difference": round(abs(diff), 4)},
            )
        )
    return tips
