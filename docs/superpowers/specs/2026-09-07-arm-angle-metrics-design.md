# 팔 각도 지표(관절 각도) 설계

작성일: 2026-09-07

## 배경

`phaseMetrics`(2026-09-06)로 구간별 지표 8개를 앱까지 내보냈다. 그런데 그 8개는 전부
**관절 한 점의 좌표**에서 나온다.

```
관절 하나 → 구간의 특정 진행률 시점 → 그 순간의 x·y → 높이 / 좌우거리 / 직선거리
```

한 점으로 만들 수 없는 것들이 있다. 각도는 세 점이, 비틀림은 두 선분이, 속도는 시간축이
필요하다. 분석 패키지 전체에 `angle`·`atan2`·`degrees` 검색 결과가 **0건**이다.

이번 건은 그중 **각도**를 추가한다. 요청의 동기는 일관성 측정이다 — 투구마다 팔이 같은
경로로 나오는가.

각도에는 기존 지표에 없는 성질이 하나 있다. 정규화 좌표계는 골반 중심 이동, 몸통축 회전,
단일 스칼라(`body_scale`) 나눗셈으로 만들어진다. 회전은 직교 변환이고 스케일은 등방이므로
**각도는 정규화에 영향받지 않고 보존된다.** 기존 8개가 "단위 없는 좌표값이라 그 자체로는
읽을 수 없는" 지표였던 것과 반대로, 각도는 도(°) 그대로 의미를 갖는다.

## 목표

- 팔 동작의 각도 지표를 기존 `phaseMetrics` 파이프라인에 얹는다.
- 도(°) 단위를 계약에 명시해, 앱이 단위와 정밀도를 올바르게 표기한다.
- 새 측정 시점을 만들지 않는다. 기존 지표가 쓰는 시점을 재사용한다.

## 범위 밖

- **문장 생성(`coaching_feedback.py`)을 바꾸지 않는다.** 각도는 상세 지표에만 나오고
  `feedback.good`/`bad` 문장에는 등장하지 않는다. `phaseMetrics` 때와 같은 원칙이다.
- **어깨-골반 분리각(몸 비틀림), 속도 계열은 다루지 않는다.** 각각 별도 건이다.
- **데이터 기반 임계값을 만들지 않는다.** 사용자의 과거 기록 분산에서 임계를 뽑는 것이
  "일관성"의 정의에 가장 충실하지만, 백엔드에 과거 기록 집계 API가 새로 필요하고 최소
  기록 수가 쌓여야 동작한다. 이번에는 고정 상수를 쓴다.

## 지표 정의

### 팔꿈치 굽힘각 (`elbow_flexion`)

투구 팔의 어깨·팔꿈치·손목 세 점이 이루는 사이각. 0~180°.

```
v1 = shoulder - elbow
v2 = wrist    - elbow
angle = degrees(atan2(|cross(v1, v2)|, dot(v1, v2)))
```

180°면 팔이 곧게 편 상태, 작을수록 접힌 상태다. `atan2(|cross|, dot)`을 쓰는 이유는
`acos(dot/|v1||v2|)`가 두 벡터가 거의 나란할 때 수치적으로 불안정하기 때문이다.

### 암슬롯 (`arm_slot`)

상완 벡터(어깨→팔꿈치)가 몸통축에서 벌어진 각. 0~180°.

```
u = elbow - shoulder            (정규화 좌표계)
angle = degrees(atan2(|u.x|, u.y))
```

0°는 팔이 몸통축 방향으로 곧게 선 상태, 90°는 몸통과 직각(사이드암), 180°는 아래로
내린 상태다.

**수평이 아니라 몸통축을 기준으로 잡은 것이 이 정의의 핵심이다.** 정규화 좌표계의 y축이
이미 골반 중심 → 어깨 중심 방향이므로, 상체가 기울어도 자동으로 보정된다. 수평 기준으로
재면 상체를 많이 숙이는 투수는 실제 암슬롯이 같아도 매번 다른 값이 나온다.

`u.x`에 절댓값을 쓰는 이유는 두 가지다. 좌완/우완에 따라 부호가 뒤집히고, 정규화 단계에
`mirror_x`(좌우반전)가 있어 부호가 또 뒤집힌다. 절댓값을 쓰면 둘 다 무관해진다.

### 퇴화 케이스

`|v1|`, `|v2|`, `|u|` 중 하나라도 0에 가까우면(관절이 겹쳐 보이는 경우) 각도가 정의되지
않는다. 이때는 `unavailable`로 처리한다. 판정 기준은 `1e-9`.

## 측정 시점과 임계값

| 구간 | 시점 | 지표 | key | 허용 |
|---|---|---|---|---|
| leg_lift | 100% | 팔꿈치 굽힘각 | `leg_lift_elbow_flexion` | 15° |
| leg_lift | 100% | 암슬롯(상완 기울기) | `leg_lift_arm_slot` | 10° |
| stride | 100% | 팔꿈치 굽힘각 | `stride_elbow_flexion` | 15° |
| stride | 100% | 암슬롯(상완 기울기) | `stride_arm_slot` | 10° |
| acceleration | 85% | 팔꿈치 굽힘각 | `acceleration_elbow_flexion` | 15° |
| acceleration | 85% | 암슬롯(상완 기울기) | `acceleration_arm_slot` | 10° |
| follow_through | 80% | 팔꿈치 굽힘각 | `follow_through_elbow_flexion` | 15° |
| follow_through | 80% | 암슬롯(상완 기울기) | `follow_through_arm_slot` | 10° |

**네 시점 모두 기존 `AXIS_RULES`가 이미 쓰는 시점이다.** 새 시점을 만들면 같은 구간
안에서도 "이 순간 보기"가 지표마다 다른 프레임으로 튄다. 시점을 공유하면 한 번 이동해
그 자세에서 여러 지표를 함께 볼 수 있다.

와인드업을 뺀 이유: 팔이 아직 몸 앞에 모여 있어 각도 변동이 커도 진단 가치가 낮다.

임계값 15°/10°는 코칭 통념에 기반한 판단값이며, 기존 8개의 임계값(0.12~0.20)과 마찬가지로
라벨링된 데이터셋에서 나온 값이 아니다. 실기기에서 보면서 조정한다. 상수를 규칙 테이블
한곳에 모아 두는 이유가 이것이다.

### why 문구

| key | why |
|---|---|
| `leg_lift_elbow_flexion` | 레그 리프트 시점의 팔 접힘은 이후 팔 스윙의 출발 자세를 정합니다. |
| `leg_lift_arm_slot` | 이 시점의 팔 높이가 흔들리면 이후 동작 전체가 따라 흔들립니다. |
| `stride_elbow_flexion` | 디딤발이 닿는 순간의 팔 접힘은 팔 스윙이 늦지 않았는지 보여줍니다. |
| `stride_arm_slot` | 디딤발 착지 때 팔이 올라와 있어야 합니다. 늦으면 어깨에 부담이 몰립니다. |
| `acceleration_elbow_flexion` | 릴리즈 직전 팔꿈치 각도는 공에 실리는 힘과 팔꿈치 부하를 함께 좌우합니다. |
| `acceleration_arm_slot` | 암슬롯이 투구마다 흔들리면 릴리즈 포인트가 달라져 제구가 무너집니다. |
| `follow_through_elbow_flexion` | 던진 뒤 팔이 자연스럽게 펴지는지는 감속이 제대로 되는지를 보여줍니다. |
| `follow_through_arm_slot` | 마무리 팔 경로가 일정해야 어깨·팔꿈치 부담이 분산됩니다. |

## 계약 변경

`phaseMetrics` 항목에 `unit` 필드를 **추가**한다. 기존 필드는 그대로다.

```json
{
  "phase": "acceleration",
  "key": "acceleration_arm_slot",
  "label": "암슬롯(상완 기울기)",
  "unit": "degree",
  "userValue": 78.4,
  "proValue": 71.9,
  "difference": 6.5,
  "threshold": 10.0,
  "status": "good",
  "favorableDirection": null,
  "why": "암슬롯이 투구마다 흔들리면 릴리즈 포인트가 달라져 제구가 무너집니다.",
  "userFrame": 62,
  "proFrame": 58
}
```

| 값 | 의미 |
|---|---|
| `"degree"` | 도(°) 단위. 앱이 `°`를 붙인다. 자릿수는 아래 참조 |
| `null` | 단위 없는 정규화 좌표. 기존 8개가 여기 해당하며 표기가 지금과 같다 |

**반올림 자릿수.** 서버는 각도 값(`userValue`/`proValue`/`difference`/`threshold`)을
소수 첫째 자리로 반올림해 보낸다. 기존 축 지표의 넷째 자리(`round(x, 4)`)를 그대로 쓰면
`78.4123`처럼 없는 정밀도가 실린다.

**status는 반올림한 값으로 판정한다.** 원값으로 판정하고 반올림한 값을 보내면, 보낸 숫자로는
`good`인데 뱃지는 `warn`인 경우가 생긴다. 화면에 실린 숫자와 판정이 어긋나면 안 된다.

앱의 표시 자릿수는 값의 역할에 따라 다르다.

| 대상 | 표시 | 이유 |
|---|---|---|
| `userValue` / `proValue` | 정수 (`78°`) | 절대 각도는 1도 아래가 노이즈다 |
| `difference` / `threshold` | 소수 첫째 자리 (`6.5°`, `±15.0°`) | 판정이 걸리는 값이다 |

차이를 정수로 줄이면 `15.4°`가 `15°`가 되어 `허용 15°`와 같아 보이는데 뱃지는 '주의'인
구간이 생긴다. 게이지 마커는 띠 밖에 있고 문구는 같다고 말하는, 앞뒤가 맞지 않는 화면이
된다. 차이만 한 자리를 유지하면 이 구간이 사라진다.

기존 8개 항목에도 `"unit": null`을 명시적으로 싣는다. 필드가 있다 없다 하는 것보다
항상 있는 편이 앱에서 다루기 쉽다.

### status 판정

각도는 `favorableDirection`이 **전부 `null`** 이다. 굽힘각도 암슬롯도 "클수록 유리"가
성립하지 않는다. 따라서 각도 지표는 `favorable` 판정이 나오지 않고 `good` / `warn` /
`unavailable` 셋뿐이다.

```
필요한 점 중 하나라도 얻지 못함 / 퇴화 케이스  → unavailable  (값은 모두 null)
|difference| <= threshold                      → good
그 외                                           → warn
```

필요한 점은 굽힘각이 세 개(어깨·팔꿈치·손목), 암슬롯이 두 개(어깨·팔꿈치)다.
신뢰도 게이팅은 `point_at_frame`이 관절마다 이미 하고 있으므로, 가려진 관절이 하나라도
있으면 그 점이 `None`으로 돌아와 자연스럽게 `unavailable`이 된다.

각도 평가 경로는 `is_favorable`을 호출하지 않는다. 호출해도 `None`이라 항상 `False`가
나오지만, 부르지 않는 편이 "각도에는 유리한 방향이 없다"는 사실을 코드에 남긴다.

### 프레임

세 점을 모두 같은 프레임(`phase_frame(phases, phase, percent)`의 결과)에서 뽑으므로
`userFrame`/`proFrame`은 그 프레임 하나다. 기존 축 지표가 점의 프레임을 그대로 쓰는 것과
결과적으로 같다.

## 저장소별 변경

### 1. analysis (분석 서버)

**새 모듈 `service/server/analysis/joint_angles.py`**

- 순수 함수 `elbow_flexion_degrees(shoulder, elbow, wrist) -> float | None`,
  `arm_slot_degrees(shoulder, elbow) -> float | None`
- `AngleRule` 데이터클래스와 규칙 테이블 `ANGLE_RULES`(위 표 8개)

```python
@dataclass(frozen=True)
class AngleRule:
    phase: str
    kind: str          # "elbow_flexion" | "arm_slot"
    percent: float
    threshold: float
    category: str
    metric_label: str
    why: str
```

관절 역할은 `kind`가 정한다. 굽힘각은 `throwing_shoulder`/`throwing_elbow`/`throwing_wrist`,
암슬롯은 `throwing_shoulder`/`throwing_elbow`를 쓴다.

**`coaching_feedback_utils.joint_name`에 `throwing_shoulder` 역할 추가.** 현재 매핑에
어깨가 없어서(`throwing_wrist`, `throwing_elbow`, `stride_knee`, `stride_foot`만 있다)
그대로 두면 `"throwing_shoulder"`가 컬럼 이름으로 그대로 새어 나가 조회에 실패한다.

**`phase_metrics.py`**

- 기존 축 지표 평가 결과에 `"unit": None`을 추가한다.
- `ANGLE_RULES` 평가 결과를 이어붙인다. 반환은 `axis 8개 + angle 8개 = 16개`.
- 각도 평가는 별도 함수 `_evaluate_angle`로 둔다. `_evaluate`와 분기로 섞지 않는다 —
  규칙 타입이 다르고 status 규칙도 다르다.

순서는 `AXIS_RULES` 순서 뒤에 `ANGLE_RULES` 순서다. 앱이 구간별로 다시 묶으므로
(`groupMetricsByPhase`) 화면에서는 각 구간 안에서 기존 지표가 먼저, 각도가 뒤에 온다.

`key`는 16개 전부 고유하다. 앱이 이 값을 리스트 렌더 key로 쓰므로 중복되면 안 된다.

### 2. backend (Spring)

`PhaseMetricDto`에 `unit: String? = null` 한 줄. Jackson 3는 DTO에 선언되지 않은 필드를
조용히 버리므로, 이것이 없으면 분석 서버가 보낸 `unit`이 앱까지 도달하지 못한다.

그 외 변경 없음.

### 3. Frontend (앱)

- `analysisApi.ts`: `PhaseMetricDetail.unit?: string | null`
- `report.types.ts`: `PhaseMetric.unit: string | null`
- `mapReport.ts`: `unit`을 그대로 옮긴다
- 새 포맷 함수 두 개 (`PhaseMetricRow.tsx` 안에 둔다). 절대값과 판정값의 자릿수가 다르므로
  하나로 합치지 않는다:

```
formatValue(value, unit)      → unit === 'degree' ? `${Math.round(value)}°`   : value.toFixed(2)
formatJudgment(value, unit)   → unit === 'degree' ? `${value.toFixed(1)}°`    : value.toFixed(2)
```

- `PhaseMetricRow`: 값 줄은 `formatValue`(`나 78° · 기준 72°`), 차이 줄과 게이지 캡션은
  `formatJudgment`(`기준보다 6.5° 큼 · 허용 ±15.0°`).
- `describeDifference`는 단위를 받아야 한다. "차이 없음" 판정도 단위별로 다르다 — 각도는
  `toFixed(1)`이 `0.0`일 때, 좌표는 지금처럼 `toFixed(2)`가 `0.00`일 때다. 판정에 쓰는
  자릿수와 표시에 쓰는 자릿수가 같아야 "기준보다 0.0° 큼" 같은 문구가 나오지 않는다.

**게이지 기하는 바꾸지 않는다.** 축척이 `|difference|`와 `threshold`의 비율만 쓰므로
단위와 무관하게 그대로 동작한다.

`unit`이 `"degree"`도 `null`도 아닌 값이 오면(향후 추가) 좌표 표기로 폴백한다. 화면이
죽지 않는 것이 우선이다.

## 알려진 한계

**단일 카메라의 2D 투영각이다.** 팔이 카메라 쪽으로 오거나 멀어지면 실제보다 짧게 찍혀
각도가 왜곡된다. 3D 자세 추정 없이는 계산으로 고칠 수 없다.

따라서 **각도는 프로 비교보다 최고의 1구 비교에서 더 믿을 만하다.** 최고의 1구는 사용자가
같은 자리에서 찍은 영상이라 왜곡이 양쪽에 비슷하게 걸려 상당 부분 상쇄되지만, 캐시된 프로
영상은 촬영 각도가 달라 상쇄되지 않는다.

이번에는 프로 비교에서도 각도를 **막지 않는다.** 값이 무의미하지는 않고, 막으면 "왜 여기만
지표가 적은가"라는 또 다른 혼란이 생긴다. 실기기에서 프로 비교 각도가 계통적으로 치우치는
것이 확인되면 그때 규칙 테이블에 모드 조건을 한 줄 더하면 된다.

## 하위 호환과 배포 순서

배포 순서에 제약이 없다.

- 분석 서버를 먼저 올리면: 백엔드가 `unit`을 모르고 버린다. 각도 지표는 도달하되 `unit`이
  없어 앱이 좌표 표기로 폴백한다 — `78.40`으로 보인다. 잘못됐지만 깨지지는 않는다.
- 백엔드를 먼저 올리면: `unit`이 `null`이다. 기존과 동일하게 동작한다.
- 앱이 먼저 올라가면: `unit`이 `undefined`라 좌표 표기. 각도 자체가 없으므로 문제없다.

세 저장소를 함께 올리는 것이 맞고, 순서를 지키지 못해도 화면이 깨지지 않는다.

## 검증

- **분석 서버**: `service/server/.venv`에 pytest가 없다. 기존 `test_phase_metrics.py`와 같은
  방식으로 `python`이 바로 실행하는 단독 스크립트 `test_joint_angles.py`를 쓴다.
  - 3-4-5 직각삼각형에서 90°가 나오는가
  - **같은 자세를 회전·확대·좌우반전해도 각도가 같은가** — 정규화 무관성이 이 설계의
    근거이므로 반드시 검증한다
  - 세 점 중 하나가 신뢰도 미달이면 `unavailable`이고 값이 `null`인가
  - 퇴화 케이스(관절이 겹침)에서 `unavailable`인가
  - 임계 경계에서 good/warn이 갈리는가 (15.0° → good, 15.1° → warn)
  - **판정이 반올림한 값과 일치하는가** — 원값 15.04°는 반올림하면 15.0°이므로 `good`이어야
    한다. 원값으로 판정하면 `warn`이 나와 화면의 숫자와 뱃지가 어긋난다
  - `unit`이 각도는 `"degree"`, 기존 8개는 `None`인가
  - **회귀: 기존 8개의 값과 판정이 그대로인가**
- **backend**: `./gradlew cleanTest test` — 기존 41개 통과 + `unit` 왕복 직렬화 테스트 추가
- **Frontend**: `npx tsc --noEmit`, `npx expo export --platform android`
- **실기기**: 분석 서버·백엔드·DB가 모두 떠 있어야 실제 각도를 볼 수 있다. 사용자 확인이
  필요하다.

## 열린 항목

- 임계값 15°/10°는 실기기에서 조정할 값이다. 대부분의 투구가 `warn`으로 뜨거나 반대로
  전부 `good`으로 뜨면 값이 틀린 것이다.
- 각도가 붙으면 구간당 지표가 3~4개가 된다. 이전 스펙의 열린 항목이던 "펼친 패널이 얇다"가
  함께 해소되는지 실기기에서 확인한다.
- 데이터 기반 임계값(사용자 과거 기록의 분산)은 별도 건으로 남긴다.
