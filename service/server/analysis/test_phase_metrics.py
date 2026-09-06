from __future__ import annotations

from analysis.coaching_feedback_utils import AxisRule, is_favorable


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
