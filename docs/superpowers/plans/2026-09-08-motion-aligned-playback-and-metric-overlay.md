# 동작 정렬 재생과 지표 시각화 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 비교 스켈레톤을 점수와 같은 기준(구간 진행률)으로 정렬해 재생하고, 지표가 어느 관절을 어떻게 재는지 스켈레톤 위에 그린다.

**Architecture:** Part 1은 앱이 이미 받고 있으나 버리던 구간 경계로 사용자 프레임 → 비교 프레임 대응을 만든다(서버 변경 없음). Part 2는 서버가 이미 알고 있으나 보내지 않던 관절 이름을 계약에 실어, 앱이 그 관절과 각도를 스켈레톤 위에 그린다.

**Tech Stack:** Python 3 + pandas (분석 서버), Kotlin + Spring Boot 4 + Jackson 3 (백엔드), TypeScript + React Native/Expo + react-native-svg (앱)

**Spec:** `docs/superpowers/specs/2026-09-08-motion-aligned-playback-and-metric-overlay-design.md` (분석 서버 저장소 기준)

## Global Constraints

- 저장소 3개는 서로 다른 디렉터리다. **각 태스크의 `cd` 대상을 반드시 확인할 것.**
  - 분석 서버: `C:\Capstone\analysis\Analysis_algorithm`
  - 백엔드: `C:\Capstone\untitled\backend`
  - 앱: `C:\Capstone\Frontend`
- **시작 전 정리 필요:** 분석 서버에 커밋되지 않은 변경이 있다 — `metric_tolerance.py`, `test_metric_tolerance.py`(신규), `phase_metrics.py`(수정). **Task 1이 `phase_metrics.py`를 건드리므로 시작 전에 커밋하거나 stash해야 한다.** 테스트를 통과하고 제품에 연결되지 않은 상태이므로 커밋을 권한다.
- **분석 알고리즘을 바꾸지 않는다.** 구간 검출·지표 계산·임계값은 그대로다. 이 작업은 이미 계산된 것을 정확히 보여주는 데까지다.
- **판정(양호/주의) 표기를 바꾸지 않는다.** 별도 논의가 진행 중이다.
- **앱이 각도를 다시 계산하지 않는다.** 서버가 보낸 `userValue`/`proValue`를 라벨로 쓴다. 앱이 자체 계산을 갖게 되면 서버와 다른 값을 낼 수 있다.
- **관절 이름은 서버가 정한다.** 투구 팔이 어느 쪽인지는 `throwing_side`로 서버가 판단한다. 앱이 `key`로 유추하면 안 된다.
- `userJoints`와 `proJoints`는 **길이와 순서가 항상 같다.** 손잡이가 달라 이름만 다르다.
- 배열 길이가 기하를 정한다: **1 = 강조만, 2 = 몸통축 대비 각, 3 = 가운데가 꼭짓점인 사이각.**
- 분석 서버 venv에 **pytest가 없다.** 아래 러너 명령을 쓴다. pytest를 설치하지 마라.
- 앱 저장소는 전체가 CRLF라 `eslint`가 수천 건 노이즈를 낸다. **게이트는 `npx tsc --noEmit`과 `npx expo export --platform android`다.**
- **앱에서 `git add .`을 절대 쓰지 마라.** `app.json`, `eas.json`(사용자 편집), `.env.backup-cloudrun`(**비밀값, .gitignore에 없음**)이 더티 상태다. 파일을 명시해 add하고, 커밋 후 `git status --short`로 이 셋이 남아 있는지 확인할 것.
- 커밋 메시지는 `git commit -m "..."` 한 줄. **PowerShell here-string(`@'...'@`)을 bash에서 쓰지 마라.**
- 파일은 UTF-8로 쓴다. 콘솔에서 한글이 깨져 보이는 것은 정상이다.

---

### Task 1: 분석 서버 — 측정에 쓴 관절 이름 내보내기

**Files:**
- Modify: `service/server/analysis/phase_metrics.py`
- Test: `service/server/analysis/test_phase_metrics.py`

**Interfaces:**
- Consumes: 기존 `joint_name(table, role) -> str`, `AxisRule.joint_role`, `AngleRule.kind`, 상수 `ARM_SLOT`
- Produces:
  - `joints_for_axis_rule(pose: pd.DataFrame, rule: AxisRule) -> list[str]`
  - `joints_for_angle_rule(pose: pd.DataFrame, rule: AngleRule) -> list[str]`
  - `build_phase_metrics(...)`의 각 항목에 `"userJoints"`, `"proJoints"` 키가 생긴다

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`service/server/analysis/test_phase_metrics.py` **맨 끝에** 덧붙인다:

```python
def _left_handed_pose(knee_y: float) -> pd.DataFrame:
    """좌완 포즈. joint_name()이 throwing_side 컬럼을 읽어 left_* 를 고르게 한다."""
    pose = _pose(knee_y)
    pose["throwing_side"] = "left"
    pose["stride_side"] = "right"
    return pose


def test_axis_metric_reports_one_joint() -> None:
    metrics = build_phase_metrics(_pose(0.5), _pose(0.5), _phases(), _phases())
    knee = next(m for m in metrics if m["key"] == "leg_lift_knee_height")
    assert knee["userJoints"] == ["left_knee"]
    assert knee["proJoints"] == ["left_knee"]


def test_arm_slot_reports_shoulder_and_elbow() -> None:
    metrics = build_phase_metrics(_pose(0.5), _pose(0.5), _phases(), _phases())
    slot = next(m for m in metrics if m["key"] == "stride_arm_slot")
    assert slot["userJoints"] == ["right_shoulder", "right_elbow"]


def test_elbow_flexion_puts_the_vertex_in_the_middle() -> None:
    """가운데가 꼭짓점이다. 순서가 바뀌면 앱이 엉뚱한 각을 그린다."""
    metrics = build_phase_metrics(_pose(0.5), _pose(0.5), _phases(), _phases())
    flexion = next(m for m in metrics if m["key"] == "stride_elbow_flexion")
    assert flexion["userJoints"] == ["right_shoulder", "right_elbow", "right_wrist"]


def test_each_side_is_resolved_separately() -> None:
    """우완 사용자가 좌완과 비교하면 양쪽이 서로 다른 팔을 잰다."""
    metrics = build_phase_metrics(
        _pose(0.5), _left_handed_pose(0.5), _phases(), _phases()
    )
    slot = next(m for m in metrics if m["key"] == "acceleration_arm_slot")
    assert slot["userJoints"] == ["right_shoulder", "right_elbow"]
    assert slot["proJoints"] == ["left_shoulder", "left_elbow"]


def test_joints_are_present_even_when_unavailable() -> None:
    """값을 못 구해도 어느 관절을 보려 했는지는 알려준다."""
    empty = pd.DataFrame([{"frame_index": float(f)} for f in range(0, 51)])
    metrics = build_phase_metrics(empty, empty, _phases(), _phases())
    assert all(m["userJoints"] and m["proJoints"] for m in metrics)


def test_both_sides_have_the_same_shape() -> None:
    metrics = build_phase_metrics(
        _pose(0.5), _left_handed_pose(0.5), _phases(), _phases()
    )
    assert all(len(m["userJoints"]) == len(m["proJoints"]) for m in metrics)
```

- [ ] **Step 2: 실패를 확인한다**

```bash
cd C:/Capstone/analysis/Analysis_algorithm/service/server && PYTHONPATH="analysis" ./.venv/Scripts/python.exe -c "import analysis.test_phase_metrics as m; m.test_axis_metric_reports_one_joint()"
```

Expected: `KeyError: 'userJoints'`

- [ ] **Step 3: 관절 이름 헬퍼를 추가한다**

`phase_metrics.py`의 `axis_value_at_phase` 정의 **바로 위에** 덧붙인다:

```python
def joints_for_axis_rule(pose: pd.DataFrame, rule: AxisRule) -> list[str]:
    """이 축 규칙이 보는 관절 이름. 손잡이가 이미 해소된 실제 컬럼 이름이다."""
    return [joint_name(pose, rule.joint_role)]


def joints_for_angle_rule(pose: pd.DataFrame, rule: AngleRule) -> list[str]:
    """이 각도 규칙이 보는 관절 이름.

    순서가 의미를 갖는다 — 굽힘각은 가운데(팔꿈치)가 꼭짓점이다. 앱은 이 순서로
    각을 그리므로 바꾸면 엉뚱한 각이 그려진다.
    """
    names = [joint_name(pose, "throwing_shoulder"), joint_name(pose, "throwing_elbow")]
    if rule.kind != ARM_SLOT:
        names.append(joint_name(pose, "throwing_wrist"))
    return names
```

- [ ] **Step 4: 두 평가 함수의 base에 싣는다**

`_evaluate`의 `base` 딕셔너리에서 `"why": rule.why,` 다음 줄에 넣는다:

```python
        "why": rule.why,
        "userJoints": joints_for_axis_rule(user_pose, rule),
        "proJoints": joints_for_axis_rule(pro_pose, rule),
```

`_evaluate_angle`의 `base` 딕셔너리에서도 `"why": rule.why,` 다음 줄에 넣는다:

```python
        "why": rule.why,
        "userJoints": joints_for_angle_rule(user_pose, rule),
        "proJoints": joints_for_angle_rule(pro_pose, rule),
```

- [ ] **Step 5: 통과와 회귀를 확인한다**

```bash
cd C:/Capstone/analysis/Analysis_algorithm/service/server && PYTHONPATH="analysis" ./.venv/Scripts/python.exe -c "
import importlib
total=0; failed=[]
for name in ('analysis.test_coaching_feedback','analysis.test_normalization_body_scale','analysis.test_phase_stride_contact','analysis.test_pose_coordinates','analysis.test_similarity_scoring_scale','analysis.test_joint_angles','analysis.test_phase_metrics','analysis.test_limb_consistency','test_app_response_shape'):
    m=importlib.import_module(name)
    for n,f in [(n,f) for n,f in vars(m).items() if n.startswith('test_')]:
        try: f(); total+=1
        except Exception as e: failed.append(f'{name}.{n}: {type(e).__name__} {e}')
print('PASS', total, '| FAIL', len(failed))
for f in failed: print(' ', f)
"
```

Expected: `FAIL 0`

- [ ] **Step 6: 응답 조립이 새 필드를 버리지 않는지 확인한다**

`app.py`의 `PUBLIC_PHASE_METRIC_FIELDS`가 화이트리스트다. 목록에 없는 키는 조용히 사라진다. `"why",` 다음 줄에 두 개를 넣는다:

```python
    "why",
    "userJoints",
    "proJoints",
    "userFrame",
    "proFrame",
)
```

그리고 `test_app_response_shape.py`의 `PHASE_METRIC` 딕셔너리에도 두 키를 넣어(`"why"` 다음), 필드 누락 테스트가 이들을 지키게 한다:

```python
    "why": "암슬롯이 투구마다 흔들리면 릴리즈 포인트가 달라집니다.",
    "userJoints": ["right_shoulder", "right_elbow"],
    "proJoints": ["left_shoulder", "left_elbow"],
    "userFrame": 62,
```

- [ ] **Step 7: 다시 전체 테스트**

Step 5의 명령을 그대로 다시 실행한다.

Expected: `FAIL 0`

- [ ] **Step 8: 커밋**

```bash
cd C:/Capstone/analysis/Analysis_algorithm && git add service/server/analysis/phase_metrics.py service/server/analysis/test_phase_metrics.py service/server/app.py service/server/test_app_response_shape.py && git commit -m "분석: 지표가 측정에 쓴 관절 이름을 함께 내보낸다"
```

---

### Task 2: 백엔드 — 관절 이름 통과

**Files:**
- Modify: `src/main/kotlin/com/capstone/backend/domain/analysis/dto/AnalysisDto.kt`
- Test: `src/test/kotlin/com/capstone/backend/domain/analysis/dto/PhaseMetricPassthroughTest.kt`

**Interfaces:**
- Produces: `PhaseMetricDto.userJoints: List<String>?`, `PhaseMetricDto.proJoints: List<String>?`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`PhaseMetricPassthroughTest.kt`의 `payload` 안 지표 객체에서 `"why"` 줄 다음에 두 줄을 넣는다:

```
              "userJoints": ["right_shoulder", "right_elbow"],
              "proJoints": ["left_shoulder", "left_elbow"],
```

그리고 클래스 **맨 끝에** 덧붙인다:

```kotlin
    @Test
    @DisplayName("측정 관절 이름이 역직렬화된다")
    fun deserializesJoints() {
        val dto = mapper.readValue(payload, PlayerAnalysisDto::class.java)

        val metric = dto.phaseMetrics!!.first()
        assertThat(metric.userJoints).containsExactly("right_shoulder", "right_elbow")
        assertThat(metric.proJoints).containsExactly("left_shoulder", "left_elbow")
    }

    @Test
    @DisplayName("관절 이름이 없는 구버전 응답도 깨지지 않는다")
    fun toleratesMissingJoints() {
        val legacy =
            """
            {
              "analysisId": "a1", "proId": "7", "overallScore": 79.3, "phaseScores": [],
              "phaseMetrics": [
                { "phase": "stride", "key": "stride_foot_width", "label": "디딤발 착지 폭", "status": "good" }
              ]
            }
            """.trimIndent()

        val dto = mapper.readValue(legacy, PlayerAnalysisDto::class.java)

        assertThat(dto.phaseMetrics!!.first().userJoints).isNull()
        assertThat(dto.phaseMetrics!!.first().proJoints).isNull()
    }
```

- [ ] **Step 2: 실패를 확인한다**

```bash
cd C:/Capstone/untitled/backend && ./gradlew test --tests "*PhaseMetricPassthroughTest*" 2>&1 | tail -20
```

Expected: 컴파일 실패 — `unresolved reference: userJoints`

- [ ] **Step 3: DTO에 두 필드를 넣는다**

`AnalysisDto.kt`의 `PhaseMetricDto`에서 `val why: String? = null,` 다음 줄에:

```kotlin
    val why: String? = null,
    /** 이 지표가 측정에 쓴 관절 이름. 손잡이가 서로 다를 수 있어 양쪽을 따로 받는다. */
    val userJoints: List<String>? = null,
    val proJoints: List<String>? = null,
    val userFrame: Double? = null,
```

- [ ] **Step 4: 통과를 확인한다**

```bash
cd C:/Capstone/untitled/backend && ./gradlew cleanTest test 2>&1 | tail -20
```

Expected: `BUILD SUCCESSFUL`

- [ ] **Step 5: 커밋**

```bash
cd C:/Capstone/untitled/backend && git add src/main/kotlin/com/capstone/backend/domain/analysis/dto/AnalysisDto.kt src/test/kotlin/com/capstone/backend/domain/analysis/dto/PhaseMetricPassthroughTest.kt && git commit -m "구간 지표 DTO에 측정 관절 이름 추가"
```

---

### Task 3: 앱 — 동작 정렬 대응 함수

순수 함수만 만든다. 화면 연결은 Task 4다.

**Files:**
- Create: `src/features/report/utils/motionAlign.ts`

**Interfaces:**
- Produces:
  - `PhaseSpan` — `{ userStartFrame: number; userEndFrame: number; proStartFrame: number; proEndFrame: number }`
  - `alignToCompareFrame(userFrame: number, spans: PhaseSpan[]): number | null`

- [ ] **Step 1: 구현을 쓴다**

`src/features/report/utils/motionAlign.ts`를 새로 만든다:

```ts
/**
 * [motionAlign.ts]
 * 사용자 프레임 → 비교 대상 프레임 대응.
 *
 * 점수는 구간 내부를 같은 진행률로 리샘플링해 비교하는데, 화면은 비교 대상을 실제
 * 타이밍으로 흘렸다. 그래서 사용자가 보는 것과 점수가 말하는 것이 다른 기준 위에 있었다.
 * 여기서 점수와 같은 규칙(구간별 선형 대응)을 만든다.
 *
 * 지표의 측정 지점도 같은 규칙으로 뽑히므로, 이 대응을 쓰면 "이 순간 보기"에서 양쪽이
 * 자동으로 실제 측정 순간에 놓인다.
 */

export interface PhaseSpan {
  userStartFrame: number;
  userEndFrame: number;
  proStartFrame: number;
  proEndFrame: number;
}

/**
 * 대응하는 비교 프레임. 대응을 만들 수 없으면 null을 돌려 호출부가 기존 실시간 정렬로
 * 되돌아가게 한다.
 */
export function alignToCompareFrame(userFrame: number, spans: PhaseSpan[]): number | null {
  if (!Number.isFinite(userFrame) || spans.length === 0) {
    return null;
  }

  const first = spans[0];
  if (userFrame <= first.userStartFrame) {
    return first.proStartFrame;
  }
  const last = spans[spans.length - 1];
  if (userFrame >= last.userEndFrame) {
    return last.proEndFrame;
  }

  for (const span of spans) {
    if (userFrame < span.userStartFrame || userFrame > span.userEndFrame) {
      continue;
    }
    const userLength = span.userEndFrame - span.userStartFrame;
    if (userLength <= 0) {
      // 사용자 구간 길이가 0이면 진행률을 정의할 수 없다. 구간 시작으로 보낸다.
      return span.proStartFrame;
    }
    const progress = (userFrame - span.userStartFrame) / userLength;
    // 비교 구간 길이가 0이어도 정상이다 — 그 구간 전체가 한 프레임에 대응된다.
    // 실측에서 가속 구간이 0프레임인 프로가 있었다.
    return span.proStartFrame + (progress * (span.proEndFrame - span.proStartFrame));
  }

  return null;
}
```

- [ ] **Step 2: 검증 스크립트로 확인한다**

```bash
SP="C:/Users/Yun/AppData/Local/Temp/claude/C--Capstone/7c552804-392f-44d1-b747-066c6fcf4a97/scratchpad/align"; cd C:/Capstone/Frontend && npx tsc src/features/report/utils/motionAlign.ts --outDir "$SP" --module commonjs --target es2019 && node -e "
const m=require('$SP/motionAlign.js'); const a=require('assert');
const spans=[
  {userStartFrame:0,   userEndFrame:20,  proStartFrame:0,   proEndFrame:10},
  {userStartFrame:20,  userEndFrame:120, proStartFrame:10,  proEndFrame:60},
  {userStartFrame:120, userEndFrame:140, proStartFrame:60,  proEndFrame:60},
];
a.strictEqual(m.alignToCompareFrame(0,   spans), 0);
a.strictEqual(m.alignToCompareFrame(20,  spans), 10);
a.strictEqual(m.alignToCompareFrame(120, spans), 60);
a.strictEqual(m.alignToCompareFrame(140, spans), 60);
a.strictEqual(m.alignToCompareFrame(10,  spans), 5);
a.strictEqual(m.alignToCompareFrame(70,  spans), 35);
a.strictEqual(m.alignToCompareFrame(130, spans), 60);
a.strictEqual(m.alignToCompareFrame(-5,  spans), 0);
a.strictEqual(m.alignToCompareFrame(999, spans), 60);
a.strictEqual(m.alignToCompareFrame(10,  []), null);
a.strictEqual(m.alignToCompareFrame(NaN, spans), null);
const zero=[{userStartFrame:5,userEndFrame:5,proStartFrame:7,proEndFrame:9}];
a.strictEqual(m.alignToCompareFrame(5, zero), 7);
console.log('ALL PASS 12');
"
```

Expected: `ALL PASS 12`

- [ ] **Step 3: 타입 검사**

```bash
cd C:/Capstone/Frontend && npx tsc --noEmit; echo "EXIT=$?"
```

Expected: `EXIT=0`

- [ ] **Step 4: 커밋**

```bash
cd C:/Capstone/Frontend && git add src/features/report/utils/motionAlign.ts && git commit -m "리포트: 동작 정렬 프레임 대응 함수 추가"
```

---

### Task 4: 앱 — 동작 정렬 재생 연결

**Files:**
- Modify: `src/features/report/types/report.types.ts`
- Modify: `src/features/report/utils/mapReport.ts`
- Modify: `src/features/report/screens/ReportScreen.tsx`
- Modify: `src/features/report/components/SkeletonOverlayPlayer.tsx`

**Interfaces:**
- Consumes: Task 3의 `PhaseSpan`, `alignToCompareFrame`
- Produces: `ReportData.alignmentSpans: PhaseSpan[]`, 플레이어 prop `alignmentSpans?: PhaseSpan[]`

- [ ] **Step 1: 화면 모델에 정렬 구간을 담는다**

`report.types.ts` 상단 import에 추가:

```ts
import { PhaseSpan } from '../utils/motionAlign';
```

`ReportData` 인터페이스에 한 줄을 넣는다(`phaseScores` 다음 줄이 자연스럽다):

```ts
  /** 비교 스켈레톤을 점수와 같은 기준으로 정렬하는 데 쓴다. 없으면 실시간 정렬로 폴백. */
  alignmentSpans: PhaseSpan[];
```

- [ ] **Step 2: 매퍼가 구간 경계를 옮기게 한다**

`mapReport.ts`의 `const phaseScores: PhaseScore[] = ...` **바로 다음에** 추가한다. 백엔드가 이미 네 값을 보내고 있는데 지금까지 버리고 있었다:

```ts
  // 정렬은 점수가 쓰는 것과 같은 구간 경계를 쓴다. 값이 온전한 구간만 담는다 —
  // 하나라도 숫자가 아니면 그 구간에서 대응이 깨진다.
  const alignmentSpans = detail.phaseScores
    .filter(
      (p) =>
        Number.isFinite(p.userStartFrame) &&
        Number.isFinite(p.userEndFrame) &&
        Number.isFinite(p.proStartFrame) &&
        Number.isFinite(p.proEndFrame),
    )
    .map((p) => ({
      userStartFrame: p.userStartFrame,
      userEndFrame: p.userEndFrame,
      proStartFrame: p.proStartFrame,
      proEndFrame: p.proEndFrame,
    }));
```

그리고 이 함수가 만들어 돌려주는 `ReportData` 객체 리터럴에 `alignmentSpans,`를 추가한다(`phaseScores,` 옆).

- [ ] **Step 3: 플레이어에 prop을 넘긴다**

`ReportScreen.tsx`의 `<SkeletonOverlayPlayer ... />`에 한 줄 추가한다(`seekRequest` 옆):

```tsx
              alignmentSpans={currentData.insight.alignmentSpans}
```

같은 파일에서 `<PhaseScoreCard scores={currentData.insight.phaseScores} />`가 쓰는 것과 같은 객체다.

- [ ] **Step 4: 플레이어가 정렬을 쓰게 한다**

`SkeletonOverlayPlayer.tsx` 상단 import에 추가:

```ts
import { PhaseSpan, alignToCompareFrame } from '../utils/motionAlign';
```

`SkeletonOverlayPlayerProps`에 한 줄 추가:

```ts
  /** 구간별 사용자↔비교 프레임 대응. 비면 실시간 정렬로 폴백한다. */
  alignmentSpans?: PhaseSpan[];
```

컴포넌트 인자 목록(`seekRequest,` 옆)에 `alignmentSpans,`를 추가하고, 배속 상태(`const [speedIdx, setSpeedIdx] = useState(0);`) 아래에 모드 상태를 둔다:

```ts
  // 동작 정렬이 기본이다. 점수가 구간 진행률로 비교하므로 화면도 같은 기준을 써야
  // 사용자가 보는 것과 점수가 말하는 것이 일치한다. 실시간은 템포 차이를 보는 용도로 남긴다.
  const [alignMotion, setAlignMotion] = useState(true);
```

기존 `proFrame` 계산(`const proFrame = useMemo<SkeletonFrame | null>(() => {`)의 **본문 맨 앞**에 정렬 경로를 넣는다. 기존 실시간 경로는 그대로 아래에 남긴다:

```ts
    if (proFrames.length === 0) return null;

    // 동작 정렬: 점수와 같은 구간 진행률 대응을 쓴다.
    if (alignMotion && alignmentSpans && alignmentSpans.length > 0 && userFrames.length > 0) {
      const ui = frameIndexAtTime(userFrames, positionSec);
      if (ui >= 0) {
        const aligned = alignToCompareFrame(userFrames[ui].frameIndex, alignmentSpans);
        if (aligned != null) {
          return frameNearestFrameIndex(proFrames, aligned);
        }
      }
    }

    if (proMotionTime && userMotionTime) {
```

`useMemo` 의존성 배열에 `alignMotion`, `alignmentSpans`, `userFrames`를 추가한다.

`frameNearestFrameIndex`가 아직 import되어 있지 않으면 `skeleton` 유틸 import에 추가한다.

- [ ] **Step 5: 토글을 화면에 둔다**

배속 버튼(`cycleSpeed`를 쓰는 `TouchableOpacity`)을 찾아, 그 **옆에** 같은 모양의 버튼을 하나 더 둔다. 라벨은 상태에 따라 `동작 정렬` / `실시간`이다:

```tsx
        <TouchableOpacity
          onPress={() => setAlignMotion((on) => !on)}
          activeOpacity={0.7}
          accessibilityRole="button"
          accessibilityLabel={alignMotion ? '실시간 재생으로 전환' : '동작 정렬 재생으로 전환'}
          className="px-3 py-1.5 rounded-full bg-surface-page border border-border/50"
        >
          <AppText weight="bold" className="text-text-secondary text-xs">
            {alignMotion ? '동작 정렬' : '실시간'}
          </AppText>
        </TouchableOpacity>
```

`isSingleVideo`가 참이면(비교 대상이 없으면) 이 버튼을 그리지 않는다 — 정렬할 상대가 없다.

- [ ] **Step 6: 게이트 통과를 확인한다**

```bash
cd C:/Capstone/Frontend && npx tsc --noEmit; echo "tsc EXIT=$?"
```

Expected: `EXIT=0`

```bash
cd C:/Capstone/Frontend && npx expo export --platform android 2>&1 | tail -4; echo "EXIT=${PIPESTATUS[0]}"
```

Expected: `Exported: dist`, `EXIT=0`

- [ ] **Step 7: 커밋**

`git add .`을 쓰지 마라.

```bash
cd C:/Capstone/Frontend && git add src/features/report/types/report.types.ts src/features/report/utils/mapReport.ts src/features/report/screens/ReportScreen.tsx src/features/report/components/SkeletonOverlayPlayer.tsx && git commit -m "리포트: 비교 스켈레톤을 점수와 같은 기준으로 정렬해 재생"
```

---

### Task 5: 앱 — 스켈레톤에 측정 관절과 각도 그리기

**Files:**
- Modify: `src/api/analysisApi.ts`
- Modify: `src/features/report/types/report.types.ts`
- Modify: `src/features/report/utils/mapReport.ts`
- Modify: `src/features/report/components/SkeletonOverlayPlayer.tsx` (`SkeletonSvg`)

**Interfaces:**
- Produces:
  - `PhaseMetric.userJoints: string[]`, `PhaseMetric.proJoints: string[]`
  - `SkeletonSvg`의 새 prop `highlight?: { joints: string[]; label: string | null } | null`

- [ ] **Step 1: 관절 이름을 화면까지 흘린다**

`analysisApi.ts`의 `PhaseMetricDetail`에서 `why: string | null;` 다음 줄에:

```ts
  /** 이 지표가 측정에 쓴 관절. 길이 1=강조만, 2=몸통축 대비 각, 3=가운데가 꼭짓점인 각. */
  userJoints?: string[] | null;
  proJoints?: string[] | null;
```

`report.types.ts`의 `PhaseMetric`에서 `why: string | null;` 다음 줄에:

```ts
  userJoints: string[];
  proJoints: string[];
  /** 비교 대상 쪽 측정 프레임. 실시간 모드에서 비교 스켈레톤을 여기에 고정한다. */
  proFrame: number | null;
```

`mapReport.ts`의 `groupMetricsByPhase` 안 `list.push({ ... })`에서 `why: m.why,` 다음 줄에:

```ts
      userJoints: m.userJoints ?? [],
      proJoints: m.proJoints ?? [],
      proFrame: m.proFrame,
```

- [ ] **Step 2: 각도 호를 그리는 순수 헬퍼를 만든다**

`SkeletonOverlayPlayer.tsx`의 `SkeletonSvg` 정의 **바로 위에** 넣는다:

```ts
const HIGHLIGHT_COLOR = '#F59E0B';

/** 화면 좌표(y가 아래로 증가)에서 두 각 사이의 작은 쪽 호. */
function arcPath(cx: number, cy: number, r: number, a0: number, a1: number): string {
  const x0 = cx + (r * Math.cos(a0));
  const y0 = cy + (r * Math.sin(a0));
  const x1 = cx + (r * Math.cos(a1));
  const y1 = cy + (r * Math.sin(a1));
  let delta = a1 - a0;
  while (delta <= -Math.PI) delta += 2 * Math.PI;
  while (delta > Math.PI) delta -= 2 * Math.PI;
  return `M ${x0} ${y0} A ${r} ${r} 0 0 ${delta > 0 ? 1 : 0} ${x1} ${y1}`;
}
```

- [ ] **Step 3: `SkeletonSvg`가 강조와 기하를 그리게 한다**

`SkeletonSvg`의 props에 `highlight`를 추가하고, 기존 관절 원을 그리는 `SKELETON_JOINTS.map(...)` **다음에** 아래 블록을 넣는다. `G`, `Path`, `Text`를 `react-native-svg` import에 추가해야 한다. 프래그먼트(`<>`) 대신 `G`를 쓰는 이유는 react-native-svg가 자식으로 SVG 요소를 기대하기 때문이다:

```tsx
      {(() => {
        const joints = highlight?.joints ?? [];
        if (joints.length === 0) return null;
        if (!joints.every(isVisible)) {
          // 반쯤 그린 그림은 잘못된 각도로 읽힌다. 아무것도 안 그리는 대신 이유를 말한다.
          return (
            <Text x={boxW / 2} y={24} fill={HIGHLIGHT_COLOR} fontSize={12} textAnchor="middle">
              관절이 가려져 표시할 수 없어요
            </Text>
          );
        }
        const pts = joints.map((j) => map(frame.points[j].x, frame.points[j].y));

        // 길이 1은 강조만. 각도 기하가 없다.
        if (pts.length === 1) {
          return <Circle cx={pts[0].px} cy={pts[0].py} r={7} fill={HIGHLIGHT_COLOR} />;
        }

        // 길이 2 = 몸통축 대비 각(암슬롯): 꼭짓점은 어깨, 기준은 몸통축 방향.
        // 길이 3 = 사이각(굽힘각): 꼭짓점은 가운데.
        let vertex = pts[1];
        let rayA = pts[0];
        let rayB = pts[2];
        let axisEnd: { px: number; py: number } | null = null;
        if (pts.length === 2) {
          vertex = pts[0];
          rayA = pts[1];
          const hipMid = midOf('left_hip', 'right_hip');
          const shoulderMid = midOf('left_shoulder', 'right_shoulder');
          if (!hipMid || !shoulderMid) return null;
          const dx = shoulderMid.px - hipMid.px;
          const dy = shoulderMid.py - hipMid.py;
          const len = Math.hypot(dx, dy) || 1;
          axisEnd = { px: vertex.px + ((dx / len) * 60), py: vertex.py + ((dy / len) * 60) };
          rayB = axisEnd;
        }

        const a0 = Math.atan2(rayA.py - vertex.py, rayA.px - vertex.px);
        const a1 = Math.atan2(rayB.py - vertex.py, rayB.px - vertex.px);
        let mid = (a0 + a1) / 2;
        if (Math.abs(a1 - a0) > Math.PI) mid += Math.PI;

        return (
          <G>
            <Line
              x1={vertex.px} y1={vertex.py} x2={rayA.px} y2={rayA.py}
              stroke={HIGHLIGHT_COLOR} strokeWidth={4} strokeLinecap="round"
            />
            <Line
              x1={vertex.px} y1={vertex.py} x2={rayB.px} y2={rayB.py}
              stroke={HIGHLIGHT_COLOR} strokeWidth={axisEnd ? 2 : 4}
              strokeDasharray={axisEnd ? '5,4' : undefined} strokeLinecap="round"
            />
            <Path d={arcPath(vertex.px, vertex.py, 24, a0, a1)} stroke={HIGHLIGHT_COLOR} strokeWidth={2} fill="none" />
            {pts.map((p, i) => (
              <Circle key={`h${i}`} cx={p.px} cy={p.py} r={6} fill={HIGHLIGHT_COLOR} />
            ))}
            {highlight?.label ? (
              <Text
                x={vertex.px + (Math.cos(mid) * 40)}
                y={vertex.py + (Math.sin(mid) * 40)}
                fill={HIGHLIGHT_COLOR}
                fontSize={14}
                fontWeight="bold"
                textAnchor="middle"
              >
                {highlight.label}
              </Text>
            ) : null}
          </G>
        );
      })()}
```

같은 컴포넌트 안, `isVisible` 정의 다음에 중점 헬퍼를 둔다:

```ts
  const midOf = (a: string, b: string) => {
    if (!isVisible(a) || !isVisible(b)) return null;
    const pa = map(frame.points[a].x, frame.points[a].y);
    const pb = map(frame.points[b].x, frame.points[b].y);
    return { px: (pa.px + pb.px) / 2, py: (pa.py + pb.py) / 2 };
  };
```

- [ ] **Step 4: 게이트 통과를 확인한다**

```bash
cd C:/Capstone/Frontend && npx tsc --noEmit; echo "tsc EXIT=$?"
```

Expected: `EXIT=0`

```bash
cd C:/Capstone/Frontend && npx expo export --platform android 2>&1 | tail -4; echo "EXIT=${PIPESTATUS[0]}"
```

Expected: `Exported: dist`, `EXIT=0`

- [ ] **Step 5: 커밋**

```bash
cd C:/Capstone/Frontend && git add src/api/analysisApi.ts src/features/report/types/report.types.ts src/features/report/utils/mapReport.ts src/features/report/components/SkeletonOverlayPlayer.tsx && git commit -m "리포트: 스켈레톤에 측정 관절과 각도를 그린다"
```

---

### Task 6: 앱 — "이 순간 보기"가 강조를 켜게 한다

**Files:**
- Modify: `src/features/report/components/PhaseMetricRow.tsx`
- Modify: `src/features/report/components/PhaseFeedback.tsx`
- Modify: `src/features/report/screens/ReportScreen.tsx`
- Modify: `src/features/report/components/SkeletonOverlayPlayer.tsx`

**Interfaces:**
- Consumes: Task 5의 `SkeletonSvg` `highlight` prop, `PhaseMetric.userJoints`/`proJoints`
- Produces: 플레이어 prop `focus?: MetricFocus`, 타입 `MetricFocus = { userJoints: string[]; proJoints: string[]; userLabel: string | null; proLabel: string | null; proFrame: number | null; nonce: number }`

- [ ] **Step 1: 지표 행이 지표 정보를 함께 올려보낸다**

`PhaseMetricRow.tsx`의 props에서 `onSeekFrame`의 시그니처를 바꾼다:

```ts
  /** 지표가 측정된 순간으로 이동하고 그 측정을 스켈레톤에 표시한다. */
  onSeekFrame?: (frame: number, metric: PhaseMetric) => void;
```

호출부도 함께 바꾼다:

```tsx
          onPress={() => onSeekFrame?.(metric.userFrame as number, metric)}
```

`PhaseFeedback.tsx`의 `PhaseFeedbackProps`에서도 같은 시그니처로 바꾼다:

```ts
  onSeekFrame?: (frame: number, metric: PhaseMetric) => void;
```

`PhaseMetric` 타입 import가 없으면 추가한다.

- [ ] **Step 2: 리포트 화면이 포커스를 만든다**

`ReportScreen.tsx`의 `handleSeekFrame`을 바꾼다. 기존에는 프레임만 받았다:

```tsx
  const [focus, setFocus] = useState<{
    userJoints: string[];
    proJoints: string[];
    userLabel: string | null;
    proLabel: string | null;
    proFrame: number | null;
    nonce: number;
  } | null>(null);

  const handleSeekFrame = useCallback((frame: number, metric: PhaseMetric) => {
    setSeekRequest((prev) => ({ frame, nonce: (prev?.nonce ?? 0) + 1 }));
    // 각도는 서버가 보낸 값을 그대로 라벨로 쓴다. 앱이 다시 계산하지 않는다.
    const unitSuffix = metric.unit === 'degree' ? '°' : '';
    setFocus((prev) => ({
      userJoints: metric.userJoints,
      proJoints: metric.proJoints,
      userLabel: metric.userValue != null ? `${Math.round(metric.userValue)}${unitSuffix}` : null,
      proLabel: metric.proValue != null ? `${Math.round(metric.proValue)}${unitSuffix}` : null,
      proFrame: metric.proFrame ?? null,
      nonce: (prev?.nonce ?? 0) + 1,
    }));
    scrollViewRef.current?.scrollTo({ y: 0, animated: true });
  }, []);
```

`PhaseMetric` import를 추가한다. `proFrame`은 Task 5에서 이미 화면 타입까지 흘려놨다.

`<SkeletonOverlayPlayer ... />`에 prop을 넘긴다:

```tsx
              focus={focus ?? undefined}
```

- [ ] **Step 3: 플레이어가 멈추고 양쪽에 그린다**

`SkeletonOverlayPlayer.tsx`의 props에 추가:

```ts
  /** 지표 측정 순간 표시. nonce가 바뀌면 재생을 멈추고 강조를 켠다. */
  focus?: {
    userJoints: string[];
    proJoints: string[];
    userLabel: string | null;
    proLabel: string | null;
    proFrame: number | null;
    nonce: number;
  };
```

컴포넌트 인자에 `focus,`를 추가하고, 활성 포커스를 상태로 둔다:

```ts
  const [activeFocus, setActiveFocus] = useState<typeof focus | null>(null);

  // 포커스 요청이 오면 재생을 멈춘다. 측정 순간을 검증하는 것이 목적이라 흘러가면 안 된다.
  useEffect(() => {
    if (!focus) return;
    setActiveFocus(focus);
    if (hasVideo) videoRef.current?.pauseAsync().catch(() => {});
    setIsPlaying(false);
    // nonce만 본다 — 같은 지표를 다시 눌러도 동작해야 한다
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focus?.nonce]);

  // 다시 재생하면 강조를 끈다. 움직이기 시작하면 그 각도는 더 이상 맞지 않는다.
  useEffect(() => {
    if (isPlaying) setActiveFocus(null);
  }, [isPlaying]);
```

비교 스켈레톤은 포커스 중이고 **실시간 모드일 때만** `proFrame`으로 고정한다. 동작 정렬 모드에서는 대응이 이미 측정 순간을 맞춘다. `proFrame` 계산의 정렬 분기 **앞에** 넣는다:

```ts
    if (activeFocus && !alignMotion && activeFocus.proFrame != null) {
      return frameNearestFrameIndex(proFrames, activeFocus.proFrame);
    }
```

`useMemo` 의존성에 `activeFocus`, `alignMotion`을 포함시킨다.

두 `<SkeletonSvg>`에 각각 넘긴다:

```tsx
              highlight={
                activeFocus
                  ? { joints: activeFocus.userJoints, label: activeFocus.userLabel }
                  : null
              }
```

오른쪽(비교) 쪽은 `proJoints`와 `proLabel`을 쓴다.

- [ ] **Step 4: 게이트 통과를 확인한다**

```bash
cd C:/Capstone/Frontend && npx tsc --noEmit; echo "tsc EXIT=$?"
```

Expected: `EXIT=0`

```bash
cd C:/Capstone/Frontend && npx expo export --platform android 2>&1 | tail -4; echo "EXIT=${PIPESTATUS[0]}"
```

Expected: `Exported: dist`, `EXIT=0`

- [ ] **Step 5: 커밋**

```bash
cd C:/Capstone/Frontend && git add src/features/report/components/PhaseMetricRow.tsx src/features/report/components/PhaseFeedback.tsx src/features/report/screens/ReportScreen.tsx src/features/report/components/SkeletonOverlayPlayer.tsx src/features/report/types/report.types.ts src/features/report/utils/mapReport.ts && git commit -m "리포트: 이 순간 보기가 측정 관절과 각도를 표시한다"
```

---

## 완료 후 남는 일

- **실기기 확인이 이 작업의 목적이다.** 프로 6명의 `stride_arm_slot`을 각각 열어 48°와 167°가 실제로 다른 자세인지 본다. 다양성이면 판정(양호/주의) 표기를 걷어내는 쪽으로, 검출 오차면 구간 검출을 고치는 쪽으로 간다.
- 서버를 켤 때 `PRO_SKELETON_DATA_URL`이 필요하다. 백엔드가 먼저 떠 있어야 한다.
- 폰이 안 열리면 `adb reverse --list`를 먼저 확인한다.
- 축 지표(길이 1)는 강조만 하고 기하를 그리지 않는다. 필요하면 별건으로 다룬다.
