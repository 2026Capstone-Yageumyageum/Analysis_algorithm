# 유사도 알고리즘 고도화 아이디어

이 문서는 유사도 알고리즘 v1을 서비스 API에 붙일 수 있는 수준으로 고도화하는 동안 떠오르는 아이디어를 계속 기록하기 위한 공간입니다.

## 기록 규칙

- 아이디어는 바로 구현하지 않아도 적습니다.
- 실험으로 확인한 내용과 아직 가설인 내용을 구분합니다.
- 나중에 논문/보고서에 쓸 수 있도록 “왜 필요한가”를 함께 남깁니다.
- 실패 가능성이 큰 아이디어도 폐기 근거를 남기기 위해 기록합니다.

## 현재 목표

사용자 후면 투구 영상과 프로 후면 투구 영상을 입력받아, 원본 영상은 저장하지 않고 `skeleton_data`, phase별 점수, 전체 점수만 백엔드가 저장할 수 있도록 Python 유사도 분석 서버를 정리합니다.

## 아이디어 목록

### 1. phase detection을 비율 분할에서 keypoints 기반으로 전환

- 배경: 초기 스캐폴드의 phase 구간은 영상 전체 길이를 비율로 나누는 임시 방식이었습니다.
- 아이디어: 다리 들기는 리드 무릎 높이, 스트라이드는 보폭 발 전진량, 릴리즈는 투구 손목 속도/팔꿈치-어깨 관계, 팔로스루는 릴리즈 이후 투구 손목 하강과 몸 중심 이동으로 잡습니다.
- 기대 효과: phase 경계가 실제 투구 동작 의미와 맞아져 DTW와 phase별 점수가 덜 흔들립니다.
- 확인 필요: 후면 영상에서 손목 confidence가 낮을 때 릴리즈 후보가 튀는지 확인해야 합니다.
- 적용 상태: `service/server/analysis/phase.py`에 v1 휴리스틱과 최소 길이 fallback을 추가했습니다. exp08 실영상 strict 검증을 통과했습니다.

### 2. 분석용 좌표와 표시용 좌표를 분리

- 배경: 서비스에서는 사용자가 저장한 원본 영상 위에 skeleton을 그려야 합니다.
- 아이디어: 분석용은 pelvis/torso/body-scale 정규화 좌표를 사용하고, 표시용은 원본 영상 기준 0~1 smooth 좌표를 유지합니다.
- 기대 효과: 점수 계산은 카메라/신체 크기 차이에 덜 흔들리고, 프론트 표시는 원본 영상 위에 정확히 맞출 수 있습니다.
- 적용 상태: `service/server/analysis/normalization.py`에서 분석용 body-frame 좌표를 만들고, 응답의 `skeleton_data`는 표시용 0~1 smooth 좌표를 유지합니다.

### 3. phase 내부 흐름 비교 후보 유지

- 배경: exp07 B 실험은 phase 시작-끝 방향 벡터만 비교해서 내부 궤적을 반영하지 못합니다.
- 아이디어: phase 내부를 일정 비율로 리샘플링한 뒤 관절 방향 변화 시퀀스를 비교하는 A 실험을 다음 후보로 둡니다.
- 기대 효과: 코킹, 가속, 릴리즈 직전 팔 흐름처럼 시작-끝만으로 사라지는 정보를 일부 살릴 수 있습니다.
- 리스크: 시간축 변화량을 다시 많이 반영하면 사용자의 속도 차이가 점수에 과도하게 들어갈 수 있습니다.

### 4. 릴리즈 phase 최소 길이 조건

- 배경: exp07에서 프로 릴리즈 구간이 2프레임으로 잡혀 방향 벡터 점수가 노이즈에 민감했습니다.
- 아이디어: 릴리즈 phase가 너무 짧게 잡히면 앞뒤 프레임을 확장하거나 `release_window`를 별도 정의합니다.
- 기대 효과: 손목/팔꿈치 벡터가 한 프레임 오차에 크게 흔들리는 문제를 줄입니다.

### 5. skeleton_data는 저장용 원문, 프론트는 파싱된 표시용 JSON

- 배경: 백엔드는 DB에 분석 결과를 저장해야 하고, 프론트는 skeleton을 그려야 합니다.
- 아이디어: Python 서버 응답에는 `skeleton_data`를 포함해 DB 저장 원문을 보장하고, 백엔드가 프론트 응답 시에는 `_smooth` 좌표 중심의 `displayKeypoints`로 변환합니다.
- 기대 효과: 실험 재현성과 프론트 렌더링 편의성을 동시에 확보합니다.

### 6. 관절 confidence 기반 phase 점수 가중 평균

- 배경: 후면 영상에서는 손목, 발목, 발끝 관절 confidence가 프레임마다 크게 흔들릴 수 있습니다.
- 아이디어: phase 점수를 단순 평균하지 않고, 사용자와 프로 관절 confidence의 기하평균을 관절별 가중치로 사용합니다.
- 기대 효과: 낮은 confidence 관절 하나가 phase 점수를 과도하게 끌어내리는 문제를 줄이고, 실제로 잘 검출된 관절을 더 신뢰합니다.
- 적용 상태: `service/server/analysis/similarity.py`에 `confidenceWeight = sqrt(userConfidence * proConfidence)` 방식으로 1차 반영했습니다.
- 확인 필요: 실영상에서 confidence가 높은 관절만 남아 점수가 지나치게 관대해지는지 확인해야 합니다.

### 7. phase detection 후보 선택에도 confidence를 반영

- 배경: 현재 phase 점수에는 confidence 가중치가 들어갔지만, phase 경계 탐지 자체는 주로 무릎 높이, 손목 속도, 발끝 거리 같은 좌표 변화량을 기준으로 합니다.
- 아이디어: 릴리즈 후보를 고를 때 투구 손목/팔꿈치 confidence가 낮은 프레임은 후보 점수를 낮추고, 레그 리프트/스트라이드는 무릎/발끝 confidence를 함께 반영합니다.
- 기대 효과: MediaPipe가 손목이나 발끝을 잘못 찍은 한두 프레임 때문에 phase 경계가 튀는 문제를 줄일 수 있습니다.
- 리스크: 후면 영상에서는 중요 관절 confidence가 전반적으로 낮을 수 있어, 너무 강하게 적용하면 phase를 못 찾는 경우가 늘어날 수 있습니다.
- 적용 상태: 아직 미적용입니다. exp08 실영상 검증 후 phase 경계가 흔들릴 때 우선 적용 후보로 둡니다.

### 8. phase 최소 길이 guard와 fallback 확장

- 배경: exp08 실영상 검증에서 프로 `stride` 구간이 `242~242`로 붕괴했고 사용자 `follow_through` 구간도 `351~352`로 너무 짧게 잡혔습니다.
- 아이디어: phase 시작/끝 프레임이 같거나 최소 길이보다 짧으면 release 기준 앞뒤 고정 window 또는 인접 phase 비율 window로 확장합니다.
- 기대 효과: 시작-끝 방향 벡터가 1프레임 노이즈에 지배되는 문제를 줄이고 strict 검증에서 `no_valid_joint`가 발생하는 상황을 줄입니다.
- 리스크: fallback window가 실제 phase 의미와 어긋나면 점수는 계산되지만 해석력이 떨어질 수 있습니다.
- 적용 상태: `service/server/analysis/phase.py`에 1차 적용했습니다. exp08 재검증에서 모든 phase가 `ready`가 되었지만, fallback으로 확장된 구간의 시각 검토가 필요합니다.

### 9. 응답 JSON에 phaseDetection과 normalization 진단 메타 포함

- 배경: exp08 검증에서 normalization과 throwingSide가 실제 응답 JSON에 명시되지 않아 백엔드와 프론트가 품질 상태를 확인하기 어렵습니다.
- 아이디어: `players[].phaseDetection` 또는 `diagnostics`에 phase별 탐지 근거, frame window, 최소 길이 보정 여부를 넣고, `normalization`에는 bodyScale, torso axis, throwingSide, mirror 여부를 넣습니다.
- 기대 효과: 점수가 이상할 때 원인이 skeleton 품질인지 phase detection인지 정규화인지 빠르게 추적할 수 있습니다.
- 리스크: 응답 크기와 계약 복잡도가 조금 늘어납니다.
- 적용 상태: `service/server/app.py` 응답의 `players[]`에 `phaseDetection`과 `normalization`을 포함했습니다. `scripts/validate_pitch_analysis_response.py`에서도 해당 메타가 있으면 검증합니다.
