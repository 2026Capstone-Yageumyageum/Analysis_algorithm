# 서비스 연동 인수인계 체크리스트

이 문서는 유사도 알고리즘 v1을 백엔드/프론트 서비스에 붙일 때 각 파트가 확인해야 할 일을 정리합니다.

## 공통 전제

- 촬영 방향은 후면(`rear`)만 지원합니다.
- 원본 영상은 Python 서버와 백엔드 서버에 장기 저장하지 않습니다.
- Python 서버는 요청 처리 중 임시 파일로만 영상을 사용합니다.
- 백엔드는 사용자 `user_data.skeleton_data`, Top 3 `players` 점수 JSON, phase 정보를 저장합니다.
- 프로 skeleton CSV는 백엔드 DB의 reference 데이터로 저장하고, Python 서버 시작/갱신 시 캐시로 전달합니다.
- 프론트는 사용자 기기에 저장된 원본 영상 위에 `displayKeypoints`를 그립니다.

## Python 분석 서버 담당

- `GET /api/schema`를 제공합니다.
- `POST /api/analyze/similarity`를 제공합니다.
- `multipart/form-data`의 `userVideo`, `metadata`를 받습니다.
- 서버 시작 시 `PRO_SKELETON_DATA_URL` 또는 `PRO_SKELETON_DATA_FILE`에서 프로 skeleton reference 목록을 로드합니다.
- `metadata.cameraView`가 비어 있거나 `rear`인 경우만 허용합니다.
- `metadata.user`, `metadata.speed`는 값이 있을 경우 JSON object만 허용합니다.
- 캐시 payload는 JSON array이며, 각 항목은 최소 `proId`, `keypointsCsvText`를 포함해야 합니다.
- 성공 응답에는 `responseSchemaVersion`, `algorithmName`, `scoreScale`, `user_data`, `players`를 포함합니다.
- 오류 응답은 `status: error`, `error.code`, `error.message` 형태로 반환합니다.
- MediaPipe Pose 실검증은 Python 3.11 환경에서 진행합니다.

## 백엔드 담당

- 배포 또는 연동 초기화 시 `GET /api/schema`로 `responseSchemaVersion`, 지원 카메라, keypoints CSV 컬럼을 확인합니다.
- Python 서버가 시작 또는 갱신 시 호출할 프로 skeleton 목록 API를 제공합니다.
- 앱/프론트에서 받은 사용자 영상만 Python 서버 분석 요청으로 전달합니다.
- Python 응답의 `status`가 `completed`이면 분석 결과를 저장합니다.
- Python 응답의 `status`가 `error`이면 `error.code`, `error.message` 기준으로 재시도 안내를 만듭니다.
- `pitch_analysis`에는 schema version, algorithm, score scale, Top 3 `players` 요약을 저장합니다.
- `pitch_user_skeleton`에는 `user_data.skeleton_data_id`, `user_data.skeleton_data`, frame count, fps, resolution을 저장합니다.
- `pitch_analysis_player_match`에는 Top 3 `players[].analysisId`, `proId`, `overallScore`, `phaseScores`를 분리 저장합니다.
- 프론트 조회용 API에서는 CSV 원문을 그대로 내려주지 말고 `displayKeypoints`로 변환해 내려줍니다.
- 변환 규칙은 `docs/backend_integration_guide.md`와 `scripts/keypoints_csv_to_display_keypoints.py`를 기준으로 합니다.

## 프론트 담당

- 사용자가 촬영한 원본 영상은 기기 로컬 또는 앱 정책에 맞는 저장소에서 재생합니다.
- 백엔드 결과 조회 API에서 `players`, 선택된 player의 `phaseScores`, `displayKeypoints`, `videos`를 받습니다.
- skeleton은 원본 영상의 실제 렌더링 영역 기준으로 0~1 좌표를 화면 좌표로 변환해 그립니다.
- `confidence`가 낮은 관절은 흐리게 표시합니다.
- `imputed`가 true인 관절은 점선 또는 다른 색으로 표시할 수 있습니다.
- phase별 비교 화면에서는 user/pro skeleton을 겹치기보다 나란히 보여주는 방식을 우선합니다.

## DB 저장 최소 필드

### `pitch_analysis`

- `video_id`
- `user_id`
- `analysis_type`
- `pitch_type`
- `camera_view`
- `response_schema_version`
- `algorithm_name`
- `score_scale`
- `players_json`
- `top_overall_score`
- `top_pro_id`
- `created_at`

### `pitch_user_skeleton`

- `video_id`
- `skeleton_data_id`
- `keypoints_csv_text`
- `frame_count`
- `fps`
- `resolution`

### `pitch_analysis_player_match`

- `analysis_id`
- `video_id`
- `rank`
- `pro_id`
- `overall_score`
- `phase_scores_json`

## 검증 전 체크

- Python 서버가 Python 3.11 환경에서 실행되는지 확인합니다.
- 사용자 skeleton CSV가 placeholder가 아니라 MediaPipe Pose 기반 실제 관절 좌표로 생성됐는지 확인합니다.
- `responseSchemaVersion`이 `pitch_analysis_response_v1`인지 확인합니다.
- `cameraView`가 `rear`인지 확인합니다.
- `user_data.skeleton_data`에 `frame_index`, `time_sec`, 관절 좌표, confidence 컬럼이 포함되는지 확인합니다.
- `players`가 최대 3개이며 `overallScore` 기준으로 정렬되어 있는지 확인합니다.
- `players[].phaseScores`에 `leg_lift`, `stride`, `release`, `follow_through`가 있는지 확인합니다.
- 구속 계산을 쓰는 경우 `arrivalFrame > releaseFrame`, `fps > 0`, `targetDistanceM - releaseExtensionM > 0` 조건을 만족하는지 확인합니다.

## 참고 문서

- `docs/service_api_contract.md`
- `docs/openapi.yaml`
- `docs/backend_integration_guide.md`
- `docs/frontend_skeleton_rendering.md`
- `docs/keypoints_csv_schema.md`
- `docs/service_response_mock.md`
- `docs/exp08_validation_plan.md`
