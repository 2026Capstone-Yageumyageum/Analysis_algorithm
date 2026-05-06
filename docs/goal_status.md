# 유사도 알고리즘 v1 고도화 진행 상태

이 문서는 `/goal`로 설정한 “유사도 알고리즘 v1을 서비스 API에 붙일 수 있는 수준으로 고도화” 작업의 현재 상태를 추적합니다.

## 완료 기준 요약

- exp01~exp07 실험 기록 정리
- 사용자 skeleton CSV 응답 스키마 확정
- 후면 영상 기준 phase detection 고도화
- pelvis/torso/body-scale 기반 2D 공간 정규화 반영
- phase별 feature와 관절 목록 확정
- phase별 점수 및 `overallScore` 계산식 구현
- 백엔드 저장용 Python 서버 응답 JSON 확정
- 프론트 skeleton 표시용 데이터 구조 정리
- 한국어 실험 기록 유지
- 원본 영상 미저장 구조 유지
- 서버 응답에 사용자 `user_data.skeleton_data`와 `user_data.keypointsCsvText` 포함
- 요청 전까지 테스트 실행하지 않기

## 요구사항별 증거

| 요구사항 | 현재 증거 | 상태 |
| --- | --- | --- |
| exp01~exp07 실험 기록 정리 | `Analysis_algorithm/experiments/exp01_*` ~ `exp07_phase_direction`, `docs/experiment_history.md`, `results/summary.csv` | 완료 |
| `idea.md` 생성 및 아이디어 기록 | `Analysis_algorithm/idea.md` | 완료 |
| 사용자 skeleton CSV 스키마 확정 | `docs/keypoints_csv_schema.md` | 완료 |
| 백엔드 저장용 응답 JSON 확정 | `docs/service_api_contract.md`, `docs/service_response_mock.md`, `service/server/app.py` | 1차 완료 |
| 서비스 API OpenAPI 초안 | `docs/openapi.yaml` | 주요 엔드포인트와 응답 스키마 문서화 완료 |
| 서비스 스키마 메타 엔드포인트 | `service/server/app.py`, `docs/openapi.yaml`, `docs/service_api_contract.md` | `/api/schema`로 스키마 버전, 지원 카메라, 알고리즘, keypoints CSV 컬럼 확인 가능 |
| 서비스 연동 인수인계 체크리스트 | `docs/service_handoff_checklist.md` | Python/백엔드/프론트 담당 작업과 저장 필드 체크리스트 정리 |
| 서비스 응답 검증 스크립트 | `scripts/validate_pitch_analysis_response.py`, `docs/exp08_validation_plan.md` | exp08 응답 JSON의 필수 필드와 keypoints CSV 컬럼을 점검하는 참조 구현 추가 |
| exp08 검증 실행 스크립트 | `scripts/run_exp08_service_validation.sh`, `docs/exp08_validation_plan.md` | 허가 후 API 호출부터 응답 저장, CSV 분리, 검증, displayKeypoints 변환까지 실행하는 절차 준비 |
| 프론트 skeleton 표시용 구조 정리 | `docs/frontend_skeleton_rendering.md`, `docs/backend_integration_guide.md`, `scripts/keypoints_csv_to_display_keypoints.py` | 완료. 0~1 기준 좌표, 프레임 밖 좌표 처리, `confidence`, `imputed` 해석까지 문서화 |
| phase별 feature와 관절 목록 확정 | `docs/scoring_policy.md`, `service/server/analysis/similarity.py` | 1차 완료 |
| phase별 점수 및 `overallScore` 계산식 구현 | `service/server/analysis/similarity.py` | confidence 가중 평균까지 1차 완료 |
| 후면 영상 기준 phase detection 고도화 | `service/server/analysis/phase.py` | 최소 길이 fallback 보정까지 구현. exp08 strict 검증 통과 |
| pelvis/torso/body-scale 기반 2D 정규화 반영 | `service/server/analysis/normalization.py`, `docs/scoring_policy.md`, `service/server/app.py` | 구현 완료. 응답 JSON 진단 메타 포함 |
| 원본 영상 미저장 구조 유지 | `service/server/app.py`의 `TemporaryDirectory` 사용, `docs/service_api_contract.md` | 구현 완료 |
| 서버 응답에 사용자 skeleton CSV 포함 | `service/server/app.py`, `docs/service_api_contract.md`, `docs/service_response_mock.md` | `user_data.skeleton_data`와 `user_data.keypointsCsvText` 호환 alias 모두 반영 완료 |
| 실험 결과를 한국어로 기록 | `experiments/`, `docs/`, `idea.md`, `results/summary.csv` | 완료 |
| 테스트 실행 금지 | 사용자 요청 전까지 미실행. 사용자 승인 후 exp08 실영상 검증 실행 | 준수 |
| exp08 검증 계획 | `docs/exp08_validation_plan.md` | 실행 전 절차와 합격/보류 기준 정리 완료 |
| exp08 검증 산출물 규칙 | `docs/exp08_validation_plan.md`, `experiments/README.md` | 응답 JSON, keypoints CSV, displayKeypoints JSON 저장 위치와 파일명 규칙 정리 |
| exp08 검증 노트 | `experiments/exp08_service_api_scaffold/validation_notes_template.md`, `outputs/exp08_service_api_validation/notes.md` | 실영상 검증 결과를 한국어로 기록. API 기본 계약과 strict 검증 통과 |

## 프롬프트 요구사항별 산출물 감사

아래 표는 `/goal` 프롬프트의 명시 요구사항을 실제 파일과 연결한 감사표입니다.

| 프롬프트 요구사항 | 산출물/증거 | 감사 결과 |
| --- | --- | --- |
| 유사도 알고리즘 v1을 서비스 API에 붙일 수 있는 수준으로 고도화 | `service/server/app.py`, `service/server/analysis/*.py`, `docs/service_api_contract.md` | Flask API 엔드포인트와 유사도 계산 모듈이 연결되어 있음 |
| 고도화 아이디어를 `idea.md`에 계속 기록 | `Analysis_algorithm/idea.md` | phase detection, 분석/표시 좌표 분리, confidence 가중치 등 기록됨 |
| exp01~exp07 실험 기록 정리 | `experiments/exp01_pose_model` ~ `experiments/exp07_phase_direction`, `docs/experiment_history.md`, `results/summary.csv` | 각 실험 목적, 방법, 관찰, 문제점, 결정이 한국어로 정리됨 |
| 포즈 모델은 MediaPipe 기준 | `experiments/exp01_pose_model/README.md`, `docs/current_decision.md`, `service/server/analysis/pose.py` | MediaPipe Pose 사용 기준과 선택 이유가 문서화됨 |
| 사용자/프로 영상은 후면 기준 비교 | `docs/service_api_contract.md`, `service/server/app.py` | `cameraView`가 `rear`로 고정되어 응답됨 |
| 후면 촬영 API 입력 강제 | `service/server/app.py`, `docs/service_api_contract.md`, `docs/openapi.yaml` | `metadata.cameraView`가 `rear`가 아니면 요청을 거부하도록 정리됨 |
| 원본 영상은 서버에 저장하지 않음 | `service/server/app.py` | `TemporaryDirectory` 안에서만 업로드 영상을 처리함 |
| 사용자 skeleton CSV와 Top 3 점수 결과만 백엔드 DB 저장 방향 | `docs/keypoints_csv_schema.md`, `docs/backend_integration_guide.md`, `docs/service_api_contract.md` | DB 저장 권장 구조와 CSV 원문 저장 정책 문서화됨 |
| `service/server`, `service/web` 스캐폴드 활용 | `service/server/`, `service/web/` | 서버와 실험용 웹 파일 존재 |
| 서비스 API 응답과 스키마를 로컬 웹에서 확인 가능 | `service/web/templates/index.html`, `service/web/static/app.js`, `service/web/static/styles.css` | `/api/schema` 계약 확인, 전체 점수, 알고리즘명, keypoints CSV 크기, phase별 점수, 포즈 상태를 화면에 요약 표시 |
| 현재 유사도는 phase별 시작-끝 방향 벡터 기반 | `service/server/analysis/similarity.py`, `docs/scoring_policy.md` | body-frame 시작-끝 방향 벡터 코사인 점수로 구현됨 |
| 구속 측정은 실제 거리, 릴리즈 프레임, 도착 프레임 기반 TOF 방식 | `service/server/analysis/speed.py`, `docs/service_api_contract.md` | `releaseFrame`, `arrivalFrame`, 거리 기반 계산식 구현 및 `arrivalFrame > releaseFrame`, `fps > 0`, 유효 거리 조건 문서화됨 |
| 영상 메타데이터 숫자 방어 | `service/server/analysis/video.py`, `service/server/analysis/pose.py`, `service/server/analysis/speed.py`, `docs/backend_integration_guide.md` | OpenCV fps/frame metadata가 `NaN/inf`일 때 응답에 비정상 숫자가 섞이지 않도록 finite/positive 값으로 정리 |
| keypoints 숫자 방어 | `service/server/analysis/pose.py`, `docs/keypoints_csv_schema.md` | MediaPipe 좌표와 confidence가 `NaN/inf`일 때 CSV와 smoothing 좌표에 비정상 숫자가 전파되지 않도록 정리 |
| 사용자/pro skeleton CSV 컬럼 스키마 확정 | `docs/keypoints_csv_schema.md`, `service/server/analysis/pose.py` | 실제 CSV 컬럼 생성 함수와 문서 스키마가 대응함 |
| 후면 영상 기준 phase detection 고도화 | `service/server/analysis/phase.py`, `docs/scoring_policy.md` | keypoints 기반 v1 휴리스틱과 최소 길이 fallback 구현. exp08 strict 검증 통과 |
| pelvis/torso/body-scale 기반 2D 공간 정규화 반영 | `service/server/analysis/normalization.py`, `docs/scoring_policy.md`, `service/server/app.py` | 분석용 body-frame 좌표 생성 구현, 문서화, 응답 진단 메타 포함 |
| phase별 비교 feature와 관절 목록 확정 | `service/server/analysis/similarity.py`, `docs/scoring_policy.md` | phase별 관절 후보와 가중치가 구현/문서화됨 |
| phase별 유사도 점수 계산식 구현 | `service/server/analysis/similarity.py` | 코사인 유사도 0~100 변환과 confidence 가중 평균 적용 |
| `overallScore` 계산식 구현 | `service/server/analysis/similarity.py`, `docs/scoring_policy.md` | 유효 phase 가중 평균으로 계산됨 |
| 백엔드 서버가 저장할 Python 서버 응답 JSON 확정 | `docs/service_api_contract.md`, `docs/openapi.yaml`, `docs/service_response_mock.md`, `docs/backend_integration_guide.md` | 서버 시작/갱신 시 프로 skeleton cache를 구성하고, 분석 요청은 `userVideo` + `metadata`만 받는 구조로 정리됨. 응답에는 `user_data.skeleton_data`, Top 3 `players` 결과, DB 권장 필드, 5프레임 CSV 목업이 포함됨 |
| 서비스 API 오류 응답 JSON 확정 | `service/server/app.py`, `docs/service_api_contract.md`, `docs/backend_integration_guide.md`, `service/web/static/app.js` | 요청 검증 실패와 서버 오류를 `status:error` 형태로 반환하고 웹에서 메시지를 표시 |
| metadata 타입 검증 보강 | `service/server/app.py`, `docs/service_api_contract.md`, `docs/openapi.yaml`, `service/server/README.md` | `metadata.user/pro/speed`가 object가 아니면 500 대신 `400 bad_request`로 처리하도록 정리 |
| 프론트가 원본 영상 위에 skeleton을 그릴 수 있는 표시용 데이터 구조 정리 | `docs/frontend_skeleton_rendering.md`, `docs/backend_integration_guide.md`, `scripts/keypoints_csv_to_display_keypoints.py` | CSV `_smooth` 좌표를 `displayKeypoints`로 변환하는 규칙, 프레임 밖 좌표 처리, `confidence`/`imputed` 표시 규칙과 참조 구현 정리됨 |
| 실험 결과를 `summary.csv`와 각 exp 문서에 한국어로 기록 | `results/summary.csv`, `experiments/exp08_service_api_scaffold/README.md` | exp08 실영상 검증 결과를 조건부 통과로 기록 |
| 코드 변경 전 변경 파일 설명 | 작업 로그 기준으로 변경 전 대상 파일을 설명한 뒤 patch 적용 | 준수 |
| 테스트 실행은 요청 전까지 하지 않음 | 사용자 요청 이후 exp08 실영상 검증 실행 | 준수 |

## 번호별 목표 감사

초기 `/goal`에 포함된 1~10번 목표를 별도로 분리해 추적합니다.

| 번호 | 목표 | 현재 증거 | 판정 |
| --- | --- | --- | --- |
| 1 | exp01~exp07 실험 기록 정리 | `experiments/exp01_pose_model` ~ `experiments/exp07_phase_direction`, `docs/experiment_history.md`, `results/summary.csv` | 완료. `exp07`은 기존 실행 산출물 경로 `outputs/exp6`와 실험 정리 번호를 문서에서 분리 설명 |
| 2 | 사용자 skeleton CSV 응답 스키마 확정 | `docs/keypoints_csv_schema.md`, `service/server/analysis/pose.py`, `GET /api/schema`의 `keypointsCsvColumns` | 1차 완료 |
| 3 | 후면 영상 기준 phase detection을 keypoints 기반으로 고도화 | `service/server/analysis/phase.py`, `docs/scoring_policy.md` | 최소 길이 fallback 보정까지 구현. exp08 strict 검증 통과 |
| 4 | pelvis/torso/body-scale 기반 2D 공간 정규화를 유사도 계산에 반영 | `service/server/analysis/normalization.py`, `service/server/analysis/similarity.py`, `service/server/app.py` | 구현 및 응답 JSON 진단 메타 포함 완료 |
| 5 | phase별 비교 feature와 관절 목록 확정 | `docs/scoring_policy.md`, `service/server/analysis/similarity.py` | 1차 완료 |
| 6 | phase별 유사도 점수 계산식 정리 및 구현 | `docs/scoring_policy.md`, `service/server/analysis/similarity.py` | confidence 가중 평균까지 구현 완료 |
| 7 | `overallScore` 계산식 정리 및 구현 | `docs/scoring_policy.md`, `service/server/analysis/similarity.py` | 유효 phase 가중 평균으로 구현 완료 |
| 8 | 백엔드 서버가 저장할 Python 서버 응답 JSON 확정 | `docs/service_api_contract.md`, `docs/openapi.yaml`, `docs/backend_integration_guide.md`, `docs/service_response_mock.md`, `service/server/app.py` | 1차 완료 |
| 9 | 프론트가 원본 영상 위에 skeleton을 그릴 수 있도록 표시용 데이터 구조 정리 | `docs/frontend_skeleton_rendering.md`, `docs/backend_integration_guide.md`, `scripts/keypoints_csv_to_display_keypoints.py` | 완료. 실제 앱 구현은 프론트/백엔드 레포에서 진행 필요 |
| 10 | 실험 결과를 `summary.csv`와 각 exp 문서에 한국어로 기록 | `results/summary.csv`, `experiments/`, `docs/experiment_history.md`, `experiments/exp08_service_api_scaffold/README.md` | exp08 실영상 strict 검증 통과 결과까지 기록 완료 |

현재 목표는 “서비스 API에 붙일 수 있는 유사도 알고리즘 v1 후보” 수준까지 충족했습니다. 다만 fallback 보정이 들어간 phase 경계는 시각 검토와 reference 확장이 필요하므로 최종 알고리즘 확정은 다음 실험으로 넘깁니다.

## exp08 실영상 검증 결과

- 검증 입력: `/Users/sonjiwoon/capstone/user_data/y1.mp4`
- 프로 reference: `/Users/sonjiwoon/capstone/Analysis_algorithm/outputs/exp08_service_api_validation/pro_skeleton_data.json`
- 응답 저장: `/Users/sonjiwoon/capstone/Analysis_algorithm/outputs/exp08_service_api_validation/exp08_response.json`
- 기본 계약 검증: 통과
- 엄격 검증: 통과
- 사용자 skeleton CSV: 446프레임, 약 348KB, 60.025fps, 1080x1920
- Top 1 결과: 류현진 reference, `overallScore` 58.54
- phase 결과: `leg_lift` 71.77, `stride` 60.44, `release` 29.35, `follow_through` 91.05
- 주요 보정: 프로 `stride/release`와 사용자 `follow_through`에 최소 길이 fallback 적용
- 판정: 서비스 API v1 후보로 조건부 통과

## 실행 환경 메모

- MediaPipe Pose 기반 실험 검증은 Python 3.11 환경을 기준으로 진행합니다.
- `service/server/requirements.txt`는 Python 3.13 이상에서 MediaPipe 설치를 건너뛰도록 되어 있습니다.
- Python 3.13 이상으로 서버를 실행하면 실제 포즈 추정 대신 fallback keypoints가 사용될 수 있으므로, 해당 결과는 유사도 품질 판단에 사용하지 않습니다.

## 후속 개선 후보

현재 목표인 “서비스 API에 붙일 수 있는 유사도 알고리즘 v1 후보”는 충족했습니다. 아래 항목은 최종 알고리즘 품질을 높이기 위한 다음 실험 후보입니다.

- 실제 `user_data/y1.mp4`와 프로 skeleton reference 목록으로 Top 1 비교 결과는 확인했지만, 프로 reference가 1개뿐이라 Top 3 정렬 검증은 아직 제한적입니다.
- `players[].phaseScores`는 모두 계산 가능 상태가 되었지만, fallback 보정된 구간은 시각 검토가 필요합니다.
- `user_data.skeleton_data`가 실제 응답에서 백엔드 저장 가능한 형식으로 반환되는 것은 확인했지만, 장기 DB 저장 크기 정책은 별도 검토가 필요합니다.
- 프론트 표시용 JSON 변환은 DTO와 변환 규칙까지 문서화되어 있지만, 실제 백엔드 변환 코드는 백엔드 레포에서 구현해야 합니다.
- confidence 기반 phase 점수 가중 평균은 적용했지만 실영상 점수 분포 검증은 아직 하지 않았습니다.

## 다음 작업

다음 코드 개선 후보를 먼저 진행합니다.

- fallback 보정이 들어간 phase 경계 시각 검토
- 프로 reference 3개 이상으로 Top 3 정렬 검증
- phase 내부 리샘플링 기반 A 실험 설계
