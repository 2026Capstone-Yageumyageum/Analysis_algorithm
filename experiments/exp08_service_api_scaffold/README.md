# exp08_service_api_scaffold

## 실험 이름

서비스 API 연동용 유사도 알고리즘 v1 스캐폴드

## 목적

exp01~exp07에서 정리한 MediaPipe 2D 관절 좌표, pelvis/torso/body-scale 정규화, phase별 방향 벡터 점수 후보를 백엔드 서버가 호출할 수 있는 Python API 형태로 연결한다.

이 실험은 실영상 점수 품질을 확정하는 단계가 아니라, 서비스 API에 붙이기 위한 입력/출력 구조와 서버 내부 계산 흐름을 고정하기 위한 단계다.

## 입력 데이터

- 기본 사용자 영상: `/Users/sonjiwoon/capstone/user_data/y1.mp4`
- 기본 프로 reference: 백엔드 DB에 저장된 프로 선수 `keypointsCsvText` 목록
- 구현 위치: `service/server`
- 실험 웹 위치: `service/web`

## 방법

1. Python 서버가 시작될 때 백엔드 서버의 프로 skeleton API를 호출해 reference 목록을 메모리에 캐싱한다.
2. 백엔드 서버는 분석 요청 시 `multipart/form-data`로 `userVideo`, `metadata`만 Python 서버에 전달한다.
3. Python 서버는 요청 처리 중 임시 파일로만 사용자 영상을 사용한다.
4. Python 서버는 사용자 영상만 MediaPipe 기반 keypoints CSV로 변환한다.
5. 캐싱된 프로 skeleton CSV 목록 전체와 사용자 skeleton CSV를 비교한다.
6. `overallScore` 기준 상위 3개 비교 결과를 `players`에 담는다.
7. 프론트 표시용 좌표는 원본 영상 기준 0~1 smooth 좌표로 유지한다.
8. 유사도 계산용 좌표는 pelvis 중심, torso 축, body-scale 기준으로 별도 변환한다.
9. 후면 영상 기준 keypoints 기반 phase detection v1으로 다리 들기, 스트라이드, 릴리즈, 팔로스루 구간을 잡는다.
10. phase별 시작-끝 body-frame 방향 벡터의 코사인 유사도를 0~100 점수로 변환한다.
11. 관절 confidence를 가중치로 사용해 phase 점수를 계산한다.
12. phase별 가중 평균으로 `overallScore`를 계산한다.
13. 구속은 실제 거리, 릴리즈 프레임, 도착 프레임 기반 TOF 방식으로 계산한다.

## 현재 API 응답 핵심

백엔드 저장용 응답에는 다음 값이 포함된다.

- `analysisId`
- `algorithmName`
- `user_data.skeleton_data_id`
- `user_data.skeleton_data`
- `user_data.frame_count`
- `user_data.fps`
- `user_data.resolution`
- `players`
- `players[].overallScore`
- `players[].phaseScores`

## 구현 파일

| 파일 | 역할 |
| --- | --- |
| `service/server/app.py` | Flask API 엔드포인트와 응답 JSON 구성 |
| `service/server/analysis/pose.py` | MediaPipe keypoints CSV 생성 |
| `service/server/analysis/normalization.py` | pelvis/torso/body-scale 기반 분석 좌표 생성 |
| `service/server/analysis/phase.py` | 후면 영상 기준 keypoints 기반 phase detection v1 |
| `service/server/analysis/similarity.py` | phase별 방향 벡터 점수와 전체 점수 계산 |
| `service/server/analysis/speed.py` | TOF 기반 구속 계산 |

## 관찰 결과

- 원본 영상 저장 없이도 백엔드가 저장할 수 있는 분석 결과 구조를 만들었다.
- 사용자 `skeleton_data`를 저장용 원문으로 유지하고, 프론트 표시용 좌표는 나중에 백엔드가 파싱해서 내려주는 구조로 정리했다.
- 프로 선수는 영상 파일이 아니라 서버 시작 시 캐싱한 `pro_skeleton_data` 목록으로 비교하는 방향으로 API 계약을 변경했다.
- 기존 exp07의 phase 시작-끝 방향 벡터 점수를 API 서버에 연결했다.
- 기존 비율 기반 phase 분할 대신 keypoints 기반 phase detection v1을 넣었다.
- 점수 계산용 좌표와 표시용 좌표를 분리했다.
- `responseSchemaVersion`, `scoreScale`, OpenAPI 초안, 목업 응답, JSON 오류 응답을 추가해 백엔드 연동 기준을 구체화했다.
- 사용자/pro skeleton CSV를 프론트 표시용 `displayKeypoints`로 바꾸는 참조 구현을 추가했다.

## 문제점

- 아직 실영상 검증을 진행하지 않았다.
- phase detection v1은 휴리스틱이므로 영상별로 릴리즈/팔로스루 경계가 흔들릴 수 있다.
- phase 내부 궤적은 아직 반영하지 않는다.
- confidence가 낮은 관절은 제외하고, 남은 관절은 confidence 기반 가중 평균으로 phase 점수를 계산한다.
- 구속 측정은 자동 공 탐지가 아니라 수동 프레임 입력 기반 TOF 방식이다.

## 유사도 알고리즘에 주는 의미

이 실험은 유사도 알고리즘이 서비스 구조에 붙을 수 있는 최소 단위를 정의한다.

핵심은 다음 세 가지다.

- 백엔드 저장 단위는 원본 영상이 아니라 사용자 `skeleton_data`와 Top 3 점수 JSON이다.
- 프로 skeleton CSV는 별도 reference 데이터로 저장하고, Python 서버 시작/갱신 시 백엔드에서 받아 캐싱한다.
- 프론트 표시는 원본 영상 위에 별도 skeleton JSON을 그리는 방식이다.
- 유사도 계산은 표시 좌표가 아니라 body-frame 분석 좌표에서 수행한다.

## 현재 결정

- 서비스 API v1 응답에는 반드시 사용자 `user_data.skeleton_data`를 포함한다.
- 서비스 API v1 응답의 `players`에는 `overallScore` 기준 Top 3 비교 결과만 포함한다.
- 응답 스키마 버전은 `pitch_analysis_response_v1`로 둔다.
- 촬영 방향은 `rear`만 허용한다.
- 원본 영상은 임시 처리 후 저장하지 않는다.
- 후면 영상 기준 phase detection v1을 다음 실험에서 실제 영상으로 검증한다.
- 현재 점수는 최종 확정 점수가 아니라 서비스 연동 가능한 v1 후보 점수로 둔다.

## 다음 단계

실제 `user_data/y1.mp4`와 프로 skeleton CSV reference 목록을 사용해 exp08 검증을 진행한다.

상세 실행 절차와 합격/보류 기준은 `/Users/sonjiwoon/capstone/Analysis_algorithm/docs/exp08_validation_plan.md`를 기준으로 한다.

검증 시 확인할 항목:

- phase 대표 프레임이 사람이 보기에도 납득 가능한가
- 릴리즈 구간이 너무 짧게 잡히지 않는가
- `players[].phaseScores`가 계산 가능한 상태로 반환되는가
- `user_data.skeleton_data`가 백엔드 저장에 충분한 CSV 원문을 포함하는가
- 프론트 표시용 JSON으로 변환할 때 필요한 smooth 좌표가 모두 있는가

검증 기록은 `validation_notes_template.md`를 복사해 `/Users/sonjiwoon/capstone/Analysis_algorithm/outputs/exp08_service_api_validation/notes.md`로 작성한다.
