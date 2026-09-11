from __future__ import annotations

import pandas as pd

from analysis.limb_consistency import LOWER_BODY_PAIRS, SMOOTH_WINDOW, resolve_side_swaps


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

    *_smooth는 실제 입력과 같게 원본의 5프레임 중심 이동평균으로 만든다. 예전에는
    원본을 그대로 복사해 뒀는데, 그러면 평활이 뒤바뀜을 앞뒤로 뭉개는 성질 자체가
    픽스처에서 사라져 진짜 데이터에서 벌어지는 일을 재현하지 못한다.
    """
    rows = []
    for frame in range(total):
        true_left = (0.20, 0.80)
        true_right = (0.30 + (0.01 * frame), 0.80 - (0.005 * frame))
        if frame >= swap_from:
            rows.append(_leg_frame(frame, *true_right, *true_left))
        else:
            rows.append(_leg_frame(frame, *true_left, *true_right))
    table = pd.DataFrame(rows)
    for side in ("left", "right"):
        for axis in ("x", "y"):
            column = f"{side}_foot_index_{axis}"
            table[f"{column}_smooth"] = (
                table[column].rolling(window=SMOOTH_WINDOW, center=True, min_periods=1).mean()
            )
    return table


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

    # 오른발 원본은 한 프레임에 0.01씩 전진한다. 보정이 라벨만 되돌리고 값은
    # 건드리지 않았는지 여기서 본다.
    right_x = fixed["right_foot_index_x"].to_numpy()
    steps = [right_x[i + 1] - right_x[i] for i in range(len(right_x) - 1)]
    assert all(abs(step - 0.01) < 1e-9 for step in steps), steps

    # 평활값은 창 크기 때문에 양 끝에서 스텝이 줄어든다(이동평균의 성질이다).
    # 요구할 것은 정확한 간격이 아니라 뒤로 밀리는 구간이 없다는 것이다.
    smooth_x = fixed["right_foot_index_x_smooth"].to_numpy()
    assert all(
        smooth_x[i + 1] > smooth_x[i] for i in range(len(smooth_x) - 1)
    ), "평활 궤적이 도중에 뒤로 밀렸다"


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


def _briefly_swapped(swap_frames: tuple[int, ...], total: int = 40) -> pd.DataFrame:
    """두 프레임만 뒤바뀐 신호. 김광현 99~100프레임에서 실제로 본 형태다.

    왼발은 화면 위로 올라가고(팔로스루에서 축발이 뜬다) 오른발은 디딤발로 멈춰
    있다. 그 사이 두 프레임만 라벨이 서로 바뀐다.
    """
    rows = []
    for frame in range(total):
        true_left = (0.20, 0.80 - (0.01 * frame))
        true_right = (0.60, 0.80)
        if frame in swap_frames:
            rows.append(_leg_frame(frame, *true_right, *true_left))
        else:
            rows.append(_leg_frame(frame, *true_left, *true_right))
    table = pd.DataFrame(rows)
    for side in ("left", "right"):
        for axis in ("x", "y"):
            column = f"{side}_foot_index_{axis}"
            table[f"{column}_smooth"] = (
                table[column].rolling(window=SMOOTH_WINDOW, center=True, min_periods=1).mean()
            )
    return table


def test_short_swap_hidden_by_smoothing_is_still_found() -> None:
    """평활값에서 지워진 짧은 뒤바뀜도 잡아야 한다.

    판정을 *_smooth로 하면 이 신호에서 한 프레임도 보정하지 못한다. 5프레임
    이동평균이 두 프레임짜리 교환을 앞뒤로 뭉개, 두 발이 자리를 바꾼 것이 아니라
    디딤발이 잠깐 솟았다 돌아온 것처럼 보이기 때문이다. 실제 영상에서 이것이
    착지 검출을 22프레임 밀어냈다(김광현 78 -> 104).
    """
    table = _briefly_swapped((20, 21))

    fixed = resolve_side_swaps(table)

    # 디딤발(오른발)은 처음부터 끝까지 제자리에 멈춰 있어야 한다.
    right_y = fixed["right_foot_index_y"].to_numpy()
    assert max(abs(value - 0.80) for value in right_y) < 1e-9, "디딤발 원본이 흔들렸다"


def test_neighbour_frames_are_resmoothed_after_a_swap() -> None:
    """뒤바뀐 프레임만 되돌리는 것으로는 부족하다.

    평활은 창 크기만큼 앞뒤로 값을 섞기 때문에, 뒤바뀐 값은 이웃 프레임의
    평활값에도 이미 들어가 있다. 원본만 고치고 평활을 그대로 두면 그 이웃들이
    두 다리가 섞인 값으로 남고, 구간 검출은 평활값을 본다.
    """
    fixed = resolve_side_swaps(_briefly_swapped((20, 21)))

    smooth = fixed["right_foot_index_y_smooth"].to_numpy()
    assert max(abs(value - 0.80) for value in smooth) < 1e-9, "이웃 프레임 평활값에 뒤바뀐 값이 남았다"
