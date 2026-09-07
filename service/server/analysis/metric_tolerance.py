"""지표 허용치를 프로들의 실측 편차에서 만든다.

기존 허용치(AXIS_RULES/ANGLE_RULES의 threshold)는 검증된 기준이 아니라 판단으로 정한
상수였다. 문서에도 근거가 없고, 그 값으로 '양호/주의'를 판정하는 것은 없는 권위를
만들어내는 셈이었다.

대신 같은 지표에서 프로들이 실제로 얼마나 다른지를 쓴다. "잘 던지는 사람들 사이에서도
이만큼은 다르다"는 실측이므로, 그 범위를 벗어난 차이만 짚는 것이 정직하다.

허용치는 프로 캐시가 갱신될 때 한 번만 계산한다. 프로 골격은 영상이 아니라 CSV라
포즈·구간 계산이 pandas 연산뿐이고 영상 디코딩이 없다. 요청마다 계산하면 최고의 1구
비교에서는 비교 대상이 하나뿐이라 편차를 구할 수 없어 모드마다 기준이 달라진다.
한 번 계산해 두면 두 모드가 같은 기준을 쓴다.
"""

from __future__ import annotations

import math
import statistics
from io import StringIO
from typing import Any, Sequence

import pandas as pd

from analysis.coaching_feedback import AXIS_RULES
from analysis.joint_angles import ANGLE_RULES
from analysis.normalization import build_body_frame_pose
from analysis.phase import detect_pitch_phases
from analysis.phase_metrics import angle_value_at_phase, axis_value_at_phase
from analysis.pro_cache import cache_status, get_cached_pro_skeletons

# 표본이 이보다 적으면 편차를 신뢰할 수 없다. 프로 6명 중 관절이 가려져 값을 못 구한
# 사람이 있을 수 있어 실제 표본은 6보다 작아질 수 있다.
MIN_PRO_SAMPLES = 3

_memo_key: object = object()
_memo: dict[str, float] = {}


def spread_of(values: Sequence[float | None]) -> float | None:
    """프로들 값의 모표준편차. 쓸 수 없으면 None을 돌려 상수 폴백으로 넘긴다."""
    usable = [float(v) for v in values if v is not None and math.isfinite(float(v))]
    if len(usable) < MIN_PRO_SAMPLES:
        return None
    spread = float(statistics.pstdev(usable))
    if not math.isfinite(spread) or spread <= 0.0:
        # 프로들이 모두 같은 값이면 편차가 0이다. 그대로 쓰면 아무리 작은 차이도
        # '주의'가 되고, 게이지 축척도 0이 되어 화면이 깨진다.
        return None
    return spread


def build_tolerance_table(pro_poses: Sequence[tuple[pd.DataFrame, Any]]) -> dict[str, float]:
    """지표별 허용치 표. 편차를 구하지 못한 지표는 아예 넣지 않는다(상수 폴백)."""
    table: dict[str, float] = {}
    for rule in AXIS_RULES:
        values = [axis_value_at_phase(pose, phases, rule)[0] for pose, phases in pro_poses]
        spread = spread_of(values)
        if spread is not None:
            table[rule.category] = spread
    for rule in ANGLE_RULES:
        values = [angle_value_at_phase(pose, phases, rule)[0] for pose, phases in pro_poses]
        spread = spread_of(values)
        if spread is not None:
            table[rule.category] = spread
    return table


def tolerance_table_from_skeletons(pro_skeletons: Sequence[dict[str, Any]]) -> dict[str, float]:
    """프로 캐시 항목(골격 CSV)에서 허용치 표를 만든다."""
    pro_poses: list[tuple[pd.DataFrame, Any]] = []
    for item in pro_skeletons:
        csv_text = item.get("skeleton_data")
        if not isinstance(csv_text, str) or not csv_text.strip():
            continue
        try:
            frame = pd.read_csv(StringIO(csv_text))
        except (ValueError, pd.errors.ParserError):
            continue
        if frame.empty:
            continue
        pose = build_body_frame_pose(frame)
        if pose.table.empty:
            continue
        pro_poses.append((pose.table, detect_pitch_phases(pose.table)))
    return build_tolerance_table(pro_poses)


def get_tolerance_table() -> dict[str, float]:
    """현재 프로 캐시 기준 허용치 표. 캐시가 갱신될 때만 다시 계산한다."""
    global _memo_key, _memo
    key = cache_status().get("refreshedAt")
    if key != _memo_key:
        _memo = tolerance_table_from_skeletons(get_cached_pro_skeletons())
        _memo_key = key
    return _memo
