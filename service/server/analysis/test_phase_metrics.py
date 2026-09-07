from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from analysis.coaching_feedback import AXIS_RULES
from analysis.coaching_feedback_utils import AxisRule, is_favorable
from analysis.phase_metrics import build_phase_metrics


def _rule(favorable_direction: str | None) -> AxisRule:
    return AxisRule(
        phase="leg_lift",
        joint_role="stride_knee",
        axis="y",
        percent=100.0,
        threshold=0.12,
        category="leg_lift_knee_height",
        metric_label="디딤 무릎 높이",
        positive_message="높다",
        negative_message="낮다",
        why="에너지 축적과 직결됩니다.",
        favorable_direction=favorable_direction,
    )


def test_is_favorable_positive_direction() -> None:
    assert is_favorable(_rule("positive"), 0.2) is True
    assert is_favorable(_rule("positive"), -0.2) is False


def test_is_favorable_negative_direction() -> None:
    assert is_favorable(_rule("negative"), -0.2) is True
    assert is_favorable(_rule("negative"), 0.2) is False


def test_is_favorable_none_direction_is_never_favorable() -> None:
    assert is_favorable(_rule(None), 0.2) is False
    assert is_favorable(_rule(None), -0.2) is False


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


def _pose(knee_y: float) -> pd.DataFrame:
    """AXIS_RULES가 보는 관절만 채운 최소 포즈 테이블.

    joint_name()은 throwing_side 기본값 right, stride_side 기본값 left를 쓰므로
    right_wrist / right_elbow / left_knee / left_foot_index 가 필요하다.
    """
    joints = ["right_wrist", "right_elbow", "left_knee", "left_foot_index"]
    rows = []
    for frame in range(0, 51):
        row: dict[str, float] = {"frame_index": float(frame)}
        for joint in joints:
            row[f"{joint}_body_x"] = 0.1
            row[f"{joint}_body_y"] = knee_y if joint == "left_knee" else 0.2
            row[f"{joint}_confidence"] = 0.9
        rows.append(row)
    return pd.DataFrame(rows)


def test_every_rule_produces_an_item_even_when_within_threshold() -> None:
    metrics = build_phase_metrics(_pose(0.5), _pose(0.5), _phases(), _phases())
    # 차이가 0이어도 8개 규칙 전부가 항목이 되어야 접었다 펼치는 점검표가 된다.
    assert len(metrics) == 8
    assert {m["status"] for m in metrics} == {"good"}


def test_difference_keeps_sign_and_threshold_decides_status() -> None:
    metrics = build_phase_metrics(_pose(0.9), _pose(0.5), _phases(), _phases())
    knee = next(m for m in metrics if m["key"] == "leg_lift_knee_height")
    assert round(knee["difference"], 4) == 0.4      # 부호 유지: 사용자 - 기준
    assert knee["threshold"] == 0.12
    assert knee["status"] == "warn"                 # pro 모드에선 유리해도 warn


def test_difference_is_negative_when_user_is_below_reference() -> None:
    # 위 테스트(user 0.9 vs pro 0.5)는 +0.4만 다뤄서, difference를 abs()로 바꿔도
    # 값이 똑같이 통과해 부호 보존을 검증하지 못했다. user < pro인 케이스를 추가해
    # 음수 부호가 실제로 살아남는지 확인한다.
    metrics = build_phase_metrics(_pose(0.3), _pose(0.5), _phases(), _phases())
    knee = next(m for m in metrics if m["key"] == "leg_lift_knee_height")
    assert round(knee["difference"], 4) == -0.2     # 부호 유지: 사용자 - 기준(음수)


def test_favorable_only_in_best_pitch_mode() -> None:
    metrics = build_phase_metrics(
        _pose(0.9), _pose(0.5), _phases(), _phases(), comparison_mode="best_pitch"
    )
    knee = next(m for m in metrics if m["key"] == "leg_lift_knee_height")
    # 무릎 높이는 favorable_direction="positive" → 더 높은 쪽이 유리
    assert knee["status"] == "favorable"


def test_missing_joint_yields_unavailable_with_null_values() -> None:
    empty = pd.DataFrame([{"frame_index": float(f)} for f in range(0, 51)])
    metrics = build_phase_metrics(empty, empty, _phases(), _phases())
    assert len(metrics) == 8
    assert {m["status"] for m in metrics} == {"unavailable"}
    assert all(m["userValue"] is None and m["difference"] is None for m in metrics)


def test_item_carries_label_why_and_frames() -> None:
    metrics = build_phase_metrics(_pose(0.5), _pose(0.5), _phases(), _phases())
    knee = next(m for m in metrics if m["key"] == "leg_lift_knee_height")
    assert knee["phase"] == "leg_lift"
    assert knee["label"] == "디딤 무릎 높이"
    assert knee["why"]                      # 왜 중요한지가 필드로 온다
    assert knee["userFrame"] == 20          # leg_lift 10~20의 100% 지점
    assert knee["favorableDirection"] == "positive"


def test_axis_metrics_carry_null_unit() -> None:
    """축 지표는 단위 없는 정규화 좌표다. 필드를 항상 실어 앱이 분기하기 쉽게 한다."""
    metrics = build_phase_metrics(_pose(0.5), _pose(0.5), _phases(), _phases())
    axis_keys = {rule.category for rule in AXIS_RULES}
    axis_metrics = [m for m in metrics if m["key"] in axis_keys]
    assert len(axis_metrics) == 8
    assert all("unit" in m and m["unit"] is None for m in axis_metrics)
