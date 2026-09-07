from __future__ import annotations

import pandas as pd

from analysis.limb_consistency import LOWER_BODY_PAIRS, resolve_side_swaps


def _leg_frame(frame: int, left_x: float, left_y: float, right_x: float, right_y: float) -> dict[str, float]:
    row: dict[str, float] = {"frame_index": float(frame)}
    for side, (x, y) in (("left", (left_x, left_y)), ("right", (right_x, right_y))):
        row[f"{side}_foot_index_x_smooth"] = x
        row[f"{side}_foot_index_y_smooth"] = y
        row[f"{side}_foot_index_x"] = x
        row[f"{side}_foot_index_y"] = y
        row[f"{side}_foot_index_confidence"] = 0.9
    return row


def _swapped_after(swap_from: int, total: int = 40) -> pd.DataFrame:
    """왼발은 왼쪽에 머물고 오른발만 앞으로 나가는 신호.

    swap_from 프레임부터 라벨이 통째로 뒤바뀐 채로 이어진다 — MediaPipe가 좌우를
    혼동하면 값이 튀지 않고 이렇게 '매끄럽게' 뒤바뀐다.
    """
    rows = []
    for frame in range(total):
        true_left = (0.20, 0.80)
        true_right = (0.30 + (0.01 * frame), 0.80 - (0.005 * frame))
        if frame >= swap_from:
            rows.append(_leg_frame(frame, *true_right, *true_left))
        else:
            rows.append(_leg_frame(frame, *true_left, *true_right))
    return pd.DataFrame(rows)


def test_sustained_label_swap_is_undone() -> None:
    """지속되는 뒤바뀜을 되돌린다.

    뒤바뀜은 한 프레임짜리 튐이 아니라 그 뒤로 계속된다. 되돌리지 않으면 '왼발'
    신호가 도중에 오른발로 넘어가버려, 디딤발 궤적에 있지도 않은 착지가 생긴다.
    """
    fixed = resolve_side_swaps(_swapped_after(20))

    left_x = fixed["left_foot_index_x_smooth"].to_numpy()
    # 왼발은 처음부터 끝까지 제자리(0.20)에 있어야 한다.
    assert max(abs(value - 0.20) for value in left_x) < 1e-9


def test_moving_side_stays_continuous_after_correction() -> None:
    fixed = resolve_side_swaps(_swapped_after(20))

    right_x = fixed["right_foot_index_x_smooth"].to_numpy()
    # 오른발은 한 프레임에 0.01씩 단조롭게 전진해야 한다.
    steps = [right_x[i + 1] - right_x[i] for i in range(len(right_x) - 1)]
    assert all(abs(step - 0.01) < 1e-9 for step in steps)


def test_clean_signal_is_left_untouched() -> None:
    """뒤바뀜이 없으면 한 프레임도 건드리지 않는다. 거짓 양성이 더 위험하다."""
    clean = _swapped_after(swap_from=999)

    fixed = resolve_side_swaps(clean)

    for column in clean.columns:
        assert fixed[column].equals(clean[column]), f"{column}이(가) 바뀌었다"


def test_upper_body_is_not_touched() -> None:
    """상체는 회전 때문에 화면상 좌우가 진짜로 교차한다.

    실측 신호에서 상체 보정은 뒤집힘을 전혀 줄이지 못했고(어깨 3회 그대로,
    손목 5회 그대로) 보정만 45회 일어났다. 효과 없이 값만 흔드는 셈이라 제외한다.
    """
    assert "shoulder" not in LOWER_BODY_PAIRS
    assert "elbow" not in LOWER_BODY_PAIRS
    assert "wrist" not in LOWER_BODY_PAIRS

    frame = _swapped_after(20)
    frame["left_shoulder_x_smooth"] = 0.40
    frame["right_shoulder_x_smooth"] = 0.10
    frame["left_shoulder_y_smooth"] = 0.30
    frame["right_shoulder_y_smooth"] = 0.30

    fixed = resolve_side_swaps(frame)

    assert fixed["left_shoulder_x_smooth"].eq(0.40).all()
    assert fixed["right_shoulder_x_smooth"].eq(0.10).all()


def test_missing_columns_are_tolerated() -> None:
    """일부 관절 컬럼이 없는 CSV에서도 깨지지 않아야 한다."""
    frame = _swapped_after(20).drop(columns=["left_foot_index_x_smooth"])

    fixed = resolve_side_swaps(frame)

    assert len(fixed) == len(frame)


if __name__ == "__main__":
    test_sustained_label_swap_is_undone()
    test_moving_side_stays_continuous_after_correction()
    test_clean_signal_is_left_untouched()
    test_upper_body_is_not_touched()
    test_missing_columns_are_tolerated()
    print("ok")
