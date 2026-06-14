# 유사도 점수 계산 정책

이 문서는 서비스 API v1의 현재 유사도 점수 계산 방식을 정리합니다.

## 현재 방식

현재 `service` 서버의 메인 점수는 `fixed_step_pose_resampling_v1`입니다.

핵심은 phase별로 선수와 사용자의 프레임 수가 달라도 같은 개수의 진행률 step으로 보간한 뒤, 같은 step의 skeleton 자세 거리를 비교하는 방식입니다. 속도 자체는 점수에 넣지 않고, phase 안에서 나타나는 자세 흐름만 비교합니다.

```text
MediaPipe keypoints
-> pelvis 중심 정렬
-> torso 축 기준 body-frame 좌표계 구성
-> stable body-scale로 신체 크기 정규화
-> 좌완/우완 mirror 처리
-> phase 탐지
-> phase별 고정 step 리샘플링
-> 같은 step의 skeleton 자세 거리 비교
-> phaseScore / overallScore 계산
```

## 좌표 정규화

입력 좌표는 원본 화면 좌표를 바로 쓰지 않고 분석용 body-frame 좌표로 변환합니다.

```text
원점: 골반 중심
Y축: 골반 중심 -> 어깨 중심 방향
X축: torso 축에 수직인 방향
scale: median(max(torso, shoulder_width * 1.6, hip_width * 2.0))
```

scale은 매 프레임 torso 길이를 그대로 쓰지 않고, confidence가 유효한 프레임들의 안정적인 median 값을 전체 영상에 고정 적용합니다. 릴리즈 때 몸이 숙여져 torso가 짧아지는 영상에서도 skeleton이 과하게 늘어나는 문제를 줄이기 위함입니다.

## Phase와 step 수

phase는 5개로 나눕니다.

| phase | 한글명 | step 수 | 가중치 |
| --- | --- | ---: | ---: |
| `windup` | 와인드업 | 20 | 0.10 |
| `leg_lift` | 레그 리프트 | 50 | 0.20 |
| `stride` | 스트라이드 | 45 | 0.25 |
| `acceleration` | 가속 | 40 | 0.30 |
| `follow_through` | 팔로스루 | 35 | 0.15 |

각 phase의 시작/끝 프레임이 다르더라도 `np.linspace(startFrame, endFrame, stepCount)`로 목표 프레임을 만들고, 각 관절 좌표를 선형 보간합니다.

예:

```text
선수 stride: 157 -> 179
사용자 stride: 140 -> 191
둘 다 45 step으로 리샘플링
같은 step index끼리 자세 비교
```

## Step별 자세 점수

각 step에서는 15개 주요 관절의 body-frame 좌표 거리를 비교합니다.

```text
distance = euclidean_distance(pro_joint, user_joint)
jointScore = 100 * exp(-0.5 * (distance / 0.55)^2)
jointWeight = sqrt(proConfidence * userConfidence)
stepScore = sum(jointScore * jointWeight) / sum(jointWeight)
```

confidence가 낮은 관절은 제외합니다.

```text
MIN_CONFIDENCE = 0.05
POSE_DISTANCE_SIGMA = 0.55
```

## Phase 점수와 전체 점수

phase 점수는 해당 phase의 유효 step 점수 평균입니다.

```text
phaseScore = mean(validStepScores)
```

전체 점수는 phase 가중 평균입니다.

```text
overallScore = sum(phaseScore * phaseWeight) / sum(validPhaseWeight)
```

## Feedback 기준

`feedback.good`, `feedback.bad`는 phase 점수를 기준으로 생성합니다.

```text
good: phaseScore >= 78
bad: phaseScore <= 68
```

phase 점수 기반 macro 메시지는 good/bad 각각 최대 2개를 먼저 반환합니다. 기준을 만족하는 phase가 없으면, good에는 가장 점수가 높은 phase 1개, bad에는 가장 점수가 낮은 phase 1개를 fallback으로 넣습니다.

`feedback.good/bad`는 기존 JSON 구조를 유지하면서 phase 기반 macro 메시지와 상세 rule 기반 코칭 문장을 함께 담습니다. 릴리즈 요약 값은 `release` 필드로 따로 반환하고, 릴리즈 타이밍/포인트 차이가 임계값을 넘는 경우에만 관련 문장을 `feedback.bad`에 추가합니다.

상세 rule 기반 문장은 현재 계산 가능한 지표만 사용합니다. 사용 지표는 다음 범위로 제한합니다.

- phase 점수 하위 구간
- body-frame 좌표의 디딤 무릎 높이/방향, 디딤발 착지 폭, 투구 팔꿈치/손목 높이, 팔로스루 손목 이동
- phase별 시간 비율 차이
- release timing/point 차이

이 문장은 실제 AI 추론이 아니라 rule 기반 설명입니다. 따라서 “경향”, “확인”처럼 보수적인 표현을 사용하고, 임계값을 넘은 항목만 `feedback.bad`에 최대 8개까지 추가합니다.

## 릴리즈 분석

릴리즈는 별도 이벤트로 계산합니다.

```text
기본: 나가기 전 프레임과 나간 프레임의 midpoint
fallback: 공 탐지 실패 시 손목 속도 기반 proxy midpoint
```

메인 API는 업로드된 user 원본 영상 경로가 있으므로 user release는 공 후보와 팔 속도 gate를 먼저 사용합니다. 캐시된 pro skeleton CSV에는 원본 영상 경로가 없을 수 있으므로, pro release는 공 기반 이벤트가 따로 주입되지 않으면 skeleton proxy release를 사용합니다. 실험 웹사이트 API는 pro/user 영상 경로가 모두 있는 경우 양쪽 모두 공 기반 release를 우선 시도합니다.

릴리즈 피드백은 두 가지를 봅니다.

```text
timing: 전체 투구 구간 내 release 위치 percent 비교
point: release frame에서 throwing wrist body-frame 좌표 비교
```

타이밍 판정:

```text
abs(userPitchPercent - proPitchPercent) <= 7: 비슷함
양수: 사용자가 늦음
음수: 사용자가 빠름
```

포인트 판정:

```text
difference <= 0.22: 비슷함
그 외: heightDifference / sideDifference 중 큰 차이를 메시지로 반환
```

## 현재 구현 위치

- `service/server/analysis/normalization.py`: pelvis/torso/body-scale 기반 분석 좌표 생성
- `service/server/analysis/phase.py`: 후면 영상 기준 keypoints 기반 phase detection
- `service/server/analysis/resampling_preview.py`: fixed-step 리샘플링과 step별 skeleton 자세 점수
- `service/server/analysis/similarity.py`: 메인 API용 phaseScore / overallScore / feedback 조립
- `service/server/analysis/feedback.py`: release 분석과 phase 기반 good/bad 메시지 조립
- `service/server/analysis/coaching_feedback.py`: 관절/시간/릴리즈 지표 기반 상세 good/bad 피드백 생성

## 아직 부족한 점

- 메인 API는 pro 원본 영상을 받지 않으므로 공 기반 pro release를 항상 쓸 수 없습니다.
- `feedback.good/bad`의 상세 원인 후보는 2D body-frame heuristic이므로 의학적/전문 코칭 결론으로 확정하지 않습니다.
- DTW는 현재 서비스 점수에 사용하지 않습니다.
- 후면 영상 원근감은 완전히 제거되지 않습니다.
