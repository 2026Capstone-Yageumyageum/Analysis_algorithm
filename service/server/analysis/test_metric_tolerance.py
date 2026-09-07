from __future__ import annotations

import math
from types import SimpleNamespace

import pandas as pd

from analysis.coaching_feedback import AXIS_RULES
from analysis.metric_tolerance import MIN_PRO_SAMPLES, build_tolerance_table, spread_of
from analysis.phase_metrics import build_phase_metrics


def test_spread_is_population_standard_deviation() -> None:
    # 평균 4, 편차 제곱 평균 = (4+1+0+1+4)/5 = 2
    assert abs(spread_of([2.0, 3.0, 4.0, 5.0, 6.0]) - math.sqrt(2.0)) < 1e-12


def test_spread_needs_enough_pros() -> None:
    """표본이 너무 적으면 편차를 신뢰할 수 없다. 상수 폴백으로 넘긴다."""
    assert spread_of([1.0, 2.0]) is None
    assert spread_of([]) is None


def test_spread_ignores_missing_values() -> None:
    assert spread_of([2.0, None, 3.0, 4.0, None, 5.0, 6.0]) is not None
    # 값이 3개 미만만 남으면 못 쓴다
    assert spread_of([2.0, None, None, None]) is None


def test_identical_pros_yield_no_spread() -> None:
    """프로들이 똑같으면 편차가 0이다. 그대로 쓰면 모든 투구가 '주의'가 된다."""
    assert spread_of([0.5, 0.5, 0.5, 0.5, 0.5, 0.5]) is None


def _phases() -> SimpleNamespace:
    return SimpleNamespace(
        intervals={
            "windup": {"startFrame": 0, "endFrame": 10},
            "leg_lift": {"startFrame": 10, "endFrame": 20},
            "stride": {"startFrame": 20, "endFrame": 30},
            "acceleration": {"startFrame": 30, "endFrame": 40},
            "follow_through": {"startFrame": 40, "endFrame": 50},
        }
    )


def _pose(knee_y: float) -> pd.DataFrame:
    """축 지표가 보는 관절만 채운 최소 포즈 테이블."""
    rows = []
    for frame in range(0, 51):
        rows.append(
            {
                "frame_index": float(frame),
                "left_knee_body_x": 0.1,
                "left_knee_body_y": knee_y,
                "left_foot_index_body_x": 0.2,
                "left_foot_index_body_y": 0.3,
                "right_wrist_body_x": 0.4,
                "right_wrist_body_y": 0.5,
                "right_elbow_body_x": 0.6,
                "right_elbow_body_y": 0.7,
                "right_shoulder_body_x": 0.8,
                "right_shoulder_body_y": 0.9,
            }
        )
    return pd.DataFrame(rows)


def test_tolerance_table_uses_pro_spread() -> None:
    """무릎 높이만 프로마다 다르게 두면 그 지표에 편차가 잡힌다."""
    poses = [(_pose(height), _phases()) for height in (0.30, 0.40, 0.50, 0.60, 0.70, 0.80)]

    table = build_tolerance_table(poses)

    knee = table.get("leg_lift_knee_height")
    assert knee is not None
    # 0.30~0.80 균등 6개의 모표준편차
    assert abs(knee - 0.17078251276599332) < 1e-9


def test_tolerance_table_omits_metrics_without_spread() -> None:
    """모든 프로가 같은 값인 지표는 표에 넣지 않는다 — 상수 폴백으로 간다."""
    poses = [(_pose(0.50), _phases()) for _ in range(6)]

    table = build_tolerance_table(poses)

    assert "leg_lift_knee_height" not in table


def test_build_phase_metrics_prefers_the_table() -> None:
    metrics = build_phase_metrics(
        _pose(0.9), _pose(0.5), _phases(), _phases(), tolerances={"leg_lift_knee_height": 0.5}
    )

    knee = next(m for m in metrics if m["key"] == "leg_lift_knee_height")
    assert knee["threshold"] == 0.5
    # 차이 0.4 < 허용 0.5 → 양호. 상수(0.12)였다면 주의였다.
    assert knee["status"] == "good"


def test_build_phase_metrics_falls_back_to_rule_constant() -> None:
    """표에 없는 지표는 규칙 상수를 그대로 쓴다. 기존 동작이 유지되어야 한다."""
    metrics = build_phase_metrics(_pose(0.9), _pose(0.5), _phases(), _phases(), tolerances={})

    knee = next(m for m in metrics if m["key"] == "leg_lift_knee_height")
    constant = next(rule.threshold for rule in AXIS_RULES if rule.category == "leg_lift_knee_height")
    assert knee["threshold"] == round(constant, 4)


def test_angle_metrics_also_use_the_table() -> None:
    metrics = build_phase_metrics(
        _pose(0.5), _pose(0.5), _phases(), _phases(), tolerances={"stride_arm_slot": 22.5}
    )

    slot = next(m for m in metrics if m["key"] == "stride_arm_slot")
    assert slot["threshold"] == 22.5


def test_min_pro_samples_is_three() -> None:
    assert MIN_PRO_SAMPLES == 3


if __name__ == "__main__":
    for name, func in list(globals().items()):
        if name.startswith("test_"):
            func()
    print("ok")
