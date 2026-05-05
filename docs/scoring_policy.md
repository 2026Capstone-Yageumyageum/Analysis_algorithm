# 유사도 점수 계산 정책

이 문서는 유사도 알고리즘 v1의 점수 계산 방향을 정리합니다.

## 현재 점수 후보

현재 `integreted` 서버의 점수는 phase별 시작-끝 관절 방향 벡터 비교입니다.

입력 좌표는 원본 화면 좌표를 바로 쓰지 않고, 다음 분석용 좌표로 변환한 뒤 사용합니다.

```text
원본 0~1 smooth 좌표
-> pelvis 중심 정렬
-> torso 축 기준 body-frame 좌표계 구성
-> body-scale로 나누어 신체 크기 정규화
-> 좌완/우완 mirror 처리
```

```text
phase 시작 프레임의 관절 위치
phase 끝 프레임의 관절 위치
-> 관절 이동 벡터
-> 단위 벡터 변환
-> 사용자 벡터와 프로 벡터의 코사인 유사도
-> 0~100 점수로 변환
```

코사인 유사도 변환식:

```text
score = ((cos_similarity + 1) / 2) * 100
```

## 관절 confidence 가중치

각 관절 점수는 사용자와 프로 영상의 boundary confidence를 함께 반영합니다.

```text
jointConfidenceWeight = sqrt(userConfidence * proConfidence)
phaseScore = sum(jointScore * jointConfidenceWeight) / sum(jointConfidenceWeight)
```

단, 사용자 또는 프로 중 하나라도 confidence가 너무 낮으면 해당 관절은 제외합니다.

```text
MIN_JOINT_CONFIDENCE = 0.05
```

## phase별 기본 가중치

초기 v1 가중치는 다음과 같이 둡니다.

| phase | 한글명 | 가중치 | 이유 |
| --- | --- | ---: | --- |
| `leg_lift` | 레그 리프트 | 0.25 | 투구 시작 균형과 하체 준비를 반영 |
| `stride` | 스트라이드 | 0.30 | 보폭 이동과 상하체 연결이 크게 드러남 |
| `release` | 릴리즈 | 0.30 | 투구폼 차이가 가장 직접적으로 드러남 |
| `follow_through` | 팔로스루 | 0.15 | 릴리즈 이후 마무리 흐름을 보조적으로 반영 |

전체 점수:

```text
overallScore = sum(phaseScore * phaseWeight) / sum(validPhaseWeight)
```

## phase별 관절 후보

| phase | 주요 관절 |
| --- | --- |
| `leg_lift` | 양쪽 무릎, 양쪽 발목, 양쪽 손목 |
| `stride` | 양쪽 foot index, 양쪽 무릎, 양쪽 손목 |
| `release` | 양쪽 어깨, 양쪽 팔꿈치, 양쪽 손목 |
| `follow_through` | 양쪽 어깨, 양쪽 팔꿈치, 양쪽 손목 |

## 아직 부족한 점

- phase 내부 궤적을 반영하지 못합니다.
- 릴리즈 구간이 너무 짧으면 한 프레임 오차에 크게 흔들립니다. 현재는 최소 길이 확장을 v1로 적용했지만 실영상 검증이 필요합니다.
- 손목 confidence가 낮으면 투구팔 점수가 흔들릴 수 있습니다.
- 후면 영상 원근감은 완전히 제거되지 않습니다.

## 현재 구현 위치

- `integreted/server/analysis/normalization.py`: pelvis/torso/body-scale 기반 분석 좌표 생성
- `integreted/server/analysis/phase.py`: 후면 영상 기준 keypoints 기반 phase detection v1
- `integreted/server/analysis/similarity.py`: confidence-weighted phase별 방향 벡터 점수와 overallScore 계산

## 다음 고도화 후보

- phase 내부를 일정 길이로 리샘플링한 뒤 방향 변화 흐름을 비교합니다.
- 관절 방향 벡터에 관절 각도 차이를 함께 반영합니다.
- 릴리즈 phase는 최소 프레임 길이 조건을 둡니다.
