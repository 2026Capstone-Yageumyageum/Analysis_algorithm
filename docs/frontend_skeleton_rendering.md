# 프론트 skeleton 표시 데이터 구조

서비스 프론트는 사용자가 기기에 저장한 원본 영상을 재생하고, 백엔드가 내려준 keypoints를 같은 시간축에 맞춰 영상 위에 그립니다.

## 기본 흐름

```text
사용자 촬영
-> 앱이 원본 영상을 사용자 기기에 저장
-> Python 서버가 시작/갱신 시 백엔드에서 프로 skeleton reference를 캐싱
-> 백엔드가 Python 서버로 userVideo 전달
-> Python 서버가 user_data.skeleton_data와 Top 3 players 점수 반환
-> 백엔드가 사용자 skeleton CSV와 players 결과 저장
-> 프론트가 결과 조회
-> 프론트는 로컬 원본 영상 위에 displayKeypoints를 렌더링
```

## 프론트에는 CSV 원문보다 표시용 JSON 권장

백엔드는 `user_data.skeleton_data`를 DB에 저장하고, 프론트 결과 조회 시에는 다음처럼 `_smooth` 좌표만 파싱해서 내려주는 것을 권장합니다. 프로 skeleton을 함께 보여줄 때는 선택된 `players[].proId`에 해당하는 백엔드 reference CSV를 같은 규칙으로 파싱합니다.

```json
{
  "analysisId": "analysis_1",
  "videoLocalId": "user_video_001",
  "proId": "123123213",
  "fps": 60.0,
  "durationSec": 4.2,
  "phaseScores": [],
  "displayKeypoints": [
    {
      "frameIndex": 40,
      "timeSec": 0.667,
      "phase": "leg_lift",
      "points": {
        "leftShoulder": { "x": 0.43, "y": 0.31, "confidence": 0.97 },
        "rightShoulder": { "x": 0.56, "y": 0.32, "confidence": 0.96 },
        "leftElbow": { "x": 0.39, "y": 0.45, "confidence": 0.94 },
        "rightElbow": { "x": 0.61, "y": 0.46, "confidence": 0.93 }
      }
    }
  ]
}
```

백엔드의 CSV -> `displayKeypoints` 변환 규칙은 `docs/backend_integration_guide.md`에 정리합니다.

참조 구현은 `Analysis_algorithm/scripts/keypoints_csv_to_display_keypoints.py`에 있습니다. 실제 앱에서는 이 코드를 그대로 쓰기보다 백엔드 언어에 맞게 같은 필드 매핑을 구현하면 됩니다.

## 좌표 해석

좌표는 원본 영상 기준 0~1 정규화 좌표를 기본으로 합니다. 다만 MediaPipe 추정 결과가 프레임 밖으로 나간 관절은 0보다 작거나 1보다 클 수 있습니다.

```text
screenX = videoRenderWidth * x + videoRenderLeft
screenY = videoRenderHeight * y + videoRenderTop
```

영상이 `contain`으로 표시될 경우 여백이 생기므로, 실제 렌더링된 영상 영역의 `left`, `top`, `width`, `height` 기준으로 변환해야 합니다.

렌더링 단계에서는 다음 중 하나를 선택합니다.

- 좌표가 영상 영역 밖이면 선분을 잘라서 표시합니다.
- 좌표를 0~1 범위로 clamp하되, 해당 관절을 낮은 confidence처럼 흐리게 표시합니다.
- confidence가 너무 낮거나 좌표가 크게 벗어난 관절은 해당 프레임에서 표시하지 않습니다.

## 추천 skeleton 연결

```text
left_shoulder - right_shoulder
left_hip - right_hip
left_shoulder - left_elbow - left_wrist
right_shoulder - right_elbow - right_wrist
left_shoulder - left_hip - left_knee - left_ankle - left_foot_index
right_shoulder - right_hip - right_knee - right_ankle - right_foot_index
```

## 표시 품질 규칙

- `confidence`가 낮은 관절은 흐리게 표시합니다.
- 표시용 DTO의 `imputed`가 true인 관절은 점선 또는 다른 색으로 표시할 수 있습니다.
- 프론트 재생 시간에 가장 가까운 `timeSec` 프레임을 찾아 skeleton을 그립니다.
- phase별 비교 화면에서는 같은 phase의 user/pro skeleton을 나란히 보여주는 방식을 우선합니다.
