from __future__ import annotations

from typing import Any

import pandas as pd

from analysis.coaching_feedback_utils import (
    PHASE_ORDER,
    SEVERITY_WEIGHT,
    AxisRule,
    CoachingTip,
    joint_name,
    magnitude_word,
    make_tip,
    metric_value,
    phase_duration_ratio,
    phase_label,
    point_at_phase,
    safe_float,
    unique_tips,
)


MAX_DETAILED_BAD_ITEMS = 8
MAX_DETAILED_GOOD_ITEMS = 4
LOW_PHASE_SCORE = 75.0
HIGH_PRIORITY_PHASE_SCORE = 60.0
GOOD_PHASE_SCORE = 82.0  # 이 이상이면 '잘된 점'으로 칭찬
GOOD_AXIS_RATIO = 0.4  # 관절 지표가 임계값의 40% 이내로 맞으면 '잘된 점'
AXIS_RULES = (
    AxisRule("leg_lift", "stride_knee", "y", 100.0, 0.12, "leg_lift_knee_height", "디딤 무릎 높이", "레그 리프트에서 디딤 무릎이 선수보다 높게 올라갑니다. 중심이 뒤로 남지 않는지 확인하세요.", "레그 리프트에서 디딤 무릎 높이가 선수보다 낮습니다. 무릎을 끌어올리는 크기와 균형을 확인하세요.", why="레그 리프트 높이는 하체에 축적되는 에너지의 크기와 직결됩니다.", favorable_direction="positive"),
    AxisRule("leg_lift", "stride_knee", "abs_x", 100.0, 0.12, "leg_lift_knee_direction", "디딤 무릎 좌우 벌어짐", "레그 리프트에서 디딤 무릎이 몸 중심에서 선수보다 더 크게 벌어집니다. 무릎 방향이 옆으로 새는지 확인하세요.", "레그 리프트에서 디딤 무릎이 선수보다 몸 중심에 가깝게 머뭅니다. 하체가 충분히 열리는지 확인하세요.", why="무릎 방향이 새면 골반 회전축이 흔들려 힘 전달이 분산됩니다."),
    AxisRule("stride", "stride_foot", "abs_x", 100.0, 0.15, "stride_foot_width", "디딤발 착지 폭", "스트라이드에서 디딤발 착지 폭이 선수보다 넓습니다. 골반 회전이 막히지 않는지 확인하세요.", "스트라이드에서 디딤발 착지 폭이 선수보다 좁습니다. 하체가 앞으로 충분히 나가는지 확인하세요.", why="착지 폭은 골반 회전과 체중 이동 효율을 좌우합니다."),
    AxisRule("acceleration", "throwing_elbow", "y", 65.0, 0.12, "throwing_elbow_height", "투구 팔꿈치 높이", "가속 구간에서 투구 팔꿈치가 선수보다 높게 형성됩니다. 어깨선과 팔꿈치 위치를 함께 확인하세요.", "가속 구간에서 투구 팔꿈치가 선수보다 낮게 형성됩니다. 팔이 처지는 패턴이 있는지 확인하세요.", why="가속기 팔꿈치 높이는 공에 실리는 힘과 제구 안정성에 영향을 줍니다."),
    AxisRule("acceleration", "throwing_wrist", "y", 85.0, 0.16, "throwing_wrist_height", "릴리즈 직전 손목 높이", "릴리즈 직전 투구 손목이 선수보다 높게 지나갑니다. 릴리즈 포인트와 팔 각도를 함께 확인하세요.", "릴리즈 직전 투구 손목이 선수보다 낮게 지나갑니다. 공을 끌고 나오는 높이가 낮아지는지 확인하세요.", why="릴리즈 직전 손목 높이는 릴리즈 포인트와 공 궤적을 결정합니다."),
    AxisRule("follow_through", "throwing_wrist", "y", 80.0, 0.18, "follow_through_finish_height", "팔로스루 손목 높이", "팔로스루에서 투구 손목이 선수보다 높게 남습니다. 끝까지 몸 앞쪽으로 내려오는지 확인하세요.", "팔로스루에서 투구 손목이 선수보다 낮게 떨어집니다. 상체가 과하게 숙여지는지 확인하세요.", why="팔로스루 마무리 높이는 부상 방지와 동작 안정성에 중요합니다."),
    AxisRule("windup", "throwing_wrist", "distance", 50.0, 0.18, "windup_hand_distance", "준비 동작 손목 거리", "와인드업에서 투구 손목이 몸 중심에서 선수보다 멀게 시작합니다. 시작 자세의 팔 위치를 확인하세요.", "와인드업에서 투구 손목이 선수보다 몸에 가깝게 시작합니다. 팔을 꺼내는 준비 동작을 확인하세요.", why="준비 자세의 팔 위치는 이후 동작 리듬의 출발점이 됩니다."),
    AxisRule("follow_through", "throwing_wrist", "distance", 85.0, 0.20, "follow_through_extension", "팔로스루 손목 이동 크기", "팔로스루에서 투구 손목이 선수보다 몸 중심에서 멀리 이동합니다. 마무리 균형을 확인하세요.", "팔로스루에서 투구 손목 이동이 선수보다 작습니다. 공을 던진 뒤 팔이 충분히 따라 나오는지 확인하세요.", why="팔로스루 이동량은 힘을 끝까지 전달했는지를 보여줍니다.", favorable_direction="positive"),
)


def build_coaching_feedback(
    *,
    user_pose: pd.DataFrame,
    pro_pose: pd.DataFrame,
    user_phases: Any,
    pro_phases: Any,
    phase_scores: list[dict[str, Any]],
    release: dict[str, Any],
    comparison_mode: str = "pro",
    reference_label: str = "선수",
) -> dict[str, list[dict[str, Any]]]:
    # 최고의 1구 비교에서는 "힘 전달엔 더 유리한 방향"의 차이를 bad가 아닌 good(코멘트)로 돌린다.
    is_best_pitch = comparison_mode == "best_pitch"
    tips = [
        *_release_tips(release),
        *_phase_score_tips(phase_scores),
        *_axis_metric_tips(user_pose, pro_pose, user_phases, pro_phases, skip_favorable=is_best_pitch),
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
    good_source = _good_tips(user_pose, pro_pose, user_phases, pro_phases, phase_scores)
    if is_best_pitch:
        # "다르지만 힘 전달엔 더 나을 수 있다"는 방향성 코멘트(측정값 포함)
        good_source = (
            _favorable_axis_tips(user_pose, pro_pose, user_phases, pro_phases, reference_label)
            + good_source
        )
    good_tips = sorted(unique_tips(good_source), key=lambda tip: -tip.magnitude)
    return {
        "good": [tip.feedback_item() for tip in good_tips[:MAX_DETAILED_GOOD_ITEMS]],
        "bad": [tip.feedback_item() for tip in ordered[:MAX_DETAILED_BAD_ITEMS]],
    }


def _good_tips(
    user_pose: pd.DataFrame,
    pro_pose: pd.DataFrame,
    user_phases: Any,
    pro_phases: Any,
    phase_scores: list[dict[str, Any]],
) -> list[CoachingTip]:
    """선수와 잘 일치한 부분을 '잘된 점'으로 만든다(측정값 함께 노출)."""
    tips: list[CoachingTip] = []
    # ① 점수가 높은 구간
    for phase in phase_scores:
        score = safe_float(phase.get("score"), fallback=None)
        if score is None or score < GOOD_PHASE_SCORE:
            continue
        name = str(phase.get("label") or "해당")
        tips.append(
            make_tip(
                str(phase.get("phase") or ""),
                "phase_similarity_good",
                "info",
                f"{name} 구간 자세가 선수와 매우 유사합니다. 지금 감각을 유지하세요.",
                score,
                {"score": round(score, 2)},
            )
        )
    # ② 선수와 거의 일치한 관절 지표
    for rule in AXIS_RULES:
        user_point = point_at_phase(user_pose, user_phases, rule.phase, joint_name(user_pose, rule.joint_role), rule.percent)
        pro_point = point_at_phase(pro_pose, pro_phases, rule.phase, joint_name(pro_pose, rule.joint_role), rule.percent)
        if user_point is None or pro_point is None:
            continue
        user_value = metric_value(user_point, rule.axis)
        pro_value = metric_value(pro_point, rule.axis)
        if abs(user_value - pro_value) > rule.threshold * GOOD_AXIS_RATIO:
            continue
        label = phase_label(user_phases, rule.phase)
        tips.append(
            make_tip(
                rule.phase,
                f"{rule.category}_good",
                "info",
                f"{label}의 {rule.metric_label}이(가) 선수와 거의 일치합니다 — 측정값 나 {user_value:.2f} vs 선수 {pro_value:.2f}.",
                rule.threshold - abs(user_value - pro_value),
                {
                    "metric": rule.metric_label,
                    "userFrame": user_point.frame,
                    "proFrame": pro_point.frame,
                    "userPhasePercent": round(rule.percent),
                    "proPhasePercent": round(rule.percent),
                    "userValue": round(user_value, 4),
                    "proValue": round(pro_value, 4),
                    "difference": round(user_value - pro_value, 4),
                },
            )
        )
    return tips


def _release_tips(release: dict[str, Any]) -> list[CoachingTip]:
    tips: list[CoachingTip] = []
    timing = release.get("timing") if isinstance(release.get("timing"), dict) else {}
    timing_diff = safe_float(timing.get("differencePercent"), fallback=None)
    # 발 착지~피니시 구간 기준이라 % 차이가 크게 잡혀, 임계값도 그에 맞춰 키웠다.
    if timing_diff is not None and abs(timing_diff) > 10.0:
        direction = "늦게" if timing_diff > 0 else "빠르게"
        tips.append(
            make_tip(
                "acceleration",
                "release_timing",
                "high" if abs(timing_diff) >= 20.0 else "medium",
                f"발 착지 이후 릴리즈가 선수보다 {direction} 나타납니다(발 착지~피니시 기준 약 {abs(timing_diff):.0f}% 차이). "
                f"릴리즈가 빠르거나 늦으면 공 끝과 제구가 흔들립니다. 발 착지 이후 공을 놓는 시점을 함께 확인하세요.",
                abs(timing_diff),
                timing,
            )
        )
    point = release.get("point") if isinstance(release.get("point"), dict) else {}
    point_diff = safe_float(point.get("difference"), fallback=None)
    if point_diff is not None and point_diff > 0.22:
        base = str(point.get("message") or "릴리즈 포인트가 선수와 차이가 큽니다.")
        message = (
            f"{base} (릴리즈 지점 거리 차이 약 {point_diff:.2f}). "
            f"릴리즈 지점이 일정해야 제구가 안정됩니다."
        )
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
                f"{name} 구간은 같은 진행률에서 선수와 자세 차이가 큽니다. "
                f"프레임을 끊어 보며 어깨·팔·하체 정렬을 선수와 맞춰 보세요.",
                100.0 - score,
                {"score": round(score, 2), "difference": round((100.0 - score) / 100.0, 4)},
            )
        )
    return tips


def _is_favorable(rule: AxisRule, diff: float) -> bool:
    """이 차이가 '힘 전달' 관점에서 더 유리한 방향인지(최고의 1구 비교 전용 해석)."""
    if rule.favorable_direction == "positive":
        return diff > 0
    if rule.favorable_direction == "negative":
        return diff < 0
    return False


def _evaluate_axis_rules(
    user_pose: pd.DataFrame, pro_pose: pd.DataFrame, user_phases: Any, pro_phases: Any
) -> list[tuple[AxisRule, Any, Any, float, float, float]]:
    """임계값을 넘은 (rule, user_point, pro_point, user_value, pro_value, diff) 목록."""
    results: list[tuple[AxisRule, Any, Any, float, float, float]] = []
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
        results.append((rule, user_point, pro_point, user_value, pro_value, diff))
    return results


def _favorable_axis_tips(
    user_pose: pd.DataFrame, pro_pose: pd.DataFrame, user_phases: Any, pro_phases: Any, reference_label: str
) -> list[CoachingTip]:
    """최고의 1구보다 '힘 전달에 더 유리한 방향'으로 벌어진 차이를 긍정 코멘트로 만든다."""
    tips: list[CoachingTip] = []
    for rule, user_point, pro_point, user_value, pro_value, diff in _evaluate_axis_rules(
        user_pose, pro_pose, user_phases, pro_phases
    ):
        if not _is_favorable(rule, diff):
            continue
        label = phase_label(user_phases, rule.phase)
        message = (
            f"{label}의 {rule.metric_label}이(가) {reference_label}보다 큽니다. {rule.why} "
            f"일관성 점수는 낮을 수 있지만, 힘 전달 측면에서는 지금 폼이 더 나을 수 있어요 "
            f"— 측정값 나 {user_value:.2f} vs {reference_label} {pro_value:.2f}."
        )
        tips.append(
            make_tip(
                rule.phase,
                f"{rule.category}_favorable",
                "info",
                message,
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
                },
            )
        )
    return tips


def _axis_metric_tips(
    user_pose: pd.DataFrame, pro_pose: pd.DataFrame, user_phases: Any, pro_phases: Any, *, skip_favorable: bool = False
) -> list[CoachingTip]:
    tips: list[CoachingTip] = []
    for rule, user_point, pro_point, user_value, pro_value, diff in _evaluate_axis_rules(
        user_pose, pro_pose, user_phases, pro_phases
    ):
        # 최고의 1구 비교에서 '힘 전달에 더 유리한' 차이는 bad가 아니라 good(코멘트)로 보낸다.
        if skip_favorable and _is_favorable(rule, diff):
            continue
        word = magnitude_word(abs(diff) / rule.threshold)
        core = rule.positive_message if diff > 0 else rule.negative_message
        label = phase_label(user_phases, rule.phase)
        message = (
            f"{core} {rule.why}".strip()
            + f" — 측정값 나 {user_value:.2f} vs 선수 {pro_value:.2f}"
            + f" ({label} {round(rule.percent)}% 지점, 선수 대비 {word} 차이)."
        )
        tips.append(
            make_tip(
                rule.phase,
                rule.category,
                "high" if abs(diff) >= rule.threshold * 1.8 else "medium",
                message,
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
                f"{label} 구간을 선수보다 {direction} 사용합니다"
                f"(전체 동작 중 비중 나 {round(user_ratio * 100.0)}% vs 선수 {round(pro_ratio * 100.0)}%). "
                f"구간 전환 리듬이 깨지면 힘 전달 타이밍이 어긋납니다. 구간 전환 타이밍을 확인하세요.",
                abs(diff),
                {"userPhasePercent": round(user_ratio * 100.0), "proPhasePercent": round(pro_ratio * 100.0), "differencePercent": round(diff * 100.0), "difference": round(abs(diff), 4)},
            )
        )
    return tips
