# exp09_pose_resampling_vs_dtw

## 실험 이름

고정 step 자세 리샘플링과 pose-only DTW 비교

## 목적

속도 feature를 제외하고 오직 자세만 비교할 때, 두 영상의 프레임 수 차이를 어떤 방식으로 맞추는 것이 적절한지 확인한다.

비교 대상은 다음 두 가지다.

1. `fixed_step_resampling`: 각 phase를 고정 개수의 진행률 step으로 선형 보간한 뒤 같은 step끼리 자세를 비교한다.
2. `pose_dtw`: 각 phase 안에서 body-frame 자세 벡터가 가까운 프레임쌍을 DTW로 정렬한 뒤 같은 점수식으로 자세를 비교한다.

두 방식 모두 관절 속도 feature는 사용하지 않는다.

## 입력 데이터

- 프로 영상: `/Users/sonjiwoon/capstone/pro_data/hyun_jin_ryu_ball_to_junior_caminero_20230923_6s.mp4`
- 사용자 영상: `/Users/sonjiwoon/capstone/user_data/y1.mp4`
- 기본 keypoints 입력: `/Users/sonjiwoon/capstone/Analysis_algorithm/outputs/exp6/pro/keypoints.csv`
- 기본 사용자 keypoints 입력: `/Users/sonjiwoon/capstone/Analysis_algorithm/outputs/exp6/user/keypoints.csv`
- 기본 산출물: `/Users/sonjiwoon/capstone/Analysis_algorithm/outputs/exp09_resampling_vs_pose_dtw`

## 방법

1. 기존 MediaPipe keypoints CSV를 읽는다.
2. 현재 서비스 서버의 `service/server/analysis/normalization.py` 기준으로 body-frame 좌표를 만든다.
3. 현재 서비스 서버의 `service/server/analysis/phase.py` 기준으로 phase 구간을 탐지한다.
4. phase별 role-normalized 관절을 사용한다.
   - 투구팔, 글러브팔, 디딤발, 축발을 `throwing_side`, `stride_side` 기준으로 해석한다.
5. 고정 step 방식은 phase별 기준 step 수로 선형 보간한다.
   - `windup`: 20
   - `leg_lift`: 50
   - `stride`: 45
   - `acceleration`: 40
   - `follow_through`: 35
6. pose-only DTW 방식은 같은 phase 안에서 body-frame 자세 벡터를 사용해 DTW path를 만든다.
7. 두 방식 모두 같은 관절 거리 기반 점수식을 사용한다.

```text
poseScore = 100 * exp(-0.5 * (joint_distance_body_units / sigma)^2)
sigma = 0.55
```

## 서비스 phase 기준 결과

| 항목 | 결과 |
| --- | ---: |
| 고정 step 리샘플링 overall | 66.81 |
| pose-only DTW overall | 68.50 |
| DTW - 고정 step | 1.69 |

| phase | fixed step | pose-only DTW | 차이 |
| --- | ---: | ---: | ---: |
| `windup` | 82.22 | 82.04 | -0.18 |
| `leg_lift` | 55.34 | 57.29 | +1.95 |
| `stride` | 46.72 | 51.01 | +4.29 |
| `acceleration` | 80.37 | 80.96 | +0.59 |
| `follow_through` | 78.21 | 78.64 | +0.43 |

## 기존 alignment boundary 기준 참고 결과

기존 `outputs/exp6/phase_dtw_alignment.json`의 phase boundary를 그대로 쓰면 다음처럼 나온다.

| 항목 | 결과 |
| --- | ---: |
| 고정 step 리샘플링 overall | 61.08 |
| pose-only DTW overall | 64.93 |
| DTW - 고정 step | 3.85 |

이 경우에는 `stride`에서 DTW가 7.76점 더 높게 나와 phase 내부 타이밍 어긋남을 더 많이 흡수했다. 다만 기존 alignment boundary는 `acceleration`이 프로 2프레임, 사용자 4프레임으로 잡히는 문제가 있어 서비스 phase 기준 결과를 우선 참고한다.

## 관찰 결과

- 현재 서비스 phase 기준에서는 pose-only DTW가 1.69점 높지만, 전체 차이는 아직 작다.
- 따라서 “속도는 제외하고 자세만 비교”하는 v2 후보로는 고정 step 리샘플링이 먼저 적용하기에 충분하다.
- DTW는 phase 내부 타이밍 차이가 큰 경우 점수를 더 높게 만들 수 있지만, 실제 자세 차이를 지나치게 흡수할 가능성도 있다.
- 고정 step 방식은 설명이 쉽고 프론트에서 같은 진행률의 user/pro skeleton을 보여주기 좋다.

## 문제점

- phase 탐지 경계가 흔들리면 두 방식 모두 영향을 받는다.
- 서비스 phase 기준에서도 일부 phase는 최소 길이 fallback warning이 발생했다.
- `stride`처럼 한쪽 영상의 phase가 매우 짧고 다른 쪽이 긴 경우, fixed step은 보간/다운샘플링 비중이 커진다.
- 레그리프트 끝은 디딤발 무릎의 화면상 최고점으로 잡는다.
- 스트라이드 끝은 디딤발이 화면상 지면에 가까워지고 속도가 줄어드는 앞발 착지 후보로 잡는다.
- 가속은 앞발 착지부터 릴리즈 proxy까지, 팔로스루는 그 이후로 나눈다.
- 이번 결과는 기본 영상쌍 1개 기준이라, 여러 사용자 영상과 여러 프로 reference로 점수 분포를 더 확인해야 한다.

## 현재 결정

- v2 첫 구현은 고정 step 리샘플링 기반 자세 유사도로 진행한다.
- DTW는 비교 실험과 시각화용 고도화 후보로 유지한다.
- 점수 계산에는 속도 feature를 넣지 않고, phase 진행률 기준 자세 흐름만 비교한다.

## 재실행 방법

```bash
cd /Users/sonjiwoon/capstone/Analysis_algorithm
.venv311/bin/python scripts/compare_pose_resampling_vs_dtw.py
```

기존 alignment boundary 기준 결과도 보고 싶으면 다음 명령을 사용한다.

```bash
.venv311/bin/python scripts/compare_pose_resampling_vs_dtw.py \
  --phase-source alignment \
  --output-dir outputs/exp09_resampling_vs_pose_dtw_alignment_boundaries
```

## 산출물

- `/Users/sonjiwoon/capstone/Analysis_algorithm/outputs/exp09_resampling_vs_pose_dtw/comparison.json`
- `/Users/sonjiwoon/capstone/Analysis_algorithm/outputs/exp09_resampling_vs_pose_dtw/phase_scores.csv`
- `/Users/sonjiwoon/capstone/Analysis_algorithm/outputs/exp09_resampling_vs_pose_dtw/fixed_step_step_scores.csv`
- `/Users/sonjiwoon/capstone/Analysis_algorithm/outputs/exp09_resampling_vs_pose_dtw/pose_dtw_pair_scores.csv`
- `/Users/sonjiwoon/capstone/Analysis_algorithm/outputs/exp09_resampling_vs_pose_dtw/report.md`
