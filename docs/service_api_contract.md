# 서비스 API 연동 계약 초안

이 문서는 백엔드 서버가 Python 유사도 분석 서버에 요청하고, Python 서버가 백엔드에 돌려줘야 하는 데이터 구조를 정의합니다.

형식화된 OpenAPI 초안은 `docs/openapi.yaml`에 있습니다.

## 기본 원칙

- 촬영 방향은 후면(`rear`)으로 고정합니다.
- Python 서버는 `metadata.cameraView`가 비어 있거나 `rear`인 요청만 허용합니다.
- 원본 영상은 Python 서버와 백엔드 서버 모두 장기 저장하지 않습니다.
- Python 서버는 요청 처리 중 임시 파일로만 영상을 사용하고, 처리 후 삭제합니다.
- 백엔드는 Python 서버 응답 중 `user_data.skeleton_data`, Top 3 `players` 점수, phase 구간, 영상 메타데이터를 DB에 저장합니다.
- 프론트는 사용자가 기기에 저장한 원본 영상 위에 백엔드가 내려준 표시용 skeleton 좌표를 그립니다.

## Python 유사도 분석 서버 응답 데이터 설명

백엔드 서버는 사용자 투구 영상과 프로 선수 투구 분석 데이터를 Python 분석 서버로 전달하고, Python 서버는 분석 결과를 JSON으로 반환합니다.

중요한 변경점은 프로 선수 입력입니다. 서비스 구조에서는 프로 영상을 매번 보내지 않고, Python 서버가 시작될 때 백엔드 DB에 이미 저장된 프로 선수의 `skeleton_data` 목록을 받아 메모리에 캐싱합니다. 이후 분석 요청에서는 사용자 영상만 새로 포즈 추출한 뒤, 캐싱된 프로 skeleton 데이터들과 비교합니다.

요청 구조는 `multipart/form-data`입니다.

- `userVideo`: 사용자 투구 영상 파일
- `metadata`: 분석 설정 JSON 문자열

프로 skeleton 데이터는 요청 본문에 넣지 않고, 서버 시작 시 아래 환경변수를 통해 로드합니다.

- `PRO_SKELETON_DATA_URL`: 백엔드가 제공하는 프로 skeleton 목록 JSON API
- `PRO_SKELETON_DATA_FILE`: 로컬 검증용 프로 skeleton 목록 JSON 파일

Python 서버는 원본 영상을 저장하지 않습니다. 분석 후 백엔드에 아래 데이터를 반환합니다.

- 사용자 영상 keypoints CSV
- 사용자 영상 frame count, fps, resolution
- 서버 캐시에 저장된 프로 skeleton 데이터 목록과 비교한 Top 3 결과
- Top 3 선수별 전체 유사도 점수
- Top 3 선수별 phase 유사도 점수
- Top 3 선수별 phase 시작/끝 프레임

## 백엔드 -> Python 서버 요청

스키마 메타데이터 확인 엔드포인트:

```http
GET /api/schema
```

이 엔드포인트는 영상 처리 없이 `responseSchemaVersion`, 지원 카메라 방향, 알고리즘명, 점수 범위, `keypointsCsvColumns`를 반환합니다.

프로 skeleton cache 확인/갱신 엔드포인트:

```http
GET /api/pro-skeleton-cache
POST /api/pro-skeleton-cache/refresh
```

백엔드는 배포/서버 시작 후 `GET /api/pro-skeleton-cache`로 Python 서버가 프로 reference를 몇 개 캐싱했는지 확인할 수 있습니다. `POST /api/pro-skeleton-cache/refresh`는 `PRO_SKELETON_DATA_URL` 또는 `PRO_SKELETON_DATA_FILE` 기준으로 캐시를 다시 로드합니다.

엔드포인트:

```http
POST /api/analyze
Content-Type: multipart/form-data
```

파일/문자열 파트:

- `userVideo`: 사용자 투구 영상 파일
- `metadata`: 분석 설정 JSON 문자열

`metadata` 예시:

```json
{
  "videoId": "user_video_001",
  "analysisType": "pro_similarity",
  "pitchType": "직구",
  "cameraView": "rear",
  "user": {
    "videoId": "user_video_001"
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

Python 서버가 시작 시 백엔드에서 받아와 캐싱하는 프로 skeleton 데이터 예시:

```json
[
  {
    "proId": "123123213",
    "playerName": "류현진",
    "skeletonDataId": "pro_skeleton_ryu_001",
    "skeleton_data": "frame_index,time_sec,nose_x,nose_y,...\n0,0.000,0.51,0.18,...",
    "frameCount": 180,
    "fps": 30.0,
    "resolution": "1280x720"
  },
  {
    "proId": "123123214",
    "playerName": "프로 선수 2",
    "skeletonDataId": "pro_skeleton_002",
    "skeleton_data": "frame_index,time_sec,nose_x,nose_y,...",
    "frameCount": 210,
    "fps": 30.0,
    "resolution": "1280x720"
  }
]
```

`metadata.user`, `metadata.speed`, `metadata.speed.user`는 값이 있을 경우 JSON object여야 합니다. 문자열이나 배열처럼 object가 아닌 값이 들어오면 Python 서버는 `400 bad_request`로 응답합니다.

프로 skeleton cache payload는 JSON array이거나, `pro_skeleton_data`, `proSkeletonData`, `items`, `data` 중 하나의 key에 array를 담은 object여야 합니다. 각 항목은 최소 `proId`와 `skeleton_data`를 포함해야 합니다.

Python 서버는 서버 캐시 전체를 비교한 뒤 `overallScore` 기준 상위 3개만 응답의 `players`에 담습니다.

구속 계산용 `speed` 값은 `arrivalFrame > releaseFrame`, `fps > 0`, `targetDistanceM - releaseExtensionM > 0` 조건을 만족해야 합니다. 조건을 만족하지 않으면 해당 구속 결과는 `status: invalid`로 응답됩니다.

## Python 서버 -> 백엔드 응답

응답 핵심:

- `videoId`: 사용자 영상 ID
- `status`: 분석 상태
- `user_data.skeleton_data_id`: 사용자 skeleton CSV를 DB에 저장할 때 사용할 유니크 ID
- `user_data.skeleton_data`: 사용자 영상에서 추출한 keypoints CSV 원문
- `user_data.frame_count`: 사용자 영상 프레임 수
- `user_data.fps`: 사용자 영상 FPS
- `user_data.resolution`: 사용자 영상 해상도
- `players`: 프로 skeleton 목록과 비교한 상위 3개 결과. 각 항목은 `analysisId`, `proId`, `overallScore`, `phaseScores`, `release`, `feedback`을 포함합니다.

응답 예시:

```json
{
  "videoId": "user_video_001",
  "status": "completed",
  "user_data": {
    "skeleton_data_id": "user_skeleton_8f31d2a9",
    "skeleton_data": "frame_index,time_sec,nose_x,nose_y,...\n0,0.000,0.51,0.18,...",
    "frame_count": 123,
    "fps": 60.0,
    "resolution": "1920x1080"
  },
  "players": [
    {
      "analysisId": "analysis_1",
      "proId": "123123213",
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
      ],
      "release": {
        "proFrame": 176.5,
        "userFrame": 128.5,
        "pro": {
          "frame": 176.5,
          "beforeFrame": 176,
          "exitFrame": 177,
          "method": "pose_proxy_midpoint_v1",
          "status": "fallback",
          "source": "throwing_wrist_speed_body"
        },
        "user": {
          "frame": 128.5,
          "beforeFrame": 128,
          "exitFrame": 129,
          "method": "ball_exit_midpoint_v1",
          "status": "ready",
          "source": "bright_or_motion_aligned_ball_blob"
        },
        "timing": {
          "proPitchPercent": 84,
          "userPitchPercent": 91,
          "differencePercent": 7,
          "message": "릴리즈 타이밍이 선수와 비슷합니다."
        },
        "point": {
          "difference": 0.18,
          "heightDifference": -0.08,
          "sideDifference": 0.16,
          "message": "릴리즈 포인트가 선수와 비슷합니다."
        }
      },
      "feedback": {
        "good": [
          {
            "phase": "stride",
            "message": "스트라이드 구간의 전체 움직임이 선수와 비교적 비슷합니다.",
            "evidence": {
              "proFrame": 155.5,
              "userFrame": 104,
              "proPhasePercent": 50,
              "userPhasePercent": 50,
              "differencePercent": 0,
              "difference": 0.21
            }
          }
        ],
        "bad": []
      }
    },
    {
      "analysisId": "analysis_2",
      "proId": "123123214",
      "overallScore": 78,
      "phaseScores": [
        {
          "phase": "leg_lift",
          "label": "레그 리프트",
          "score": 81,
          "userStartFrame": 40,
          "userEndFrame": 92,
          "proStartFrame": 76,
          "proEndFrame": 138
        }
      ],
      "release": {
        "proFrame": 138.5,
        "userFrame": 128.5,
        "pro": {
          "frame": 138.5,
          "beforeFrame": 138,
          "exitFrame": 139,
          "method": "pose_proxy_midpoint_v1",
          "status": "fallback",
          "source": "throwing_wrist_speed_body"
        },
        "user": {
          "frame": 128.5,
          "beforeFrame": 128,
          "exitFrame": 129,
          "method": "ball_exit_midpoint_v1",
          "status": "ready",
          "source": "bright_or_motion_aligned_ball_blob"
        },
        "timing": {
          "proPitchPercent": 86,
          "userPitchPercent": 91,
          "differencePercent": 5,
          "message": "릴리즈 타이밍이 선수와 비슷합니다."
        },
        "point": {
          "difference": 0.24,
          "heightDifference": -0.17,
          "sideDifference": 0.16,
          "message": "릴리즈 포인트가 선수보다 낮게 형성됩니다."
        }
      },
      "feedback": {
        "good": [],
        "bad": []
      }
    },
    {
      "analysisId": "analysis_3",
      "proId": "123123215",
      "overallScore": 71,
      "phaseScores": [
        {
          "phase": "leg_lift",
          "label": "레그 리프트",
          "score": 74,
          "userStartFrame": 40,
          "userEndFrame": 92,
          "proStartFrame": 82,
          "proEndFrame": 150
        }
      ],
      "release": {
        "proFrame": 150.5,
        "userFrame": 128.5,
        "pro": {
          "frame": 150.5,
          "beforeFrame": 150,
          "exitFrame": 151,
          "method": "pose_proxy_midpoint_v1",
          "status": "fallback",
          "source": "throwing_wrist_speed_body"
        },
        "user": {
          "frame": 128.5,
          "beforeFrame": 128,
          "exitFrame": 129,
          "method": "ball_exit_midpoint_v1",
          "status": "ready",
          "source": "bright_or_motion_aligned_ball_blob"
        },
        "timing": {
          "proPitchPercent": 88,
          "userPitchPercent": 91,
          "differencePercent": 3,
          "message": "릴리즈 타이밍이 선수와 비슷합니다."
        },
        "point": {
          "difference": 0.31,
          "heightDifference": -0.24,
          "sideDifference": 0.19,
          "message": "릴리즈 포인트가 선수보다 낮게 형성됩니다."
        }
      },
      "feedback": {
        "good": [],
        "bad": []
      }
    }
  ]
}
```

## 백엔드 DB 저장 권장 필드

- `videoId`
- `user_data.skeleton_data_id`
- `user_data.skeleton_data`
- `user_data.frame_count`
- `user_data.fps`
- `user_data.resolution`
- `players`
- `players[].analysisId`
- `players[].proId`
- `players[].overallScore`
- `players[].phaseScores`
- `players[].release`
- `players[].feedback`

`players`는 전체 프로 skeleton 목록 중 `overallScore` 기준 상위 3개입니다. 각 `players[].phaseScores`에는 fixed-step 리샘플링 기반 phase별 유사도와 사용자/프로 시작-끝 프레임이 들어가므로, 프론트의 phase별 비교 화면과 결과 상세 화면에서 함께 사용할 수 있습니다. `players[].release`는 릴리즈 순간 전용 분석이며, `pro`/`user` 안의 `method`, `status`, `source`로 공 기반 탐지인지 proxy fallback인지 구분합니다. `players[].feedback`은 릴리즈를 제외한 phase 기반 잘한 점/문제점 요약입니다.

프로 skeleton CSV는 백엔드 DB에 이미 저장되어 있고 Python 서버 메모리 캐시에 올라와 있으므로, 응답에 다시 포함하지 않는 것을 기본으로 합니다. 필요하면 디버깅용 옵션으로만 포함합니다.

## 오류 응답

Python 서버는 요청 검증 실패나 서버 내부 오류도 JSON 형태로 반환합니다.

```json
{
  "status": "error",
  "error": {
    "code": "bad_request",
    "message": "프로 skeleton 캐시가 비어 있습니다. 서버 시작 시 백엔드에서 프로 데이터를 받아오도록 설정해 주세요."
  }
}
```

백엔드는 `status === "error"`이면 `error.code`, `error.message`를 사용자에게 보여줄 메시지나 재시도 안내로 변환합니다.

## 프론트 응답용 변환

백엔드는 프론트에 전체 CSV 원문을 그대로 보내기보다 다음 형태로 변환하는 것을 권장합니다.

```json
{
  "videoId": "user_video_001",
  "userSkeletonDataId": "user_skeleton_8f31d2a9",
  "players": [
    {
      "analysisId": "analysis_1",
      "proId": "123123213",
      "overallScore": 82,
      "phaseScores": []
    }
  ],
  "displayKeypoints": {
    "user": [
      {
        "frameIndex": 40,
        "timeSec": 0.667,
        "points": {
          "leftShoulder": { "x": 0.43, "y": 0.31, "confidence": 0.97 },
          "rightShoulder": { "x": 0.56, "y": 0.32, "confidence": 0.96 }
        }
      }
    ],
    "pro": []
  }
}
```

자세한 DB 저장 구조와 프론트 DTO 변환 규칙은 `docs/backend_integration_guide.md`를 기준으로 합니다.

5프레임 skeleton CSV 예시가 포함된 목업 응답은 `docs/service_response_mock.md`를 기준으로 합니다.
