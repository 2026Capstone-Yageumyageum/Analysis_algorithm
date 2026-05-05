# 유사도 알고리즘 실험 이력

이 문서는 `prior_exp`와 현재 `exp/result`, `exp/summary.csv`를 바탕으로 유사도 알고리즘 개발 과정을 논문에 사용할 수 있는 흐름으로 정리하기 위한 문서입니다.

## 정리 원칙

- 시간순보다 문제 해결 흐름을 우선합니다.
- 각 실험은 “왜 다음 방법으로 넘어갔는가”를 설명해야 합니다.
- 대용량 영상 파일은 직접 포함하지 않고 경로와 결과 요약만 남깁니다.
- 실패 실험도 폐기 이유를 명확히 남깁니다.

## 예정된 정리 흐름

1. 포즈 추정 모델 선택
2. 투수 관심영역과 자르기 전처리 검토
3. 자기폐색과 스켈레톤 안정성 문제
4. 키 기준 정규화와 한계
5. 골반 중심 상대좌표와 몸통/신체 크기 정규화
6. 투구 구간 정의와 구간 분할
7. 전체 동적 시간 정렬(DTW) 실패 분석
8. 구간별 동적 시간 정렬(DTW) 방향 선택
9. PitcherMotion 스타일 시각화 실험
10. 최종 유사도 특징값 후보 정리

## 실험 이력

### 1. 포즈 추정 모델 선택

초기 실험에서는 MediaPipe와 RTMPose를 모두 사용했습니다. 일부 macOS 환경에서 MediaPipe 초기화가 실패하면서 RTMPose가 대체 경로로 사용되었고, 이 과정에서 여러 사용자 영상과 프로 선수 영상에 대해 뼈대 추출 결과를 비교했습니다.

최종적으로 현재 실험 흐름에서는 MediaPipe를 기준 포즈 추정 모델로 사용합니다. 가장 큰 이유는 실험 영상에서 MediaPipe가 RTMPose보다 관절 위치를 더 자연스럽게 잡고, 투구 동작 중 스켈레톤이 더 안정적으로 유지된다고 판단했기 때문입니다.

이 실험의 핵심 문제는 단순히 모델이 달라지는 것이 아니라, 스켈레톤 추출 오류가 이후 정규화와 시간축 정렬 전체에 전파된다는 점입니다.

이후 공간 정규화, 시간축 정렬, PitcherMotion 스타일 시각화 실험도 MediaPipe 2D 관절 좌표를 중심으로 이어졌습니다.

관련 근거:

- `/Users/sonjiwoon/capstone/prior_exp/2026-04-10_root_pitch_experiments/result/experiment_journal.md`
- `/Users/sonjiwoon/capstone/exp/summary.csv`

### 2. 투수 관심영역과 자르기 전처리 검토

초기에는 투수만 보이도록 영상을 자르는 방식을 검토했습니다. 일부 실험에서는 투수 crop 또는 pitch clip을 사용했지만, 현재 유사도 알고리즘의 핵심 단계로 채택한 것은 아닙니다.

이유는 너무 타이트하게 자르면 팔, 다리, 발끝이 잘리거나, 투수의 전신이 보이지 않아 포즈 추정이 더 불안정해질 수 있기 때문입니다.

따라서 현재 정리 기준에서는 별도의 강한 자르기 전처리를 핵심 방법으로 두지 않습니다. 대신 “투수 전신이 안정적으로 들어오는 입력”을 우선하고, 투수 관심영역/자르기 실험은 포즈 추정 안정성 검토 과정으로만 기록합니다.

### 3. 공간 정규화

공간 정규화는 우선 선수 키를 기준으로 진행했습니다. 영상마다 선수 크기와 해상도가 다르기 때문에, 사람의 실제 키 또는 화면상 신체 길이를 기준으로 좌표 크기를 맞추는 방향으로 실험했습니다.

RTMPose 기반 키 정규화 결과도 과거 기준선으로 남아 있지만, 현재 논문용 실험 흐름에서는 별도 단계로 분리하지 않습니다. 현재 공간 정규화 흐름은 MediaPipe 기반 실험을 중심으로 정리합니다.

이 방식은 단순 화면 픽셀 좌표 비교보다 낫지만, 카메라 시점, 원근감, 투수가 앞으로 이동하면서 화면상 크기가 달라지는 문제까지 완전히 해결하지는 못했습니다.

현재 결론은 다음과 같습니다.

- 키 기준 정규화는 현재 공간 정규화의 기본 출발점입니다.
- 하지만 최종 유사도 계산에서는 골반 중심 상대좌표, 몸통 길이 기준 정규화, 신체 기준 좌표계를 함께 고려해야 합니다.

관련 실험:

- `spatial_exp15_ryu_mediapipe_envelope`

### 4. 시간축 정규화

시간축 정규화는 전체 영상에 동적 시간 정렬(DTW)을 바로 적용하려고 했지만, 제대로 연결되지 않았습니다. 특히 다리 들기 이후 릴리즈까지 자연스럽게 이어지지 않거나, 의미가 다른 구간끼리 억지로 정렬되는 문제가 있었습니다.

따라서 현재 방향은 전체 영상을 한 번에 비교하지 않고, 투구 동작을 구간별로 나눈 뒤 각 구간끼리 비교하는 것입니다.

현재 비교 기준:

- 준비
- 다리 들기
- 보폭 이동
- 릴리즈
- 팔로스루

이 방향은 “같은 의미의 동작끼리 시간축을 맞춘다”는 점에서 논문용 알고리즘 설명에 더 적합합니다.

관련 실험:

- `temporal_exp1_ryu_mediapipe_height`
- `temporal_exp2_y2_mediapipe_height`
- `_compare_cache`의 구간별 동적 시간 정렬 결과

### 5. PitcherMotion 스타일 시각화와 특징값 추출

PitcherMotion 스타일 실험은 최종 유사도 점수를 바로 계산하는 실험이 아니라, 두 투구 동작을 비교 가능한 형태로 정규화하고 시각화하기 위한 실험입니다.

핵심 아이디어는 다음과 같습니다.

- 다리 들기 시점을 기준점으로 맞춥니다.
- 프로와 사용자 스켈레톤을 같은 좌표계에 겹쳐 보여줍니다.
- 관절 각도, 손목 높이, 보폭 이동, 몸통 기울기 같은 특징값을 그래프로 확인합니다.
- 분석 기준과 표시 기준을 분리합니다.

이 실험을 통해 유사도 계산 전에 어떤 특징값을 뽑고, 어떤 구간에서 차이가 발생하는지 확인할 수 있었습니다.

다만 준비 구간 길이와 릴리즈 시점 차이가 커서, 이후에는 구간별 동적 시간 정렬을 연결해야 합니다.

관련 실험:

- `pitchermotion_style_exp1_y1_ryu`
- `pitchermotion_style_exp2_y1_ryu_preroll`

### 6. 현재 정리된 방향

현재까지의 흐름을 바탕으로 유사도 알고리즘은 다음 순서로 정리합니다.

```text
MediaPipe 2D 관절 좌표 추출
-> 키 기준 공간 정규화
-> 골반 중심 상대좌표와 신체 크기 기준 보정
-> 투구 구간 분할
-> 구간별 동적 시간 정렬
-> 관절 각도, 상대좌표, 정규화 길이, 전방/좌우 이동 특징값 비교
```

즉, 현재 실험 정리의 핵심은 “MediaPipe를 기준으로 하고, 공간은 우선 키 기준으로 맞추되, 시간축은 전체 영상이 아니라 투구 구간별로 비교한다”입니다.

### 7. Phase 시작-끝 방향 벡터 기반 B 실험

유사도 점수를 1~100으로 만들기 위한 첫 번째 정량 후보로 phase 시작-끝 방향 벡터 비교를 진행했습니다.

이 방식은 각 phase의 시작 프레임과 끝 프레임에서 관절 이동 방향만 계산합니다. 이동량 크기와 속도 차이를 줄이기 위해 각 벡터를 단위 벡터로 바꾼 뒤, 프로 선수와 사용자 벡터의 코사인 유사도를 1~100 점수로 변환했습니다.

이번 실험의 전체 후보 점수는 58.32였습니다. 팔로스루는 84.07로 높게 나왔지만, 릴리즈는 36.86으로 낮게 나왔습니다. 특히 릴리즈 구간이 프로 영상 기준 2프레임으로 잡혀 방향 벡터가 노이즈에 민감한 상태였습니다.

이 실험의 의미는 “시간에 따른 변화량을 최대한 제거하고 phase별 최종 방향성만 비교할 수 있다”는 점입니다. 반대로 phase 내부에서 팔이 어떻게 움직였는지, 코킹과 가속 과정이 어떤 궤적을 보였는지는 반영하지 못합니다.

따라서 B 실험은 1차 정량 후보로 보관하고, 다음 단계에서는 phase 내부 방향 변화 흐름을 비교하는 A 실험을 후보로 둡니다.

관련 결과:

- `/Users/sonjiwoon/capstone/Analysis_algorithm/outputs/exp6/phase_direction_report.md`
- `/Users/sonjiwoon/capstone/Analysis_algorithm/experiments/exp07_phase_direction/README.md`

정리 기준 실험 번호는 `exp07`입니다. 다만 초기 실행 산출물은 당시 스크립트 번호를 따라 `outputs/exp6`에 남아 있으므로, 산출물 경로와 실험 정리 번호를 분리해서 봅니다.

### 8. 서비스 API 연동 스캐폴드

exp07까지의 실험 결과를 바탕으로, 백엔드 서버가 호출할 Python 분석 서버 형태를 별도로 만들었습니다.

현재 위치:

- `/Users/sonjiwoon/capstone/integreted/server`
- `/Users/sonjiwoon/capstone/integreted/web`

이 단계의 목적은 최종 알고리즘 품질 검증이 아니라, 백엔드/프론트와 맞출 데이터 흐름을 고정하는 것입니다.

현재 결정:

- 요청은 `userVideo`, `pro_skeleton_data`, `metadata`를 포함한 `multipart/form-data`로 받습니다.
- 촬영 방향은 후면으로 고정하며, `metadata.cameraView`가 `rear`가 아니면 서버에서 거부합니다.
- 원본 영상은 임시 처리 후 저장하지 않습니다.
- 응답에는 `responseSchemaVersion`, `scoreScale`, `user_data.skeleton_data`, `players` Top 3 결과를 포함합니다.
- 백엔드는 사용자 `skeleton_data`를 DB에 저장하고, 프로 skeleton CSV는 별도 reference 데이터로 관리합니다.
- 프론트에는 선택된 `players[].phaseScores`와 사용자/프로 skeleton CSV를 표시용 skeleton JSON으로 변환해서 내려주는 방향입니다.

현재 구현 보강:

- `integreted/server/analysis/phase.py`에 후면 영상 기준 keypoints 기반 phase detection v1을 추가했습니다.
- `integreted/server/analysis/normalization.py`에 pelvis/torso/body-scale 기반 분석 좌표 생성을 추가했습니다.
- `integreted/server/analysis/similarity.py`는 비율 기반 구간 대신 탐지된 phase 구간과 body-frame 좌표를 사용하도록 변경했습니다.
- 공통 오류 응답을 `status:error` JSON 형태로 정리했습니다.
- OpenAPI 초안과 5프레임 목업 응답을 추가했습니다.
- `keypointsCsvText`를 프론트 표시용 `displayKeypoints`로 변환하는 참조 구현을 추가했습니다.

이 단계의 한계:

- 아직 실영상 검증을 하지 않았습니다.
- phase detection v1은 휴리스틱이므로 릴리즈/팔로스루 경계가 영상별로 흔들릴 수 있습니다.
- confidence 기반 phase 점수 가중 평균은 적용했지만, 실제 영상 점수 분포 검증은 아직 하지 않았습니다.

관련 문서:

- `/Users/sonjiwoon/capstone/Analysis_algorithm/docs/service_api_contract.md`
- `/Users/sonjiwoon/capstone/Analysis_algorithm/docs/openapi.yaml`
- `/Users/sonjiwoon/capstone/Analysis_algorithm/docs/keypoints_csv_schema.md`
- `/Users/sonjiwoon/capstone/Analysis_algorithm/docs/scoring_policy.md`
- `/Users/sonjiwoon/capstone/Analysis_algorithm/docs/frontend_skeleton_rendering.md`
- `/Users/sonjiwoon/capstone/Analysis_algorithm/docs/backend_integration_guide.md`
- `/Users/sonjiwoon/capstone/Analysis_algorithm/docs/service_response_mock.md`
- `/Users/sonjiwoon/capstone/Analysis_algorithm/docs/exp08_validation_plan.md`
