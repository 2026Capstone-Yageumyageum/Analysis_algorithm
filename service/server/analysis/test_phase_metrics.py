from __future__ import annotations

import math
from types import SimpleNamespace

import pandas as pd

from analysis.coaching_feedback import AXIS_RULES
from analysis.coaching_feedback_utils import AxisRule, is_favorable
from analysis.joint_angles import ANGLE_RULES, ARM_SLOT, ELBOW_FLEXION
from analysis.normalization import BODY_JOINTS
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
    # 차이가 0이어도 16개 규칙 전부가 항목이 되어야 접었다 펼치는 점검표가 된다.
    assert len(metrics) == 16  # 축 지표 8 + 각도 지표 8
    # _pose()는 축 지표가 보는 관절만 채운다. 어깨가 없어 각도 지표는 unavailable이다.
    axis_keys = {rule.category for rule in AXIS_RULES}
    assert {m["status"] for m in metrics if m["key"] in axis_keys} == {"good"}
    assert {m["status"] for m in metrics if m["key"] not in axis_keys} == {"unavailable"}


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
    assert len(metrics) == 16  # 축 지표 8 + 각도 지표 8
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


def _left_handed_pose(knee_y: float) -> pd.DataFrame:
    """좌완 포즈. joint_name()이 throwing_side 컬럼을 읽어 left_* 를 고르게 한다."""
    pose = _pose(knee_y)
    pose["throwing_side"] = "left"
    pose["stride_side"] = "right"
    return pose


def _full_pose() -> pd.DataFrame:
    """BODY_JOINTS 전부를 채운 포즈. 축 지표뿐 아니라 각도 지표(어깨·팔꿈치·손목)도
    양쪽 손잡이 어느 쪽으로 풀려도 유효한 점을 찾도록 한다. 관절마다 좌표를 다르게 둬
    벡터가 퇴화(길이 0)해 각도가 None이 되는 일이 없게 한다 — 이 테스트는 실제 각도값이
    아니라 정렬 공식 일치를 확인하는 것이 목적이라 각도가 얼마인지는 상관없다."""
    rows = []
    for frame in range(0, 51):
        row: dict[str, float] = {"frame_index": float(frame)}
        for i, joint in enumerate(BODY_JOINTS):
            row[f"{joint}_body_x"] = 0.05 * (i + 1)
            row[f"{joint}_body_y"] = 0.03 * (i + 1)
            row[f"{joint}_confidence"] = 0.9
        rows.append(row)
    return pd.DataFrame(rows)


def test_axis_metric_reports_one_joint() -> None:
    metrics = build_phase_metrics(_pose(0.5), _pose(0.5), _phases(), _phases())
    knee = next(m for m in metrics if m["key"] == "leg_lift_knee_height")
    assert knee["userJoints"] == ["left_knee"]
    assert knee["proJoints"] == ["left_knee"]


def test_arm_slot_reports_shoulder_and_elbow() -> None:
    metrics = build_phase_metrics(_pose(0.5), _pose(0.5), _phases(), _phases())
    slot = next(m for m in metrics if m["key"] == "stride_arm_slot")
    assert slot["userJoints"] == ["right_shoulder", "right_elbow"]


def test_elbow_flexion_puts_the_vertex_in_the_middle() -> None:
    """가운데가 꼭짓점이다. 순서가 바뀌면 앱이 엉뚱한 각을 그린다."""
    metrics = build_phase_metrics(_pose(0.5), _pose(0.5), _phases(), _phases())
    flexion = next(m for m in metrics if m["key"] == "stride_elbow_flexion")
    assert flexion["userJoints"] == ["right_shoulder", "right_elbow", "right_wrist"]


def test_each_side_is_resolved_separately() -> None:
    """우완 사용자가 좌완과 비교하면 양쪽이 서로 다른 팔을 잰다."""
    metrics = build_phase_metrics(
        _pose(0.5), _left_handed_pose(0.5), _phases(), _phases()
    )
    slot = next(m for m in metrics if m["key"] == "acceleration_arm_slot")
    assert slot["userJoints"] == ["right_shoulder", "right_elbow"]
    assert slot["proJoints"] == ["left_shoulder", "left_elbow"]


def test_joints_are_present_even_when_unavailable() -> None:
    """값을 못 구해도 어느 관절을 보려 했는지는 알려준다."""
    empty = pd.DataFrame([{"frame_index": float(f)} for f in range(0, 51)])
    metrics = build_phase_metrics(empty, empty, _phases(), _phases())
    assert all(m["userJoints"] and m["proJoints"] for m in metrics)


def test_both_sides_have_the_same_shape() -> None:
    metrics = build_phase_metrics(
        _pose(0.5), _left_handed_pose(0.5), _phases(), _phases()
    )
    assert all(len(m["userJoints"]) == len(m["proJoints"]) for m in metrics)


# ── 아래 세 테스트는 분석 서버 → 백엔드 → 앱을 잇는 계약을 검증한다. 앱에는 테스트
# 러너가 없으므로(러너 부재는 프론트엔드 리포지토리 쪽 사정), 이 세 저장소를 잇는
# 불변식을 지키는 방어선은 여기뿐이다(전체 리뷰 Important 4).


def test_joint_count_matches_rule_geometry() -> None:
    """앱은 배열 길이로 그릴 기하를 정한다: 축 지표=1(강조만), 암슬롯=2(몸통축 대비 각),
    굽힘각=3(가운데가 꼭짓점). 여기서 길이가 하나라도 규칙 종류와 안 맞으면 앱이 엉뚱한
    각도를 그리거나 그려야 할 강조를 놓친다."""
    metrics = build_phase_metrics(_pose(0.5), _left_handed_pose(0.5), _phases(), _phases())
    axis_keys = {rule.category for rule in AXIS_RULES}
    arm_slot_keys = {rule.category for rule in ANGLE_RULES if rule.kind == ARM_SLOT}
    flexion_keys = {rule.category for rule in ANGLE_RULES if rule.kind == ELBOW_FLEXION}
    assert len(metrics) == len(axis_keys) + len(arm_slot_keys) + len(flexion_keys)

    for m in metrics:
        if m["key"] in axis_keys:
            expected = 1
        elif m["key"] in arm_slot_keys:
            expected = 2
        elif m["key"] in flexion_keys:
            expected = 3
        else:
            raise AssertionError(f"unclassified metric key: {m['key']}")
        assert len(m["userJoints"]) == expected, m["key"]
        assert len(m["proJoints"]) == expected, m["key"]


def test_joint_names_are_known_body_joints() -> None:
    """joint_name()은 역할이 매핑 테이블에 없으면 role 문자열을 그대로 돌려준다. 그런 role이
    새로 생기면 여기서 걸리지 않는 한 앱은 "관절이 가려져 표시할 수 없어요"만 조용히 띄우고,
    왜 항상 그런지는 아무도 모른다. userJoints/proJoints의 모든 이름이 앱이 아는 15개 관절
    (analysis.normalization.BODY_JOINTS) 안에 있는지 전 규칙에 대해 확인한다."""
    metrics = build_phase_metrics(_pose(0.5), _left_handed_pose(0.5), _phases(), _phases())
    for m in metrics:
        for name in [*m["userJoints"], *m["proJoints"]]:
            assert name in BODY_JOINTS, f"{m['key']}: unknown joint name {name!r}"


def test_pro_frame_matches_app_alignment_formula() -> None:
    """앱의 alignToCompareFrame 규칙 —
    proStart + (fu - userStart) / (userEnd - userStart) * (proEnd - proStart)
    — 이 각 지표의 proFrame과 일치해야 "이 순간 보기"에서 그려지는 프레임이 라벨이
    단언하는 그 순간과 같아진다. 같은 intervals로 phase_frame을 사용자·프로 양쪽에
    부른 것과 동치임을 확인한다.

    사용자 구간(10프레임)보다 프로 구간을 몇 배 길게 둬(가속 구간 40프레임) 리뷰
    Important 3이 지적한 증폭 시나리오도 함께 지나가게 한다.
    """
    user_phases = _phases()
    pro_phases = SimpleNamespace(
        intervals={
            "windup": {"startFrame": 5, "endFrame": 23, "label": "와인드업"},
            "leg_lift": {"startFrame": 23, "endFrame": 53, "label": "레그 리프트"},
            "stride": {"startFrame": 53, "endFrame": 71, "label": "스트라이드"},
            # 사용자 10프레임(30~40) vs 프로 40프레임(71~111) — 스냅 오차 증폭 시나리오.
            "acceleration": {"startFrame": 71, "endFrame": 111, "label": "가속"},
            "follow_through": {"startFrame": 111, "endFrame": 140, "label": "팔로스루"},
        }
    )
    metrics = build_phase_metrics(_full_pose(), _full_pose(), user_phases, pro_phases)
    assert len(metrics) > 0
    checked = 0
    for m in metrics:
        if m["userFrame"] is None or m["proFrame"] is None:
            continue
        user_span = user_phases.intervals[m["phase"]]
        pro_span = pro_phases.intervals[m["phase"]]
        user_start, user_end = user_span["startFrame"], user_span["endFrame"]
        pro_start, pro_end = pro_span["startFrame"], pro_span["endFrame"]
        expected = pro_start + (
            (m["userFrame"] - user_start) / (user_end - user_start)
        ) * (pro_end - pro_start)
        # userFrame/proFrame은 frame_value()를 거쳐 반올림돼 있어(최대 5e-5 오차),
        # 구간 길이비로 증폭돼도 무시할 만한 수준의 허용치를 둔다.
        assert math.isclose(m["proFrame"], expected, rel_tol=0, abs_tol=1e-2), m["key"]
        checked += 1
    # 모든 지표가 unavailable로 스킵되는 회귀(포즈가 잘못돼 아무것도 안 걸리는 경우)를 막는다.
    assert checked == len(metrics)
