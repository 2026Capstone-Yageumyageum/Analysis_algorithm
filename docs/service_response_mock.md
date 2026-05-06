# 서비스 응답 목업 데이터

이 문서는 백엔드/프론트 팀원이 Python 유사도 서버 응답을 저장하거나 화면 표시 구조로 바꿀 때 참고할 수 있는 목업입니다.

실제 서버 응답은 JSON이며, `user_data.skeleton_data`에는 사용자 영상에서 추출한 CSV 원문 문자열이 들어갑니다. 프로 선수 skeleton CSV는 Python 서버 시작/갱신 시 백엔드 DB에서 받아와 메모리에 캐싱하며, 분석 요청 응답에는 다시 포함하지 않는 것을 기본으로 합니다.

아래 CSV는 읽기 쉬운 5프레임 축약 예시입니다. 실제 전체 컬럼은 `docs/keypoints_csv_schema.md`를 기준으로 합니다.

## 요청 metadata 예시

```json
{
  "videoId": "user_video_001",
  "analysisType": "pro_similarity",
  "pitchType": "직구",
  "cameraView": "rear",
  "user": {
    "videoId": "user_y1_local"
  },
  "speed": {
    "user": {
      "releaseFrame": 120,
      "arrivalFrame": 148,
      "targetDistanceM": 16.0,
      "releaseExtensionM": 1.5,
      "fps": 60.0
    }
  }
}
```

## Python 서버가 캐싱하는 `pro_skeleton_data` 예시

```json
[
  {
    "proId": "123123213",
    "playerName": "류현진",
    "skeletonDataId": "pro_skeleton_ryu_001",
    "keypointsCsvText": "frame_index,time_sec,nose_x,nose_y,...\n0,0.000,0.51,0.18,...",
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
  },
  {
    "proId": "123123215",
    "playerName": "프로 선수 3",
    "skeletonDataId": "pro_skeleton_003",
    "keypointsCsvText": "frame_index,time_sec,nose_x,nose_y,...",
    "frameCount": 198,
    "fps": 30.0,
    "resolution": "1280x720"
  }
]
```

## Python 서버 응답 예시

```json
{
  "videoId": "user_video_001",
  "status": "completed",
  "responseSchemaVersion": "pitch_analysis_response_v1",
  "analysisType": "pro_similarity",
  "pitchType": "직구",
  "cameraView": "rear",
  "processedAt": "2026-05-05T15:30:00+09:00",
  "algorithmName": "body_frame_phase_direction_vector_v1",
  "scoreScale": "0~100",
  "user_data": {
    "skeleton_data_id": "user_skeleton_8f31d2a9",
    "skeleton_data": "아래 user CSV 예시 문자열",
    "keypointsCsvText": "아래 user CSV 예시 문자열",
    "frame_count": 240,
    "fps": 60.0,
    "resolution": "1080x1920"
  },
  "players": [
    {
      "rank": 1,
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
        },
        {
          "phase": "stride",
          "label": "스트라이드",
          "score": 79,
          "userStartFrame": 92,
          "userEndFrame": 116,
          "proStartFrame": 145,
          "proEndFrame": 166
        },
        {
          "phase": "release",
          "label": "릴리즈",
          "score": 81,
          "userStartFrame": 116,
          "userEndFrame": 128,
          "proStartFrame": 166,
          "proEndFrame": 176
        },
        {
          "phase": "follow_through",
          "label": "팔로우 스루",
          "score": 84,
          "userStartFrame": 128,
          "userEndFrame": 180,
          "proStartFrame": 176,
          "proEndFrame": 210
        }
      ],
      "phaseDetection": {
        "user": {
          "representativeFrames": {
            "setup": 0,
            "leg_lift": 40,
            "stride": 92,
            "release": 128,
            "follow_through": 180
          },
          "warnings": []
        },
        "pro": {
          "representativeFrames": {
            "setup": 0,
            "leg_lift": 80,
            "stride": 145,
            "release": 176,
            "follow_through": 210
          },
          "warnings": []
        }
      },
      "normalization": {
        "user": {
          "status": "ready",
          "method": "pelvis_torso_body_scale_2d_v1",
          "throwingSide": "right",
          "mirrorApplied": false
        },
        "pro": {
          "status": "ready",
          "method": "pelvis_torso_body_scale_2d_v1",
          "throwingSide": "left",
          "mirrorApplied": true
        }
      }
    },
    {
      "rank": 2,
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
      ]
    },
    {
      "rank": 3,
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
      ]
    }
  ]
}
```

`players`는 `overallScore` 기준 상위 3개만 반환합니다. 각 `players[].phaseScores`는 phase별 유사도 점수와 사용자/프로 시작-끝 프레임을 포함합니다. `players[].phaseDetection`과 `players[].normalization`은 phase 경계와 정규화 상태를 확인하기 위한 진단 메타입니다. 프로 skeleton CSV 원문은 Python 서버가 시작/갱신 시 캐싱한 reference 데이터에 있으므로 응답에는 중복 포함하지 않습니다.

## `user_data.skeleton_data` 5프레임 축약 예시

```csv
frame_index,time_sec,left_shoulder_x,left_shoulder_y,left_shoulder_confidence,right_shoulder_x,right_shoulder_y,right_shoulder_confidence,left_hip_x,left_hip_y,left_hip_confidence,right_hip_x,right_hip_y,right_hip_confidence,left_wrist_x,left_wrist_y,left_wrist_confidence,right_wrist_x,right_wrist_y,right_wrist_confidence,left_knee_x,left_knee_y,left_knee_confidence,right_knee_x,right_knee_y,right_knee_confidence,left_foot_index_x,left_foot_index_y,left_foot_index_confidence,right_foot_index_x,right_foot_index_y,right_foot_index_confidence,left_shoulder_x_smooth,left_shoulder_y_smooth,right_shoulder_x_smooth,right_shoulder_y_smooth,left_hip_x_smooth,left_hip_y_smooth,right_hip_x_smooth,right_hip_y_smooth,left_wrist_x_smooth,left_wrist_y_smooth,right_wrist_x_smooth,right_wrist_y_smooth,pitcher_com_x_smooth,pitcher_com_y_smooth,pitcher_detected,normalised_frame,no_missing_frames_flag,smooth_com_flag
0,0.000000,0.430,0.320,0.97,0.570,0.321,0.97,0.451,0.552,0.98,0.551,0.553,0.98,0.352,0.579,0.93,0.651,0.580,0.93,0.432,0.721,0.96,0.572,0.722,0.96,0.410,0.932,0.94,0.590,0.933,0.94,0.430,0.320,0.570,0.321,0.451,0.552,0.551,0.553,0.352,0.579,0.651,0.580,0.501,0.436,true,0,true,true
1,0.016667,0.431,0.321,0.97,0.571,0.322,0.97,0.452,0.553,0.98,0.552,0.554,0.98,0.353,0.578,0.93,0.652,0.579,0.93,0.433,0.720,0.96,0.573,0.721,0.96,0.411,0.931,0.94,0.591,0.932,0.94,0.431,0.321,0.571,0.322,0.452,0.553,0.552,0.554,0.353,0.578,0.652,0.579,0.502,0.438,true,1,true,true
2,0.033333,0.432,0.322,0.97,0.572,0.323,0.97,0.453,0.554,0.98,0.553,0.555,0.98,0.354,0.577,0.93,0.653,0.578,0.93,0.434,0.719,0.96,0.574,0.720,0.96,0.412,0.930,0.94,0.592,0.931,0.94,0.432,0.322,0.572,0.323,0.453,0.554,0.553,0.555,0.354,0.577,0.653,0.578,0.503,0.439,true,2,true,true
3,0.050000,0.433,0.323,0.97,0.573,0.324,0.97,0.454,0.555,0.98,0.554,0.556,0.98,0.355,0.576,0.93,0.654,0.577,0.93,0.435,0.718,0.96,0.575,0.719,0.96,0.413,0.929,0.94,0.593,0.930,0.94,0.433,0.323,0.573,0.324,0.454,0.555,0.554,0.556,0.355,0.576,0.654,0.577,0.504,0.440,true,3,true,true
4,0.066667,0.434,0.324,0.97,0.574,0.325,0.97,0.455,0.556,0.98,0.555,0.557,0.98,0.356,0.575,0.93,0.655,0.576,0.93,0.436,0.717,0.96,0.576,0.718,0.96,0.414,0.928,0.94,0.594,0.929,0.94,0.434,0.324,0.574,0.325,0.455,0.556,0.555,0.557,0.356,0.575,0.655,0.576,0.505,0.441,true,4,true,true
```

## 캐시 `pro_skeleton_data[].keypointsCsvText` 5프레임 축약 예시

아래 예시는 응답에 포함되는 값이 아니라, 백엔드가 Python 서버의 프로 skeleton cache API 또는 cache source에 제공하는 프로 skeleton CSV 형식 예시입니다.

```csv
frame_index,time_sec,left_shoulder_x,left_shoulder_y,left_shoulder_confidence,right_shoulder_x,right_shoulder_y,right_shoulder_confidence,left_hip_x,left_hip_y,left_hip_confidence,right_hip_x,right_hip_y,right_hip_confidence,left_wrist_x,left_wrist_y,left_wrist_confidence,right_wrist_x,right_wrist_y,right_wrist_confidence,left_knee_x,left_knee_y,left_knee_confidence,right_knee_x,right_knee_y,right_knee_confidence,left_foot_index_x,left_foot_index_y,left_foot_index_confidence,right_foot_index_x,right_foot_index_y,right_foot_index_confidence,left_shoulder_x_smooth,left_shoulder_y_smooth,right_shoulder_x_smooth,right_shoulder_y_smooth,left_hip_x_smooth,left_hip_y_smooth,right_hip_x_smooth,right_hip_y_smooth,left_wrist_x_smooth,left_wrist_y_smooth,right_wrist_x_smooth,right_wrist_y_smooth,pitcher_com_x_smooth,pitcher_com_y_smooth,pitcher_detected,normalised_frame,no_missing_frames_flag,smooth_com_flag
0,0.000000,0.427,0.318,0.96,0.566,0.319,0.96,0.448,0.548,0.97,0.548,0.549,0.97,0.344,0.586,0.91,0.644,0.587,0.91,0.428,0.716,0.95,0.568,0.717,0.95,0.407,0.927,0.93,0.587,0.928,0.93,0.427,0.318,0.566,0.319,0.448,0.548,0.548,0.549,0.344,0.586,0.644,0.587,0.497,0.434,true,0,true,true
1,0.033333,0.426,0.319,0.96,0.565,0.320,0.96,0.447,0.549,0.97,0.547,0.550,0.97,0.343,0.587,0.91,0.643,0.588,0.91,0.427,0.715,0.95,0.567,0.716,0.95,0.406,0.926,0.93,0.586,0.927,0.93,0.426,0.319,0.565,0.320,0.447,0.549,0.547,0.550,0.343,0.587,0.643,0.588,0.496,0.435,true,1,true,true
2,0.066667,0.425,0.320,0.96,0.564,0.321,0.96,0.446,0.550,0.97,0.546,0.551,0.97,0.342,0.588,0.91,0.642,0.589,0.91,0.426,0.714,0.95,0.566,0.715,0.95,0.405,0.925,0.93,0.585,0.926,0.93,0.425,0.320,0.564,0.321,0.446,0.550,0.546,0.551,0.342,0.588,0.642,0.589,0.495,0.436,true,2,true,true
3,0.100000,0.424,0.321,0.96,0.563,0.322,0.96,0.445,0.551,0.97,0.545,0.552,0.97,0.341,0.589,0.91,0.641,0.590,0.91,0.425,0.713,0.95,0.565,0.714,0.95,0.404,0.924,0.93,0.584,0.925,0.93,0.424,0.321,0.563,0.322,0.445,0.551,0.545,0.552,0.341,0.589,0.641,0.590,0.494,0.437,true,3,true,true
4,0.133333,0.423,0.322,0.96,0.562,0.323,0.96,0.444,0.552,0.97,0.544,0.553,0.97,0.340,0.590,0.91,0.640,0.591,0.91,0.424,0.712,0.95,0.564,0.713,0.95,0.403,0.923,0.93,0.583,0.924,0.93,0.423,0.322,0.562,0.323,0.444,0.552,0.544,0.553,0.340,0.590,0.640,0.591,0.493,0.438,true,4,true,true
```

## 프론트 표시용 변환 예시

백엔드가 CSV 한 행을 파싱하면 프론트에는 아래처럼 내려줄 수 있습니다.

```json
{
  "frameIndex": 0,
  "timeSec": 0.0,
  "phase": "leg_lift",
  "points": {
    "leftShoulder": {
      "x": 0.43,
      "y": 0.32,
      "confidence": 0.97,
      "imputed": false
    },
    "rightShoulder": {
      "x": 0.57,
      "y": 0.321,
      "confidence": 0.97,
      "imputed": false
    }
  }
}
```

프론트 표시는 원본 0~1 smooth 좌표를 쓰고, 유사도 점수 계산은 Python 서버 내부의 body-frame 좌표를 씁니다.
