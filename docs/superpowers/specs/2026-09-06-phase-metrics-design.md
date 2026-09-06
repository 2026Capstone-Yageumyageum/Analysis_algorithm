# 구간별 상세 지표(phaseMetrics) 설계

작성일: 2026-09-06

## 배경

리포트의 구간별 피드백이 "무엇이 문제인지"는 말하지만 **폼을 고치는 데까지 이어지지 않는다.**
사용자가 짚은 부족한 점은 세 가지다.

1. 문제를 지적하지만 **영상의 어느 순간**을 말하는지 알 수 없다.
2. 숫자가 나와도 **좋은 건지 나쁜 건지, 얼마나 차이 나는지** 감이 오지 않는다.
3. 구간별로 볼 수 있는 **상세 지표가 없다.**

조사해 보니 필요한 값은 이미 계산되고 있으나 중간에 사라진다.

- `AXIS_RULES`(coaching_feedback.py)는 관절 지표 8개를 정의하고, 각 규칙은 라벨·임계값·
  `why`(왜 중요한지)·`favorable_direction`(어느 쪽이 유리한지)을 들고 있다.
- 그런데 지표는 **한국어 문장으로 뭉쳐진 뒤**, `feedback_evidence()` 화이트리스트가
  `metric`/`userValue`/`proValue`를 버린다. `why`도 필드가 아니라 문장 꼬리로만 전달된다.
- 앱은 그 문장에서 정규식으로 숫자를 되뽑는다(`mapReport.splitMetric`). 문구가 바뀌면 깨진다.
- `evidence.userFrame`/`proFrame`은 전달되지만 앱이 한 번도 쓰지 않는다.
  앱에는 이미 `seekToPhase(frame)`가 구현돼 있는데도 연결돼 있지 않다.

즉 재료는 있고 배선이 없다.

## 목표

- 구간별 지표를 **구조화된 형태로** 앱까지 전달한다.
- 각 지표가 **어느 프레임에서 측정됐는지** 함께 전달해, 그 순간으로 이동할 수 있게 한다.
- 임계값과 판정을 함께 전달해, 숫자가 **좋은지 나쁜지** 스스로 말하게 한다.
- 임계를 넘지 않은 지표도 **항상 포함**한다. 그래야 구간을 펼쳤을 때 점검표가 된다.

## 범위 밖

- **새 지표를 만들지 않는다.** 어깨-골반 분리각·상체 기울기 같은 지표 추가는 분석 알고리즘
  작업이라 별도 건으로 다룬다. 이번에는 기존 8개를 제대로 드러내는 데까지다.
- **기존 문장(`feedback.good`/`bad`) 생성 로직을 바꾸지 않는다.** 문장은 요약을 계속 맡는다.
- **`mapReport.splitMetric`(정규식 파싱)을 제거하지 않는다.** 기존 문장이 계속 오므로
  화면도 그대로 동작해야 한다. 문장에서 숫자를 빼는 것이 확정된 뒤에 제거하는 편이 안전하다.

## 계약 변경

`/api/analyze` 응답의 각 player 객체에 `phaseMetrics` 배열을 **추가**한다. 기존 필드는 그대로 둔다.

```json
{
  "phase": "leg_lift",
  "key": "leg_lift_knee_height",
  "label": "디딤 무릎 높이",
  "userValue": 0.42,
  "proValue": 0.35,
  "difference": 0.07,
  "threshold": 0.12,
  "status": "good",
  "favorableDirection": "positive",
  "why": "레그 리프트 높이는 하체에 축적되는 에너지의 크기와 직결됩니다.",
  "userFrame": 41,
  "proFrame": 38
}
```

| 필드 | 설명 |
|---|---|
| `phase` | `AxisRule.phase` (windup / leg_lift / stride / acceleration / follow_through) |
| `key` | `AxisRule.category`. 항목의 안정적인 식별자 |
| `label` | `AxisRule.metric_label`. 사용자에게 보여줄 지표 이름 |
| `userValue`, `proValue` | body-frame 정규화 좌표 기준 측정값. **단위가 없다** — 앱은 단위를 붙이지 않는다 |
| `difference` | `userValue - proValue`. **부호를 유지한다** (`evidence.difference`는 절댓값이라 다르다) |
| `threshold` | `AxisRule.threshold`. 이 값 이하면 양호로 본다 |
| `status` | `good` / `warn` / `favorable` / `unavailable` |
| `favorableDirection` | `positive`(큰 쪽이 유리) / `negative` / `null` |
| `why` | 이 지표가 왜 중요한지. 기존에는 문장 꼬리에만 있었다 |
| `userFrame`, `proFrame` | 측정이 일어난 프레임. 앱의 "이 순간 보기"가 쓴다 |

### status 판정

```
user_point 또는 pro_point 를 얻지 못함        → unavailable  (값은 모두 null)
|difference| <= threshold                     → good
|difference| >  threshold 이고
  부호가 favorable_direction 과 일치하며
  comparison_mode == "best_pitch"             → favorable
그 외                                          → warn
```

`favorable`을 최고의 1구 비교에서만 쓰는 이유: 프로 비교에서는 유리한 방향의 차이도 여전히
"프로와 다른 점"으로 다루는 것이 기존 동작이다(`_axis_metric_tips(skip_favorable=is_best_pitch)`).
판정 기준을 두 곳에서 다르게 두면 같은 화면에서 앞뒤가 맞지 않는다.

`unavailable`을 감추지 않는 이유: 값이 없는 것과 문제가 없는 것은 사용자에게 전혀 다른
의미다. 앞서 mock 폴백을 걷어낸 것과 같은 판단이다.

## 저장소별 변경

### 1. analysis (분석 서버)

- 새 모듈 `service/server/analysis/phase_metrics.py`
  - `build_phase_metrics(user_pose, pro_pose, user_phases, pro_phases, comparison_mode) -> list[dict]`
  - `AXIS_RULES`를 순회하며 **임계 초과 여부와 무관하게** 항상 항목을 만든다.
  - 좌표 조회는 기존 `point_at_phase` / `metric_value`를 재사용한다.
- `similarity.compute_similarity` 반환값에 `phaseMetrics`를 더한다.
- `coaching_feedback.py`의 **문장 생성 로직은 바꾸지 않는다.** `AXIS_RULES`만 읽어 쓴다.
  다만 "유리한 방향" 판정(`_is_favorable`)은 `AxisRule`의 성질이므로
  `coaching_feedback_utils.py`로 옮겨 `is_favorable`로 공유한다. 문장 생성과 지표 산출이
  각자 판정을 들고 있으면 언젠가 서로 다른 답을 낸다. 옮기는 것뿐이고 로직은 그대로다.

### 2. backend (Spring)

`PlayerAnalysisDto`는 고정 필드만 가지므로, **DTO에 없는 필드는 역직렬화에서 버려진다.**
분석 서버만 고치면 앱까지 도달하지 못한다.

- `PhaseMetricDto` 추가
- `PlayerAnalysisDto`에 `phaseMetrics: List<PhaseMetricDto>? = null` 추가

그 외 변경 없음. `detailJson` 재직렬화 시 함께 실린다.

### 3. Frontend (앱)

- `analysisApi.ts`: `PhaseMetricDetail` 타입 추가, `PlayerDetail.phaseMetrics?`
- `mapReport.ts`: 지표를 구간별로 묶어 `PhaseFeedback.metrics`에 넣는다
- `PhaseFeedback.tsx`: 카드 하단에 "상세 지표 N개" 접기 행. 펼치면 지표 목록
  - 지표 행: 라벨 + 상태 뱃지 / `나 · 기준` 값 / `차이 X / 허용 Y` / `why` / "이 순간 보기"
- `ReportScreen.tsx`: `seekRequest {frame, nonce}` 상태를 만들어 플레이어에 내려주고,
  요청 시 `ScrollView`를 위로 올린다
- `SkeletonOverlayPlayer.tsx`: `seekRequest`의 `nonce`가 바뀌면 기존 `seekToPhase`를 호출

`ref`/`useImperativeHandle` 대신 상태로 가는 이유는, 플레이어에 이미 프레임 이동 함수가
있어 연결만 하면 되고 명령형 핸들보다 데이터 흐름을 따라가기 쉬워서다.

## 하위 호환과 배포 순서

배포 순서에 제약이 없다.

- 분석 서버를 먼저 올리면: 백엔드가 모르는 필드를 무시한다(Jackson 기본 동작). 깨지지 않는다.
- 백엔드를 먼저 올리면: `phaseMetrics`가 `null`이다.
- 앱이 먼저 올라가면: `phaseMetrics`가 없으므로 **접기 행 자체를 그리지 않는다.**
  빈 패널을 여는 것보다 낫다.

## 검증

- **분석 서버**: `service/server/.venv`에 pytest가 설치돼 있지 않다. 새 의존성을 넣지 않기 위해
  `python`으로 바로 실행되는 단독 검증 스크립트로 `build_phase_metrics`를 확인한다.
  확인 항목: 모든 규칙이 항상 항목이 되는가 / 임계 경계에서 good·warn이 갈리는가 /
  좌표를 못 얻으면 `unavailable`이 되고 값이 `null`인가 / `favorable`이 best_pitch에서만 나오는가.
- **backend**: `./gradlew cleanTest test` — 기존 38개가 그대로 통과하는지.
- **Frontend**: `npx tsc --noEmit`, `npx expo export --platform android`.
- **실기기**: 분석 서버·백엔드가 모두 떠 있어야 실제 지표를 볼 수 있다. 사용자 확인이 필요하다.

## 열린 항목

- 지표가 구간당 1~2개뿐이라 펼친 패널이 얇다. 지표를 늘리는 것은 별도 건으로 남긴다.
- 문장에서 숫자를 빼고 `splitMetric`을 제거하는 일은 이 변경이 자리를 잡은 뒤에 다룬다.
