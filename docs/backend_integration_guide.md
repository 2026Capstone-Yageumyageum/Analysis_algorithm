# 백엔드 연동 가이드

이 문서는 백엔드 팀원이 Python 유사도 분석 서버 응답을 DB 저장과 프론트 응답으로 연결할 때 필요한 DTO 기준을 정리합니다.

엔드포인트와 응답 스키마의 형식화된 초안은 `docs/openapi.yaml`을 함께 참고합니다.

## 전체 흐름

```text
Frontend
-> Backend
   사용자 영상 파일, 구종, 로컬 영상 ID 전달
-> Python Analysis Server
   userVideo, metadata 전달
   프로 skeleton 데이터는 서버 시작/갱신 시 백엔드에서 받아 캐싱
-> Backend
   사용자 skeleton CSV, Top 3 프로 비교 점수, phase 정보 저장
-> Frontend
   Top 3 점수, phase, 사용자 displayKeypoints 전달
```

## Backend -> Python 요청 DTO

연동 초기화 또는 배포 확인 단계에서는 먼저 아래 엔드포인트로 스키마 메타데이터를 확인할 수 있습니다.

```http
GET /api/schema
```

백엔드는 여기서 `responseSchemaVersion`, `supportedCameraViews`, `similarity.algorithmName`, `similarity.scoreScale`, `keypointsCsvColumns`를 확인할 수 있습니다.

프로 skeleton 캐시 상태는 아래 엔드포인트로 확인합니다.

```http
GET /api/pro-skeleton-cache
POST /api/pro-skeleton-cache/refresh
```

`GET`은 현재 캐시된 프로 reference 개수와 source를 반환합니다. `POST`는 Python 서버가 가진 `PRO_SKELETON_DATA_URL` 또는 `PRO_SKELETON_DATA_FILE` 기준으로 다시 로드합니다.

`multipart/form-data` 요청입니다.

파일/문자열 필드:

- `userVideo`

문자열 필드:

- `metadata`: 아래 JSON을 문자열화한 값

```json
{
  "videoId": "user_video_001",
  "analysisType": "pro_similarity",
  "pitchType": "직구",
  "cameraView": "rear",
  "user": {
    "videoId": "user_video_001",
    "localVideoId": "device_local_video_001"
  },
  "speed": {
    "user": {
      "releaseFrame": 120,
      "arrivalFrame": 148,
      "targetDistanceM": 16.0,
      "releaseExtensionM": 1.5
    }
  }
}
```

프로 skeleton 데이터는 분석 요청마다 보내지 않고, Python 서버가 시작될 때 백엔드 API에서 받아와 메모리에 캐싱합니다. 개발/검증 환경에서는 로컬 JSON 파일을 캐시 소스로 사용할 수 있습니다.

Python 서버 실행 환경변수:

```bash
PRO_SKELETON_DATA_URL=https://backend.example.com/internal/pro-skeletons
```

또는 로컬 검증용:

```bash
PRO_SKELETON_DATA_FILE=/path/to/pro_skeleton_data.json
```

백엔드가 Python 서버에 제공해야 하는 프로 skeleton 데이터 예시는 다음과 같습니다.

```json
[
  {
    "proId": "123123213",
    "playerName": "류현진",
    "skeletonDataId": "pro_skeleton_ryu_001",
    "keypointsCsvText": "frame_index,time_sec,nose_x,nose_y,...",
    "frameCount": 180,
    "fps": 30.0,
    "resolution": "1280x720"
  },
  {
    "proId": "123123214",
    "playerName": "프로 선수 2",
    "skeletonDataId": "pro_skeleton_002",
    "keypointsCsvText": "frame_index,time_sec,nose_x,nose_y,...",
    "frameCount": 210,
    "fps": 30.0,
    "resolution": "1280x720"
  }
]
```

`metadata.user`, `metadata.speed`, `metadata.speed.user`는 값이 있을 경우 JSON object로 보내야 합니다. object가 아닌 값은 Python 서버에서 `400 bad_request`로 거부합니다.

프로 skeleton cache payload의 각 항목은 최소 `proId`, `keypointsCsvText`를 포함해야 합니다. Python 서버는 캐싱된 전체 프로 skeleton 목록을 비교하고 `overallScore` 기준 Top 3만 응답합니다.

구속 계산을 함께 요청할 때는 `arrivalFrame > releaseFrame`, `fps > 0`, `targetDistanceM - releaseExtensionM > 0` 조건을 만족해야 합니다. 조건을 만족하지 않으면 분석 요청 자체는 성공할 수 있지만, 해당 `speed.user` 또는 `speed.pro`는 `status: invalid`로 내려갑니다.

OpenCV가 영상 fps를 읽지 못하면 `videoMeta.fps`는 `0`으로 내려갈 수 있습니다. 이 경우 구속 계산은 `metadata.speed.*.fps`가 있으면 그 값을 우선 사용하고, 없으면 내부 기본값 `60.0`을 fallback으로 사용합니다.

`speed.*.status`가 `ready`이면 `speedKmh`, `speedMps`, `releaseFrame`, `arrivalFrame`, `frameDelta`, `fps`, `targetDistanceM`, `releaseExtensionM`, `effectiveDistanceM`, `flightTimeSec`를 저장 대상으로 봅니다.

## Python -> Backend 응답 DTO

백엔드는 이 응답을 저장 기준으로 사용합니다.

```json
{
  "videoId": "user_video_001",
  "status": "completed",
  "responseSchemaVersion": "pitch_analysis_response_v1",
  "analysisType": "pro_similarity",
  "pitchType": "직구",
  "cameraView": "rear",
  "algorithmName": "body_frame_phase_direction_vector_v1",
  "scoreScale": "0~100",
  "user_data": {
    "skeleton_data_id": "user_skeleton_8f31d2a9",
    "skeleton_data": "frame_index,time_sec,...",
    "frame_count": 123,
    "fps": 60.0,
    "resolution": "1920x1080"
  },
  "players": [
    {
      "rank": 1,
      "analysisId": "analysis_1",
      "proId": "123123213",
      "overallScore": 82,
      "phaseScores": []
    }
  ]
}
```

오류 응답은 아래 형태로 처리합니다.

```json
{
  "status": "error",
  "error": {
    "code": "bad_request",
    "message": "userVideo 파일이 필요합니다."
  }
}
```

백엔드는 `status`가 `error`이면 분석 결과 저장 대신 `error.code`, `error.message`를 기준으로 재시도 안내 또는 사용자 메시지를 만듭니다.

## DB 저장 권장 구조

처음에는 정규화된 테이블을 과하게 나누지 않고, 원문 보존을 우선합니다.

### `pitch_analysis`

| 필드 | 타입 예시 | 설명 |
| --- | --- | --- |
| `video_id` | varchar | Python 응답의 `videoId` |
| `user_id` | varchar | 사용자 ID |
| `analysis_type` | varchar | `pro_similarity` |
| `pitch_type` | varchar | 직구, 슬라이더 등 |
| `camera_view` | varchar | 현재는 `rear` 고정 |
| `response_schema_version` | varchar | Python 응답 스키마 버전 |
| `algorithm_name` | varchar | 알고리즘 버전 |
| `score_scale` | varchar | 현재는 `0~100` |
| `players_json` | json/text | Python 응답의 Top 3 `players` 원문 |
| `top_overall_score` | decimal | `players[0].overallScore` |
| `top_pro_id` | varchar | `players[0].proId` |
| `created_at` | timestamp | 저장 시각 |

### `pitch_user_skeleton`

| 필드 | 타입 예시 | 설명 |
| --- | --- | --- |
| `video_id` | varchar | `pitch_analysis.video_id` |
| `skeleton_data_id` | varchar | Python 응답의 `user_data.skeleton_data_id` |
| `keypoints_csv_text` | longtext | Python 응답의 `user_data.skeleton_data` |
| `frame_count` | integer | Python 응답의 `user_data.frame_count` |
| `fps` | decimal | Python 응답의 `user_data.fps` |
| `resolution` | varchar | 예: `1920x1080` |

### `pitch_analysis_player_match`

| 필드 | 타입 예시 | 설명 |
| --- | --- | --- |
| `analysis_id` | varchar | Python 응답의 `players[].analysisId` |
| `video_id` | varchar | 사용자 영상 ID |
| `rank` | integer | Top 3 순위 |
| `pro_id` | varchar | reference model ID |
| `overall_score` | decimal | 프로 skeleton과의 전체 유사도 |
| `phase_scores_json` | json/text | `players[].phaseScores` 원문 |

이렇게 분리하면 사용자 skeleton CSV 저장, Top 3 비교 결과 조회, phase 상세 조회를 분리할 수 있습니다. 프로 skeleton CSV는 이미 백엔드 DB에 저장되어 있으므로 Python 응답에서 다시 저장하지 않습니다.

## Backend -> Frontend 결과 응답 DTO

프론트에는 CSV 원문을 그대로 보내지 않는 것을 권장합니다. 백엔드가 `keypointsCsvText`를 파싱해서 `_smooth` 좌표 중심의 `displayKeypoints`로 변환합니다.

```json
{
  "videoId": "user_video_001",
  "pitchType": "직구",
  "userSkeletonDataId": "user_skeleton_8f31d2a9",
  "players": [
    {
      "rank": 1,
      "analysisId": "analysis_1",
      "proId": "123123213",
      "playerName": "류현진",
      "overallScore": 82,
      "phaseScores": [
        {
          "phase": "leg_lift",
          "label": "레그 리프트",
          "score": 86,
          "userStartFrame": 40,
          "userEndFrame": 92,
          "proStartFrame": 80,
          "proEndFrame": 145
        }
      ]
    }
  ],
  "videos": {
    "user": {
      "localVideoId": "device_local_video_001",
      "fps": 60.0,
      "width": 1080,
      "height": 1920,
      "durationSec": 4.2
    },
    "pro": {
      "proId": "123123213",
      "playerName": "류현진",
      "fps": 30.0,
      "width": 1280,
      "height": 720,
      "durationSec": 6.0
    }
  },
  "displayKeypoints": {
    "user": [],
    "pro": []
  }
}
```

## `displayKeypoints` 변환 규칙

CSV 한 행을 프론트 표시용 한 프레임으로 변환합니다.

```json
{
  "frameIndex": 40,
  "timeSec": 0.667,
  "phase": "leg_lift",
  "points": {
    "leftShoulder": {
      "x": 0.43,
      "y": 0.31,
      "confidence": 0.97,
      "imputed": false
    }
  }
}
```

변환 매핑:

| CSV 컬럼 | 프론트 필드 |
| --- | --- |
| `frame_index` | `frameIndex` |
| `time_sec` | `timeSec` |
| `{joint}_x_smooth` | `points.{joint}.x` |
| `{joint}_y_smooth` | `points.{joint}.y` |
| `{joint}_confidence` | `points.{joint}.confidence` |
| `{joint}_imputed_flag` | `points.{joint}.imputed` |

프론트 필드 이름은 camelCase를 권장합니다.

예시:

- `left_shoulder` -> `leftShoulder`
- `right_foot_index` -> `rightFootIndex`

`{joint}_imputed_flag` 컬럼이 없는 nose, shoulder, hip 계열 관절은 `imputed: false`로 내려주는 것을 기본값으로 둡니다.

좌표는 원본 영상 기준 0~1 정규화 좌표를 기본으로 하지만, MediaPipe 추정상 프레임 밖 관절은 0보다 작거나 1보다 클 수 있습니다. 백엔드는 원문 좌표를 보존하고, 프론트 렌더링 단계에서 clamp, 흐림 처리, 미표시 중 하나를 선택합니다.

## phase 매핑 규칙

각 keypoint frame의 `phase`는 선택된 `players[].phaseScores`의 frame 범위를 보고 백엔드가 부여합니다.

```text
if selectedPlayer.phaseScores[].userStartFrame <= frameIndex <= selectedPlayer.phaseScores[].userEndFrame:
    phase = selectedPlayer.phaseScores[].phase
```

프로 skeleton을 화면에 함께 표시해야 하면, 선택된 `players[].proId`에 해당하는 백엔드 DB의 `pro_skeleton_data.keypointsCsvText`를 파싱하고 `proStartFrame`, `proEndFrame` 기준으로 phase를 매핑합니다.

## 변환 참조 구현

Python 기준 참조 구현은 아래 파일에 둡니다. 백엔드가 Kotlin/Spring에서 구현할 때도 같은 매핑 규칙을 따르면 됩니다.

```text
Analysis_algorithm/scripts/keypoints_csv_to_display_keypoints.py
```

사용 예시는 다음과 같습니다. 이 명령은 참조용이며, 실제 검증은 사용자 허가 후 진행합니다.

```bash
python Analysis_algorithm/scripts/keypoints_csv_to_display_keypoints.py \
  --csv keypoints.csv \
  --phase-json analysis_response.json \
  --target user \
  --output display_keypoints_user.json
```

## 보안/저장 정책

- 원본 영상은 저장하지 않습니다.
- Python 서버는 임시 파일로만 영상을 사용합니다.
- 백엔드는 `user_data.skeleton_data`와 Top 3 `players` 분석 JSON만 저장합니다.
- 프로 skeleton CSV는 별도 reference 데이터로 저장해두고, Python 서버 시작/갱신 시 캐시 API로 전달합니다.
- 원본 영상 재생은 사용자 기기에 저장된 로컬 영상 또는 별도 정책으로 관리되는 프로 영상 자산을 사용합니다.

## 참고 목업

백엔드 저장용 응답 JSON과 5프레임 skeleton CSV 예시는 `docs/service_response_mock.md`를 참고합니다.
