"""좌우 라벨 시간 일관성 보정.

후면 촬영에서는 두 다리가 화면상 겹쳐 보여 MediaPipe가 좌우를 혼동한다. 이때
좌표 자체는 정확하고 라벨만 뒤바뀌기 때문에, visibility(신뢰도)로는 잡히지 않는다.
실측 영상에서 신뢰도는 0.78을 유지했고 프레임 간 변화가 0.03을 넘은 적도 없었지만,
투구 구간에서 "어느 발이 아래인가"가 1.7초 사이 5번 뒤바뀌었다.

뒤바뀜은 한 프레임짜리 튐이 아니라 그 뒤로 계속된다. 그래서 '왼발' 신호가 도중에
오른발로 넘어가버리고, 디딤발 궤적에 있지도 않은 착지가 생긴다.

각 프레임에서 좌/우 배정을 그대로 둘 때와 맞바꿀 때 중, 직전(보정된) 프레임에서
덜 움직이는 쪽을 고른다. 몸이 실제로 회전해 팔다리가 화면상 교차해도 연속성
기준이라 올바르게 따라간다.

**판정은 평활값이 아니라 원본 좌표로 한다.** 입력 CSV의 `*_smooth`는 원본의
5프레임 중심 이동평균인데(전 영상 30컬럼에서 오차 1e-6로 확인), 평활은 짧은
뒤바뀜을 앞뒤로 뭉개 깨끗한 교환을 지워버린다. 김광현 99~100프레임의 두 프레임
뒤바뀜이 그랬다 — 원본에서는 두 발 값이 통째로 자리를 바꾸는데, 평활값에서는
97~102에 걸쳐 디딤발이 3%쯤 솟았다 돌아오는 모양이 되어 "맞바꾸는 편이 낫다"는
신호가 사라진다. 실제로 이 영상은 보정 프레임이 0개였고, 그 뭉개진 함몰이
착지 검출을 22프레임 밀어냈다.

원본을 고친 뒤에는 `*_smooth`를 보정된 원본에서 다시 계산한다. 뒤바뀐 프레임만
맞바꾸면 그 값이 섞여 들어간 이웃 프레임의 평활값은 그대로 틀린 채 남는다.

**하체에만 적용한다.** 상체는 투구 중 몸이 90도 가까이 돌아 좌우가 진짜로 교차하고,
실측에서 상체 보정은 뒤집힘을 전혀 줄이지 못한 채(어깨 3회·손목 5회 그대로) 값만
45번 흔들었다. 상체의 좌우 혼동은 깊이(z) 없이는 풀기 어렵다 — 지금 추출 파이프라인은
landmark.z를 읽지 않는다.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

LOWER_BODY_PAIRS = ("hip", "knee", "ankle", "foot_index")

# 맞바꾼 쪽이 "확실히" 나을 때만 바꾼다. 두 관절이 가까울 때는 두 배정의 이동량이
# 비슷해져, 여유 없이 두면 노이즈만으로 계속 뒤집는다(팔꿈치에서 360프레임 중
# 157번 뒤집혔다). 0.5~0.7 사이에서는 실측 결과가 같았고 그 중간값을 쓴다.
SWAP_MARGIN = 0.6


# 입력 CSV의 *_smooth를 만든 창 크기. 여기서 재계산할 때도 같은 값을 써야
# 보정하지 않은 프레임의 값이 원본과 어긋나지 않는다.
SMOOTH_WINDOW = 5


def resolve_side_swaps(
    keypoints_df: pd.DataFrame,
    pairs: tuple[str, ...] = LOWER_BODY_PAIRS,
    margin: float = SWAP_MARGIN,
) -> pd.DataFrame:
    """좌우가 뒤바뀐 프레임을 되돌린 keypoints를 새로 만들어 돌려준다."""
    if keypoints_df.empty:
        return keypoints_df

    corrected = keypoints_df.copy()
    touched: list[str] = []
    for joint in pairs:
        swapped = _swapped_frames(keypoints_df, joint, margin)
        if swapped is None or not swapped.any():
            continue
        _apply_swap(corrected, keypoints_df, joint, swapped)
        touched.append(joint)
    if touched:
        _recompute_smoothed(corrected, touched)
    return corrected


def _recompute_smoothed(corrected: pd.DataFrame, joints: list[str]) -> None:
    """보정된 원본으로 *_smooth를 다시 만든다.

    뒤바뀐 프레임만 맞바꾸고 평활값을 그대로 두면, 그 값이 섞여 들어간 이웃
    프레임(창 크기만큼 앞뒤)의 평활값은 여전히 두 다리가 섞인 값으로 남는다.
    """
    for joint in joints:
        for side in ("left", "right"):
            for axis in ("x", "y"):
                source_column = f"{side}_{joint}_{axis}"
                smooth_column = f"{source_column}_smooth"
                if source_column not in corrected.columns or smooth_column not in corrected.columns:
                    continue
                values = pd.to_numeric(corrected[source_column], errors="coerce")
                corrected[smooth_column] = values.rolling(
                    window=SMOOTH_WINDOW, center=True, min_periods=1
                ).mean()


def _swapped_frames(keypoints_df: pd.DataFrame, joint: str, margin: float) -> np.ndarray | None:
    left = _side_xy(keypoints_df, "left", joint)
    right = _side_xy(keypoints_df, "right", joint)
    if left is None or right is None:
        return None

    left_x, left_y = left
    right_x, right_y = right
    swapped = np.zeros(len(keypoints_df), dtype=bool)
    previous_left = (left_x[0], left_y[0])
    previous_right = (right_x[0], right_y[0])

    for index in range(1, len(keypoints_df)):
        current_left = (left_x[index], left_y[index])
        current_right = (right_x[index], right_y[index])
        keep = _step(current_left, previous_left) + _step(current_right, previous_right)
        swap = _step(current_right, previous_left) + _step(current_left, previous_right)
        if swap < (keep * margin):
            current_left, current_right = current_right, current_left
            swapped[index] = True
        previous_left, previous_right = current_left, current_right

    return swapped


def _side_xy(keypoints_df: pd.DataFrame, side: str, joint: str) -> tuple[np.ndarray, np.ndarray] | None:
    """뒤바뀜 판정에 쓸 좌표. 원본이 있으면 원본을 쓴다(평활은 교환을 뭉갠다)."""
    x_column = f"{side}_{joint}_x"
    y_column = f"{side}_{joint}_y"
    if x_column not in keypoints_df.columns or y_column not in keypoints_df.columns:
        x_column = f"{side}_{joint}_x_smooth"
        y_column = f"{side}_{joint}_y_smooth"
    if x_column not in keypoints_df.columns or y_column not in keypoints_df.columns:
        return None
    x = pd.to_numeric(keypoints_df[x_column], errors="coerce").to_numpy(dtype=float)
    y = pd.to_numeric(keypoints_df[y_column], errors="coerce").to_numpy(dtype=float)
    if not np.isfinite(x).any() or not np.isfinite(y).any():
        return None
    return x, y


def _step(current: tuple[float, float], previous: tuple[float, float]) -> float:
    """직전 위치에서 얼마나 움직였는가. 값을 못 구한 프레임은 판단에 쓰지 않는다."""
    if not all(np.isfinite(value) for value in (*current, *previous)):
        return 0.0
    return float(np.hypot(current[0] - previous[0], current[1] - previous[1]))


def _apply_swap(
    corrected: pd.DataFrame, source: pd.DataFrame, joint: str, swapped: np.ndarray
) -> None:
    """뒤바뀐 프레임에서 해당 관절의 left_/right_ 컬럼을 통째로 맞바꾼다.

    좌표뿐 아니라 신뢰도·보간 플래그까지 함께 옮겨야 한쪽만 어긋나지 않는다.
    """
    prefix = f"left_{joint}"
    for left_column in [column for column in source.columns if column.startswith(prefix)]:
        right_column = "right_" + left_column[len("left_") :]
        if right_column not in source.columns:
            continue
        corrected.loc[swapped, left_column] = source.loc[swapped, right_column].to_numpy()
        corrected.loc[swapped, right_column] = source.loc[swapped, left_column].to_numpy()
