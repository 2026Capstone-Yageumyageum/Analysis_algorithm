# exp08 실영상 검증 계획

이 문서는 `exp08_service_api_scaffold`를 실제 기본 영상 쌍으로 검증할 때 사용할 실행 계획입니다.

현재 `/goal` 제약에 따라 테스트/서버 실행은 사용자가 명시적으로 요청하기 전까지 진행하지 않습니다. 따라서 이 문서는 “실행 전 준비된 검증 절차”입니다.

## 검증 목적

서비스 API에 붙일 수 있는 유사도 알고리즘 v1이 실제 영상에서 아래 조건을 만족하는지 확인합니다.

- MediaPipe Pose가 실제 keypoints를 생성하는가
- `user_data.skeleton_data`가 사용자 영상 전체 CSV 원문으로 응답되는가
- 서버 시작 시 캐싱된 프로 skeleton 목록과 비교한 Top 3 `players`가 응답되는가
- 후면 영상 기준 phase detection v1이 납득 가능한 대표 프레임을 잡는가
- phase별 `score`가 계산 가능한 상태로 반환되는가
- pelvis/torso/body-scale 기반 정규화 메타데이터가 응답되는가
- 원본 영상이 장기 저장되지 않는 구조가 유지되는가

## 기본 입력

| 구분 | 경로 |
| --- | --- |
| 사용자 영상 | `/Users/sonjiwoon/capstone/user_data/y1.mp4` |
| 프로 reference | 백엔드 DB 또는 검증 fixture의 `pro_skeleton_data` JSON |
| 서버 루트 | `service/server` |
| 실험 웹 | `service/web` |

## 실행 환경

MediaPipe Pose 기반 검증은 Python 3.11을 기준으로 합니다.

```bash
cd service/server
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
PRO_SKELETON_DATA_FILE=/Users/sonjiwoon/capstone/Analysis_algorithm/outputs/exp08_service_api_validation/pro_skeleton_data.json \
  .venv/bin/python app.py
```

서버 기본 주소:

```text
http://127.0.0.1:5020
```

## API 요청 예시

아래 명령은 실행 허가를 받은 뒤 사용할 예시입니다.

```bash
curl -sS \
  -X POST http://127.0.0.1:5020/api/analyze/similarity \
  -F userVideo=@/Users/sonjiwoon/capstone/user_data/y1.mp4 \
  -F 'metadata={
    "videoId":"y1",
    "analysisType":"pro_similarity",
    "pitchType":"직구",
    "cameraView":"rear",
    "user":{"videoId":"y1"}
  }'
```

## 전체 검증 스크립트

서버가 이미 실행 중이라면 아래 스크립트로 API 호출부터 응답 저장, keypoints CSV 분리, 자동 점검, displayKeypoints 변환까지 한 번에 진행할 수 있습니다.

```bash
bash /Users/sonjiwoon/capstone/Analysis_algorithm/scripts/run_exp08_service_validation.sh
```

환경 변수를 바꾸면 서버 주소나 입력 영상을 교체할 수 있습니다.

```bash
SERVER_URL=http://127.0.0.1:5020 \
USER_VIDEO=/path/to/user.mp4 \
PRO_KEYPOINTS_CSV=/path/to/pro_keypoints.csv \
bash /Users/sonjiwoon/capstone/Analysis_algorithm/scripts/run_exp08_service_validation.sh
```

## 검증 산출물 위치

실제 검증을 실행하면 결과는 아래 폴더에 저장합니다.

```text
/Users/sonjiwoon/capstone/Analysis_algorithm/outputs/exp08_service_api_validation/
```

권장 파일 구성:

```text
exp08_service_api_validation/
  exp08_response.json
  exp08_validation_stdout.txt
  exp08_validation_strict_stdout.txt
  keypoints_user.csv
  pro_skeleton_data.json
  display_keypoints_user.json
  notes.md
```

`exp08_response.json`에는 Python 서버의 전체 응답 JSON을 저장합니다. `keypoints_user.csv`는 응답의 `user_data.skeleton_data`를 분리 저장한 검토용 파일이며, `pro_skeleton_data.json`은 서버 캐시에 넣기 위해 준비한 프로 skeleton reference 목록입니다. 원본 영상은 저장하지 않습니다.

## 확인할 응답 필드

| 필드 | 기대값 |
| --- | --- |
| `status` | `completed` |
| `cameraView` | `rear` |
| `algorithmName` | `body_frame_phase_direction_vector_v1` |
| `user_data.skeleton_data` | `frame_index,time_sec,...`로 시작하는 CSV 문자열 |
| `user_data.frame_count` | 사용자 영상 프레임 수 |
| `user_data.fps` | 사용자 영상 FPS |
| `user_data.resolution` | 예: `1920x1080` |
| `players` | 최대 3개 |
| `players[].rank` | 1~3 |
| `players[].proId` | 캐시의 `pro_skeleton_data[].proId`와 매칭 |
| `players[].overallScore` | 0~100 숫자 |
| `players[].phaseScores[].score` | 0~100 숫자 |
| `players[].phaseScores[].userStartFrame` | 사용자 phase 시작 프레임 |
| `players[].phaseScores[].userEndFrame` | 사용자 phase 끝 프레임 |
| `players[].phaseScores[].proStartFrame` | 프로 phase 시작 프레임 |
| `players[].phaseScores[].proEndFrame` | 프로 phase 끝 프레임 |

## 응답 JSON 자동 점검

응답 JSON을 파일로 저장한 뒤 아래 참조 스크립트로 계약을 점검합니다. 이 명령은 사용자 허가 후 실제 검증 단계에서만 실행합니다.

```bash
python /Users/sonjiwoon/capstone/Analysis_algorithm/scripts/validate_pitch_analysis_response.py \
  /Users/sonjiwoon/capstone/Analysis_algorithm/outputs/exp08_service_api_validation/exp08_response.json
```

엄격 모드에서는 `players`가 비어 있거나 `players[].phaseScores`가 계산되지 않으면 실패로 처리합니다.

```bash
python /Users/sonjiwoon/capstone/Analysis_algorithm/scripts/validate_pitch_analysis_response.py \
  /Users/sonjiwoon/capstone/Analysis_algorithm/outputs/exp08_service_api_validation/exp08_response.json \
  --strict
```

프론트 표시용 변환 참조도 같은 폴더에 저장합니다.

```bash
python /Users/sonjiwoon/capstone/Analysis_algorithm/scripts/keypoints_csv_to_display_keypoints.py \
  --csv /Users/sonjiwoon/capstone/Analysis_algorithm/outputs/exp08_service_api_validation/keypoints_user.csv \
  --phase-json /Users/sonjiwoon/capstone/Analysis_algorithm/outputs/exp08_service_api_validation/exp08_response.json \
  --target user \
  --output /Users/sonjiwoon/capstone/Analysis_algorithm/outputs/exp08_service_api_validation/display_keypoints_user.json
```

## 합격 기준

아래 조건을 모두 만족하면 exp08은 “서비스 API 연동 가능한 v1 후보”로 통과 처리합니다.

- `user_data.skeleton_data`가 비어 있지 않고, `docs/keypoints_csv_schema.md`의 필수 컬럼을 포함합니다.
- `players`가 최대 3개이며 `rank` 순서대로 정렬됩니다.
- `players[].overallScore`가 0~100 범위 숫자입니다.
- `players[].phaseScores`에 `leg_lift`, `stride`, `release`, `follow_through`가 모두 존재합니다.
- 각 phase에 사용자/프로 시작-끝 프레임이 존재합니다.
- 서버 실행 후 결과 폴더나 업로드 영상 파일이 장기 저장되지 않습니다.

## 실패 또는 보류 기준

아래 조건 중 하나라도 발생하면 exp08은 보류하고 원인을 기록합니다.

- MediaPipe가 설치되지 않아 사용자 skeleton이 placeholder로 생성됩니다.
- `players[].phaseScores`가 대부분 계산 불가 상태입니다.
- 릴리즈 구간이 너무 짧아 점수가 한 프레임 노이즈에 민감합니다.
- `user_data.skeleton_data`가 너무 커서 백엔드 저장 정책 재검토가 필요합니다.
- phase 대표 프레임이 사람이 보기에도 명백히 다른 동작 구간을 가리킵니다.

## 기록 방식

검증 후 아래 파일을 갱신합니다.

- `Analysis_algorithm/experiments/exp08_service_api_scaffold/validation_notes_template.md`를 복사한 `Analysis_algorithm/outputs/exp08_service_api_validation/notes.md`
- `Analysis_algorithm/experiments/exp08_service_api_scaffold/README.md`
- `Analysis_algorithm/results/summary.csv`
- `Analysis_algorithm/docs/goal_status.md`
- 필요하면 `Analysis_algorithm/idea.md`

기록은 한국어로 작성합니다.

## 검증 후 판단

검증 결과가 통과이면 goal 완료 후보가 됩니다.

검증 결과가 보류이면 다음 실험으로 넘어갑니다.

- phase 내부 리샘플링 기반 A 실험
- release window 재정의
- confidence threshold 조정
- `displayKeypoints` 백엔드 변환 구현
