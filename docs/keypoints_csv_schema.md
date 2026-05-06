# keypointsCsvText 스키마

`keypointsCsvText`는 Python 서버가 영상에서 추출한 `keypoints.csv` 원문을 JSON 문자열로 담은 값입니다. 서비스 응답에서는 백엔드 저장용 기본 필드인 `user_data.skeleton_data`와 같은 값을 `user_data.keypointsCsvText` 호환 alias로 함께 내려줍니다.

## 의미

```json
{
  "keypointsCsvText": {
    "user": "사용자 영상 keypoints.csv 원문",
    "pro": "프로 영상 keypoints.csv 원문"
  }
}
```

- `user`: 사용자 영상에서 추출한 프레임별 관절 좌표
- `pro`: 프로 영상에서 추출한 프레임별 관절 좌표
- 각 행은 한 프레임을 의미합니다.
- 좌표는 원본 영상 크기 기준의 0~1 정규화 좌표를 기본으로 합니다.
- 실제 컬럼 순서의 source of truth는 Python 서버의 `GET /api/schema` 응답 중 `keypointsCsvColumns`와 `service/server/analysis/pose.py`의 `CSV_COLUMNS`입니다.

## 좌표와 confidence 해석

- `{joint}_x`, `{joint}_y`: MediaPipe가 반환한 원본 영상 기준 정규화 좌표입니다.
- `{joint}_x_smooth`, `{joint}_y_smooth`: 원본 좌표에 이동평균 smoothing을 적용한 표시/분석용 기본 좌표입니다.
- 좌표는 보통 0~1 범위이지만, 관절이 프레임 밖에 있거나 MediaPipe 추정이 흔들릴 때 0보다 작거나 1보다 큰 값이 나올 수 있습니다. 프론트는 렌더링 시 필요하면 화면 영역 기준으로 clamp하거나 confidence를 함께 보고 흐리게 표시합니다.
- MediaPipe가 `NaN/inf` 좌표를 반환하면 Python 서버는 이전 프레임의 해당 관절 좌표 또는 기본 fallback 좌표를 사용해 CSV에 비정상 숫자가 들어가지 않게 합니다.
- `{joint}_confidence`: MediaPipe `visibility` 기반 신뢰도입니다. Python 서버는 이 값을 0~1 범위로 정리합니다. 0에 가까울수록 해당 관절을 신뢰하기 어렵습니다.

## 필수 컬럼

```text
frame_index
time_sec
nose_x
nose_y
nose_confidence
left_shoulder_x
left_shoulder_y
left_shoulder_confidence
right_shoulder_x
right_shoulder_y
right_shoulder_confidence
left_elbow_x
left_elbow_y
left_elbow_confidence
right_elbow_x
right_elbow_y
right_elbow_confidence
left_wrist_x
left_wrist_y
left_wrist_confidence
right_wrist_x
right_wrist_y
right_wrist_confidence
left_hip_x
left_hip_y
left_hip_confidence
right_hip_x
right_hip_y
right_hip_confidence
left_knee_x
left_knee_y
left_knee_confidence
right_knee_x
right_knee_y
right_knee_confidence
left_ankle_x
left_ankle_y
left_ankle_confidence
right_ankle_x
right_ankle_y
right_ankle_confidence
left_foot_index_x
left_foot_index_y
left_foot_index_confidence
right_foot_index_x
right_foot_index_y
right_foot_index_confidence
```

## 보정 여부 컬럼

```text
left_elbow_imputed_flag
right_elbow_imputed_flag
left_wrist_imputed_flag
right_wrist_imputed_flag
left_knee_imputed_flag
right_knee_imputed_flag
left_ankle_imputed_flag
right_ankle_imputed_flag
left_foot_index_imputed_flag
right_foot_index_imputed_flag
```

`true`이면 해당 관절이 직접 검출된 값이 아니라 이전/이후 프레임 또는 smoothing으로 보정된 값입니다.

현재 imputed flag는 팔꿈치, 손목, 무릎, 발목, foot index에만 둡니다. nose, shoulder, hip 계열은 confidence와 smooth 좌표를 기준으로 처리합니다.

## smoothing 좌표 컬럼

프론트 skeleton 표시와 유사도 계산의 기본 입력은 원본 좌표보다 `_smooth` 좌표를 우선 사용합니다.

```text
nose_x_smooth
nose_y_smooth
left_shoulder_x_smooth
left_shoulder_y_smooth
right_shoulder_x_smooth
right_shoulder_y_smooth
left_elbow_x_smooth
left_elbow_y_smooth
right_elbow_x_smooth
right_elbow_y_smooth
left_wrist_x_smooth
left_wrist_y_smooth
right_wrist_x_smooth
right_wrist_y_smooth
left_hip_x_smooth
left_hip_y_smooth
right_hip_x_smooth
right_hip_y_smooth
left_knee_x_smooth
left_knee_y_smooth
right_knee_x_smooth
right_knee_y_smooth
left_ankle_x_smooth
left_ankle_y_smooth
right_ankle_x_smooth
right_ankle_y_smooth
left_foot_index_x_smooth
left_foot_index_y_smooth
right_foot_index_x_smooth
right_foot_index_y_smooth
```

## 투수 중심 및 품질 컬럼

```text
pitcher_com_x_smooth
pitcher_com_y_smooth
pitcher_detected
normalised_frame
no_missing_frames_flag
smooth_com_flag
```

- `pitcher_com_*_smooth`: 투수 몸 중심점
- `pitcher_detected`: 해당 프레임에서 투수 포즈가 검출됐는지 여부
- `normalised_frame`: 분석용 정규화 프레임 번호
- `no_missing_frames_flag`: 주요 관절 누락 여부
- `smooth_com_flag`: 중심점 smoothing 적용 여부

## 저장 정책

백엔드는 `keypointsCsvText`를 처음에는 `TEXT` 또는 `LONGTEXT`로 그대로 저장하는 방식을 권장합니다.

이후 검색/통계가 필요해지면 CSV 원문을 유지한 채 별도 파싱 테이블을 추가합니다.
