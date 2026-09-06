# 구간별 상세 지표(phaseMetrics) 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 리포트의 구간별 피드백에 "어느 프레임의 문제인지"와 "임계 대비 얼마나 차이 나는지"를 구조화된 지표로 전달해, 사용자가 구간을 펼쳐 점검표처럼 확인하고 그 순간으로 이동할 수 있게 한다.

**Architecture:** 분석 서버가 `AXIS_RULES` 8개를 임계 초과 여부와 무관하게 항상 평가해 `phaseMetrics` 배열로 응답에 더한다. 백엔드는 DTO에 필드를 추가해 통과시키고, 앱은 구간별로 묶어 접기 패널로 보여준다. 기존 문장 생성 로직과 화면은 건드리지 않는 **추가 변경**이라 배포 순서에 제약이 없다.

**Tech Stack:** Python 3 + pandas (분석 서버) / Kotlin + Spring Boot 4 + Jackson 3 (백엔드) / React Native + TypeScript + NativeWind (앱)

**Spec:** `docs/superpowers/specs/2026-09-06-phase-metrics-design.md`

## Global Constraints

- 저장소 경로: 분석 서버 `C:\Capstone\analysis\Analysis_algorithm`, 백엔드 `C:\Capstone\untitled\backend`, 앱 `C:\Capstone\Frontend`
- 분석 서버 파이썬 명령은 **`service/server` 디렉터리에서** `.venv/Scripts/python.exe`로 실행한다. 테스트가 `from analysis.X import Y` 형태로 import 하기 때문이다.
- **`service/server/.venv`에 pytest가 없다. 새 의존성을 설치하지 않는다.** 테스트는 pytest 형식으로 쓰되, 실행은 아래 한 줄로 한다:
  `python -c "from analysis import test_phase_metrics as t; [getattr(t,n)() for n in dir(t) if n.startswith('test_')]; print('ALL PASS')"`
- `userValue`/`proValue`는 body-frame 정규화 좌표로 **단위가 없다.** 앱은 값에 단위를 붙이지 않는다.
- `difference`는 **부호를 유지**한다(`userValue - proValue`). 기존 `evidence.difference`(절댓값)와 다르다.
- `status`는 `good` / `warn` / `favorable` / `unavailable` 네 가지뿐이다.
- `favorable`은 `comparison_mode == "best_pitch"`일 때만 나온다.
- 커밋 메시지는 저장소 컨벤션 `Tag(Scope): 요약`을 따른다. 끝에 `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`를 붙인다.
- 앱 저장소는 전체가 CRLF이고 prettier는 LF를 기대해 `npx eslint`가 5,000건 가까운 노이즈를 낸다. 검증은 `npx tsc --noEmit`(exit 0)을 1차로 쓴다.

---

### Task 1: 유리 방향 판정을 공용 위치로 옮긴다

`build_phase_metrics`와 기존 문장 생성이 "유리한 방향" 판정을 각자 갖게 되면 언젠가 갈라진다. `AxisRule`의 성질이므로 `AxisRule`이 있는 곳으로 옮긴다.

**Files:**
- Modify: `service/server/analysis/coaching_feedback_utils.py`
- Modify: `service/server/analysis/coaching_feedback.py:192-198`
- Test: `service/server/analysis/test_phase_metrics.py` (신규)

**Interfaces:**
- Produces: `is_favorable(rule: AxisRule, diff: float) -> bool` — `coaching_feedback_utils`에서 export

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`service/server/analysis/test_phase_metrics.py` 생성:

```python
from __future__ import annotations

from analysis.coaching_feedback_utils import AxisRule, is_favorable


def _rule(favorable_direction: str | None) -> AxisRule:
    return AxisRule(
        phase="leg_lift",
        joint_role="stride_knee",
        axis="y",
        percent=100.0,
        threshold=0.12,
        category="leg_lift_knee_height",
        metric_label="디딤 무릎 높이",
        positive_message="높다",
        negative_message="낮다",
        why="에너지 축적과 직결됩니다.",
        favorable_direction=favorable_direction,
    )


def test_is_favorable_positive_direction() -> None:
    assert is_favorable(_rule("positive"), 0.2) is True
    assert is_favorable(_rule("positive"), -0.2) is False


def test_is_favorable_negative_direction() -> None:
    assert is_favorable(_rule("negative"), -0.2) is True
    assert is_favorable(_rule("negative"), 0.2) is False


def test_is_favorable_none_direction_is_never_favorable() -> None:
    assert is_favorable(_rule(None), 0.2) is False
    assert is_favorable(_rule(None), -0.2) is False
```

- [ ] **Step 2: 실패를 확인한다**

Run (`service/server`에서):
```
.venv/Scripts/python.exe -c "from analysis import test_phase_metrics as t; [getattr(t,n)() for n in dir(t) if n.startswith('test_')]; print('ALL PASS')"
```
Expected: FAIL — `ImportError: cannot import name 'is_favorable'`

- [ ] **Step 3: 함수를 옮긴다**

`coaching_feedback_utils.py`에 추가(`AxisRule` 정의 아래):

```python
def is_favorable(rule: AxisRule, diff: float) -> bool:
    """이 차이가 '힘 전달' 관점에서 더 유리한 방향인지.

    AxisRule의 성질이므로 규칙 옆에 둔다. 문장 생성과 지표 산출이 각자
    판정을 들고 있으면 언젠가 서로 다른 답을 내게 된다.
    """
    if rule.favorable_direction == "positive":
        return diff > 0
    if rule.favorable_direction == "negative":
        return diff < 0
    return False
```

`coaching_feedback.py`에서 기존 `_is_favorable` 정의(192~198행)를 삭제하고, 상단 import에 `is_favorable`을 더한 뒤 호출부를 `is_favorable(...)`로 바꾼다. **로직은 그대로다.**

- [ ] **Step 4: 통과를 확인한다**

Run: Step 2와 같은 명령
Expected: `ALL PASS`

- [ ] **Step 5: 기존 동작이 깨지지 않았는지 확인한다**

Run (`service/server`에서):
```
.venv/Scripts/python.exe -c "import analysis.coaching_feedback as m; print(len(m.AXIS_RULES))"
```
Expected: `8` (import 오류 없이)

- [ ] **Step 6: 커밋**

```bash
git add service/server/analysis/coaching_feedback_utils.py service/server/analysis/coaching_feedback.py service/server/analysis/test_phase_metrics.py
git commit -m "Refactor(analysis): 유리 방향 판정을 AxisRule 옆으로 이동"
```

---

### Task 2: `build_phase_metrics` 구현

**Files:**
- Create: `service/server/analysis/phase_metrics.py`
- Modify: `service/server/analysis/test_phase_metrics.py`

**Interfaces:**
- Consumes: `is_favorable(rule, diff)` (Task 1)
- Produces: `build_phase_metrics(user_pose: pd.DataFrame, pro_pose: pd.DataFrame, user_phases: Any, pro_phases: Any, comparison_mode: str = "pro") -> list[dict[str, Any]]`

- [ ] **Step 1: 실패하는 테스트를 추가한다**

`test_phase_metrics.py` 끝에 추가:

```python
from types import SimpleNamespace

import pandas as pd

from analysis.phase_metrics import build_phase_metrics


def _phases() -> SimpleNamespace:
    # phase_frame()은 intervals[phase]의 startFrame/endFrame만 본다.
    return SimpleNamespace(
        intervals={
            "windup": {"startFrame": 0, "endFrame": 10, "label": "와인드업"},
            "leg_lift": {"startFrame": 10, "endFrame": 20, "label": "레그 리프트"},
            "stride": {"startFrame": 20, "endFrame": 30, "label": "스트라이드"},
            "acceleration": {"startFrame": 30, "endFrame": 40, "label": "가속"},
            "follow_through": {"startFrame": 40, "endFrame": 50, "label": "팔로스루"},
        }
    )


def _pose(knee_y: float) -> pd.DataFrame:
    """AXIS_RULES가 보는 관절만 채운 최소 포즈 테이블.

    joint_name()은 throwing_side 기본값 right, stride_side 기본값 left를 쓰므로
    right_wrist / right_elbow / left_knee / left_foot_index 가 필요하다.
    """
    joints = ["right_wrist", "right_elbow", "left_knee", "left_foot_index"]
    rows = []
    for frame in range(0, 51):
        row: dict[str, float] = {"frame_index": float(frame)}
        for joint in joints:
            row[f"{joint}_body_x"] = 0.1
            row[f"{joint}_body_y"] = knee_y if joint == "left_knee" else 0.2
            row[f"{joint}_confidence"] = 0.9
        rows.append(row)
    return pd.DataFrame(rows)


def test_every_rule_produces_an_item_even_when_within_threshold() -> None:
    metrics = build_phase_metrics(_pose(0.5), _pose(0.5), _phases(), _phases())
    # 차이가 0이어도 8개 규칙 전부가 항목이 되어야 접었다 펼치는 점검표가 된다.
    assert len(metrics) == 8
    assert {m["status"] for m in metrics} == {"good"}


def test_difference_keeps_sign_and_threshold_decides_status() -> None:
    metrics = build_phase_metrics(_pose(0.9), _pose(0.5), _phases(), _phases())
    knee = next(m for m in metrics if m["key"] == "leg_lift_knee_height")
    assert round(knee["difference"], 4) == 0.4      # 부호 유지: 사용자 - 기준
    assert knee["threshold"] == 0.12
    assert knee["status"] == "warn"                 # pro 모드에선 유리해도 warn


def test_favorable_only_in_best_pitch_mode() -> None:
    metrics = build_phase_metrics(
        _pose(0.9), _pose(0.5), _phases(), _phases(), comparison_mode="best_pitch"
    )
    knee = next(m for m in metrics if m["key"] == "leg_lift_knee_height")
    # 무릎 높이는 favorable_direction="positive" → 더 높은 쪽이 유리
    assert knee["status"] == "favorable"


def test_missing_joint_yields_unavailable_with_null_values() -> None:
    empty = pd.DataFrame([{"frame_index": float(f)} for f in range(0, 51)])
    metrics = build_phase_metrics(empty, empty, _phases(), _phases())
    assert len(metrics) == 8
    assert {m["status"] for m in metrics} == {"unavailable"}
    assert all(m["userValue"] is None and m["difference"] is None for m in metrics)


def test_item_carries_label_why_and_frames() -> None:
    metrics = build_phase_metrics(_pose(0.5), _pose(0.5), _phases(), _phases())
    knee = next(m for m in metrics if m["key"] == "leg_lift_knee_height")
    assert knee["phase"] == "leg_lift"
    assert knee["label"] == "디딤 무릎 높이"
    assert knee["why"]                      # 왜 중요한지가 필드로 온다
    assert knee["userFrame"] == 20          # leg_lift 10~20의 100% 지점
    assert knee["favorableDirection"] == "positive"
```

- [ ] **Step 2: 실패를 확인한다**

Run: Global Constraints의 테스트 명령
Expected: FAIL — `ModuleNotFoundError: No module named 'analysis.phase_metrics'`

- [ ] **Step 3: 모듈을 구현한다**

`service/server/analysis/phase_metrics.py` 생성:

```python
"""구간별 상세 지표.

기존 coaching_feedback은 "임계를 넘은 것"만 문장으로 만든다. 그래서 정상 범위인
지표는 앱까지 도달하지 못하고, 사용자는 "이 구간에 아무것도 안 뜬다"가 잘한 것인지
측정을 못 한 것인지 알 수 없었다.

여기서는 같은 AXIS_RULES를 임계 초과 여부와 무관하게 전부 평가해, 값·임계·판정을
구조화된 형태로 내보낸다. 문장 생성 로직은 건드리지 않는다.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from analysis.coaching_feedback import AXIS_RULES
from analysis.coaching_feedback_utils import (
    AxisRule,
    is_favorable,
    joint_name,
    metric_value,
    point_at_phase,
)

STATUS_GOOD = "good"
STATUS_WARN = "warn"
STATUS_FAVORABLE = "favorable"
STATUS_UNAVAILABLE = "unavailable"


def build_phase_metrics(
    user_pose: pd.DataFrame,
    pro_pose: pd.DataFrame,
    user_phases: Any,
    pro_phases: Any,
    comparison_mode: str = "pro",
) -> list[dict[str, Any]]:
    """AXIS_RULES 전부를 평가해 구간별 지표 목록을 만든다.

    임계를 넘지 않은 지표도 반드시 포함한다. 측정하지 못한 지표는 감추지 않고
    status="unavailable"로 남긴다 — 값이 없는 것과 문제가 없는 것은 다른 의미다.
    """
    return [_evaluate(rule, user_pose, pro_pose, user_phases, pro_phases, comparison_mode) for rule in AXIS_RULES]


def _evaluate(
    rule: AxisRule,
    user_pose: pd.DataFrame,
    pro_pose: pd.DataFrame,
    user_phases: Any,
    pro_phases: Any,
    comparison_mode: str,
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "phase": rule.phase,
        "key": rule.category,
        "label": rule.metric_label,
        "threshold": round(rule.threshold, 4),
        "favorableDirection": rule.favorable_direction,
        "why": rule.why,
    }

    user_point = point_at_phase(user_pose, user_phases, rule.phase, joint_name(user_pose, rule.joint_role), rule.percent)
    pro_point = point_at_phase(pro_pose, pro_phases, rule.phase, joint_name(pro_pose, rule.joint_role), rule.percent)

    if user_point is None or pro_point is None:
        return {
            **base,
            "userValue": None,
            "proValue": None,
            "difference": None,
            "status": STATUS_UNAVAILABLE,
            "userFrame": None,
            "proFrame": None,
        }

    user_value = metric_value(user_point, rule.axis)
    pro_value = metric_value(pro_point, rule.axis)
    diff = user_value - pro_value

    return {
        **base,
        "userValue": round(user_value, 4),
        "proValue": round(pro_value, 4),
        "difference": round(diff, 4),
        "status": _status(rule, diff, comparison_mode),
        "userFrame": user_point.frame,
        "proFrame": pro_point.frame,
    }


def _status(rule: AxisRule, diff: float, comparison_mode: str) -> str:
    if abs(diff) <= rule.threshold:
        return STATUS_GOOD
    # 프로 비교에서는 유리한 방향의 차이도 "프로와 다른 점"으로 다루는 것이 기존 동작이다
    # (_axis_metric_tips(skip_favorable=is_best_pitch)). 판정을 두 곳에서 다르게 두면
    # 같은 화면에서 앞뒤가 맞지 않는다.
    if comparison_mode == "best_pitch" and is_favorable(rule, diff):
        return STATUS_FAVORABLE
    return STATUS_WARN
```

- [ ] **Step 4: 통과를 확인한다**

Run: Global Constraints의 테스트 명령
Expected: `ALL PASS`

- [ ] **Step 5: 커밋**

```bash
git add service/server/analysis/phase_metrics.py service/server/analysis/test_phase_metrics.py
git commit -m "Feat(analysis): 구간별 상세 지표 산출(build_phase_metrics) 추가"
```

---

### Task 3: 응답에 `phaseMetrics`를 싣는다

**Files:**
- Modify: `service/server/analysis/similarity.py:96-113`

**Interfaces:**
- Consumes: `build_phase_metrics(...)` (Task 2)
- Produces: `/api/analyze` 응답의 각 player 객체에 `phaseMetrics: list[dict]`

- [ ] **Step 1: import 와 호출을 추가한다**

`similarity.py` 상단 import에 추가:

```python
from analysis.phase_metrics import build_phase_metrics
```

`compute_similarity` 안에서 `analysis_feedback = build_analysis_feedback(...)` 호출 **바로 아래**에 추가:

```python
    # 문장(feedback)과 별개로, 구조화된 구간 지표를 함께 내보낸다.
    phase_metrics = build_phase_metrics(
        user_pose.table,
        pro_pose.table,
        user_phases,
        pro_phases,
        comparison_mode=comparison_mode,
    )
```

반환 dict의 `"feedback": analysis_feedback["feedback"],` 바로 아래에 추가:

```python
        "phaseMetrics": phase_metrics,
```

- [ ] **Step 2: 응답 모양을 확인한다**

Run (`service/server`에서):
```
.venv/Scripts/python.exe -c "import inspect, analysis.similarity as s; src=inspect.getsource(s.compute_similarity); assert 'phaseMetrics' in src and 'build_phase_metrics' in src; print('WIRED')"
```
Expected: `WIRED`

- [ ] **Step 3: 기존 테스트가 깨지지 않았는지 확인한다**

Run:
```
.venv/Scripts/python.exe -c "from analysis import test_phase_metrics as t; [getattr(t,n)() for n in dir(t) if n.startswith('test_')]; print('ALL PASS')"
```
Expected: `ALL PASS`

- [ ] **Step 4: 커밋**

```bash
git add service/server/analysis/similarity.py
git commit -m "Feat(analysis): 분석 응답에 phaseMetrics 포함"
```

---

### Task 4: 백엔드가 필드를 버리지 않게 한다

`PlayerAnalysisDto`는 고정 필드만 갖고 있어, DTO에 없는 필드는 역직렬화에서 사라진다. 분석 서버만 고치면 앱까지 도달하지 못한다.

**Files:**
- Modify: `src/main/kotlin/com/capstone/backend/domain/analysis/dto/AnalysisDto.kt:32-39`
- Test: `src/test/kotlin/com/capstone/backend/domain/analysis/dto/PhaseMetricPassthroughTest.kt` (신규)

**Interfaces:**
- Consumes: 분석 서버의 `phaseMetrics` JSON (Task 3)
- Produces: `PlayerAnalysisDto.phaseMetrics: List<PhaseMetricDto>?` — `detailJson` 재직렬화 시 함께 실린다

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`src/test/kotlin/com/capstone/backend/domain/analysis/dto/PhaseMetricPassthroughTest.kt` 생성:

```kotlin
package com.capstone.backend.domain.analysis.dto

import org.assertj.core.api.Assertions.assertThat
import org.junit.jupiter.api.DisplayName
import org.junit.jupiter.api.Test
import tools.jackson.databind.json.JsonMapper
import tools.jackson.module.kotlin.kotlinModule

/**
 * 분석 서버가 보낸 phaseMetrics가 앱까지 살아남는지 확인한다.
 *
 * PlayerAnalysisDto는 고정 필드만 갖는다. 필드를 선언하지 않으면 Jackson이 조용히
 * 버리므로, 분석 서버를 고쳐도 앱에는 아무것도 도달하지 않는다.
 */
class PhaseMetricPassthroughTest {
    private val mapper = JsonMapper.builder().addModule(kotlinModule()).build()

    private val payload =
        """
        {
          "analysisId": "a1",
          "proId": "7",
          "overallScore": 79.3,
          "phaseScores": [],
          "phaseMetrics": [
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
              "why": "에너지 축적과 직결됩니다.",
              "userFrame": 41,
              "proFrame": 38
            }
          ]
        }
        """.trimIndent()

    @Test
    @DisplayName("phaseMetrics가 역직렬화된다")
    fun deserializesPhaseMetrics() {
        val dto = mapper.readValue(payload, PlayerAnalysisDto::class.java)

        assertThat(dto.phaseMetrics).hasSize(1)
        val metric = dto.phaseMetrics!!.first()
        assertThat(metric.key).isEqualTo("leg_lift_knee_height")
        assertThat(metric.status).isEqualTo("good")
        assertThat(metric.difference).isEqualTo(0.07)
        assertThat(metric.userFrame).isEqualTo(41.0)
        assertThat(metric.why).isNotBlank()
    }

    @Test
    @DisplayName("재직렬화해도 phaseMetrics가 살아남는다 — detailJson에 실려야 한다")
    fun survivesReserialization() {
        val dto = mapper.readValue(payload, PlayerAnalysisDto::class.java)

        val json = mapper.writeValueAsString(dto)

        assertThat(json).contains("phaseMetrics")
        assertThat(json).contains("leg_lift_knee_height")
    }

    @Test
    @DisplayName("구버전 분석 서버 응답(phaseMetrics 없음)도 깨지지 않는다")
    fun toleratesMissingPhaseMetrics() {
        val legacy = """{"analysisId":"a1","proId":"7","overallScore":79.3,"phaseScores":[]}"""

        val dto = mapper.readValue(legacy, PlayerAnalysisDto::class.java)

        assertThat(dto.phaseMetrics).isNull()
    }
}
```

- [ ] **Step 2: 실패를 확인한다**

Run (백엔드 루트에서):
```
./gradlew test --tests '*PhaseMetricPassthroughTest*' --console=plain
```
Expected: FAIL — 컴파일 오류 `Unresolved reference 'phaseMetrics'` / `PhaseMetricDto`

- [ ] **Step 3: DTO를 추가한다**

`AnalysisDto.kt`의 `PlayerAnalysisDto`를 다음으로 바꾸고, 그 아래에 `PhaseMetricDto`를 더한다:

```kotlin
data class PlayerAnalysisDto(
    val analysisId: String,
    val proId: String,
    val overallScore: Double,
    val phaseScores: List<PhaseScoreDto>,
    val release: ReleaseDto? = null,
    val feedback: FeedbackDto? = null,
    // 구버전 분석 서버는 이 필드를 보내지 않으므로 nullable 이어야 한다.
    val phaseMetrics: List<PhaseMetricDto>? = null,
)

/**
 * 구간별 상세 지표. 분석 서버가 산출한 값을 그대로 통과시키기 위한 DTO다.
 *
 * 백엔드는 이 값을 해석하지 않는다. 여기에 필드를 선언하는 이유는 오직 하나,
 * 선언하지 않으면 Jackson이 조용히 버려서 앱까지 도달하지 못하기 때문이다.
 */
data class PhaseMetricDto(
    val phase: String,
    val key: String,
    val label: String,
    val userValue: Double? = null,
    val proValue: Double? = null,
    val difference: Double? = null,
    val threshold: Double? = null,
    val status: String,
    val favorableDirection: String? = null,
    val why: String? = null,
    val userFrame: Double? = null,
    val proFrame: Double? = null,
)
```

- [ ] **Step 4: 통과를 확인한다**

Run:
```
./gradlew test --tests '*PhaseMetricPassthroughTest*' --console=plain
```
Expected: `BUILD SUCCESSFUL`

- [ ] **Step 5: 기존 테스트 38개가 그대로인지 확인한다**

Run:
```
./gradlew cleanTest test --console=plain
```
Expected: `BUILD SUCCESSFUL`. 실행된 테스트 수가 38 + 3 = 41 이어야 한다.

- [ ] **Step 6: 커밋**

```bash
git add src/main/kotlin/com/capstone/backend/domain/analysis/dto/AnalysisDto.kt src/test/kotlin/com/capstone/backend/domain/analysis/dto/PhaseMetricPassthroughTest.kt
git commit -m "Feat(api): 분석 상세에 phaseMetrics 통과 필드 추가"
```

---

### Task 5: 앱 타입과 구간별 매핑

**Files:**
- Modify: `src/api/analysisApi.ts:63-82`
- Modify: `src/features/report/types/report.types.ts`
- Modify: `src/features/report/utils/mapReport.ts`

**Interfaces:**
- Consumes: 백엔드 `detailJson`의 `phaseMetrics` (Task 4)
- Produces:
  - `PhaseMetricDetail` (analysisApi.ts)
  - `PhaseMetric` (report.types.ts) — 화면이 쓰는 형태
  - `PhaseFeedback.metrics: PhaseMetric[]` — 구간별로 묶인 지표

- [ ] **Step 1: API 타입을 추가한다**

`src/api/analysisApi.ts`의 `FeedbackDetail` 아래에 추가:

```ts
/** 구간별 상세 지표 (분석 서버 phaseMetrics 원본) */
export interface PhaseMetricDetail {
  phase: string;
  key: string;
  label: string;
  /** body-frame 정규화 좌표. 단위가 없으므로 화면에서 단위를 붙이지 않는다. */
  userValue: number | null;
  proValue: number | null;
  /** userValue - proValue. 부호를 유지한다(evidence.difference는 절댓값이라 다름). */
  difference: number | null;
  threshold: number | null;
  status: 'good' | 'warn' | 'favorable' | 'unavailable';
  favorableDirection: 'positive' | 'negative' | null;
  why: string | null;
  /** 측정이 일어난 프레임. "이 순간 보기"가 쓴다. */
  userFrame: number | null;
  proFrame: number | null;
}
```

같은 파일 `PlayerDetail`에 필드를 더한다:

```ts
  /** 구버전 분석 서버는 보내지 않는다. 없으면 화면이 상세 패널을 그리지 않는다. */
  phaseMetrics?: PhaseMetricDetail[] | null;
```

- [ ] **Step 2: 화면용 타입을 추가한다**

`src/features/report/types/report.types.ts`의 `PhaseFeedback` 위에 추가:

```ts
/** 화면에 그릴 구간 지표 한 줄 */
export interface PhaseMetric {
  key: string;
  label: string;
  userValue: number | null;
  proValue: number | null;
  difference: number | null;
  threshold: number | null;
  status: 'good' | 'warn' | 'favorable' | 'unavailable';
  why: string | null;
  /** "이 순간 보기"가 이동할 프레임. 없으면 버튼을 감춘다. */
  userFrame: number | null;
}
```

같은 파일 `PhaseFeedback` 인터페이스에 필드를 더한다:

```ts
  /** 이 구간의 상세 지표. 서버가 주지 않으면 빈 배열이며, 화면은 패널을 접은 채로도 열지 않는다. */
  metrics: PhaseMetric[];
```

- [ ] **Step 3: mapReport에서 구간별로 묶는다**

`src/features/report/utils/mapReport.ts`의 import에 `PhaseMetricDetail`을 더하고(`analysisApi`에서), `PhaseMetric`을 더한다(`report.types`에서). 그리고 파일 안에 헬퍼를 추가한다:

```ts
/** 서버 지표를 구간(phase)별로 묶는다. 순서는 서버가 준 순서를 유지한다. */
function groupMetricsByPhase(
  metrics: PhaseMetricDetail[] | null | undefined,
): Map<string, PhaseMetric[]> {
  const grouped = new Map<string, PhaseMetric[]>();
  (metrics ?? []).forEach((m) => {
    const list = grouped.get(m.phase) ?? [];
    list.push({
      key: m.key,
      label: m.label,
      userValue: m.userValue,
      proValue: m.proValue,
      difference: m.difference,
      threshold: m.threshold,
      status: m.status,
      why: m.why,
      userFrame: m.userFrame,
    });
    grouped.set(m.phase, list);
  });
  return grouped;
}
```

`buildReportData`의 상세 있는 경로에서, `const feedbacks: PhaseFeedback[] = detail.phaseScores.map((p) => {` **직전**에 추가:

```ts
  const metricsByPhase = groupMetricsByPhase(detail.phaseMetrics);
```

그리고 그 `map` 콜백이 돌려주는 객체에 필드를 더한다:

```ts
      metrics: metricsByPhase.get(p.phase) ?? [],
```

상세가 없는 폴백 경로는 `feedbacks: []`를 돌려주므로 수정할 것이 없다.

- [ ] **Step 4: 타입 검사**

Run (앱 루트에서):
```
npx tsc --noEmit
```
Expected: exit 0

- [ ] **Step 5: 커밋**

```bash
git add src/api/analysisApi.ts src/features/report/types/report.types.ts src/features/report/utils/mapReport.ts
git commit -m "Feat(ui): 구간별 상세 지표 타입 및 매핑 추가"
```

---

### Task 6: 구간 카드에 상세 지표 접기 패널

**Files:**
- Create: `src/features/report/components/PhaseMetricRow.tsx`
- Modify: `src/features/report/components/PhaseFeedback.tsx`

**Interfaces:**
- Consumes: `PhaseMetric` (Task 5)
- Produces: `PhaseFeedback`의 새 prop `onSeekFrame?: (frame: number) => void` — Task 7이 연결한다

- [ ] **Step 1: 지표 행 컴포넌트를 만든다**

`src/features/report/components/PhaseMetricRow.tsx` 생성:

```tsx
/**
 * [PhaseMetricRow.tsx]
 * 구간 상세 지표 한 줄.
 *
 * 값 자체(0.42)는 body-frame 정규화 좌표라 사용자에게 의미가 없다. 그래서
 * "차이 / 허용"을 나란히 보여 임계 대비로 읽히게 한다. 판정은 뱃지가 맡는다.
 */

import React from 'react';
import { View, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import AppText from '../../../components/common/AppText';
import { PhaseMetric } from '../types/report.types';

const STATUS_STYLE: Record<PhaseMetric['status'], { label: string; color: string; bg: string }> = {
  good: { label: '양호', color: '#3BC1A8', bg: 'bg-[#E8F8F5]' },
  warn: { label: '주의', color: '#D3735D', bg: 'bg-[#FAF4EB]' },
  favorable: { label: '다르지만 유리', color: '#6366F1', bg: 'bg-[#EEF0FF]' },
  unavailable: { label: '측정 못함', color: '#8E949A', bg: 'bg-[#F2F3F4]' },
};

interface PhaseMetricRowProps {
  metric: PhaseMetric;
  /** 지표가 측정된 순간으로 이동. 없으면 버튼을 그리지 않는다. */
  onSeekFrame?: (frame: number) => void;
}

export default function PhaseMetricRow({ metric, onSeekFrame }: PhaseMetricRowProps) {
  const style = STATUS_STYLE[metric.status];
  const measured = metric.userValue !== null && metric.proValue !== null;
  const canSeek = onSeekFrame !== undefined && metric.userFrame !== null;

  return (
    <View className="border-t border-border py-3">
      <View className="flex-row items-center justify-between mb-1.5">
        <AppText weight="bold" className="text-text-primary text-sm">
          {metric.label}
        </AppText>
        <View className={`px-2 py-0.5 rounded-full ${style.bg}`}>
          <AppText weight="bold" className="text-xs" style={{ color: style.color }}>
            {style.label}
          </AppText>
        </View>
      </View>

      {measured ? (
        <View className="flex-row items-center mb-1">
          <AppText className="text-text-secondary text-xs">
            나 {metric.userValue}  ·  기준 {metric.proValue}
          </AppText>
        </View>
      ) : (
        <AppText className="text-text-secondary text-xs mb-1">
          관절이 가려져 이 구간에서는 값을 재지 못했어요.
        </AppText>
      )}

      {measured && metric.difference !== null && metric.threshold !== null ? (
        <AppText weight="medium" className="text-text-primary text-xs mb-1">
          차이 {Math.abs(metric.difference).toFixed(2)} / 허용 {metric.threshold.toFixed(2)}
        </AppText>
      ) : null}

      {metric.why ? (
        <AppText className="text-text-secondary text-xs leading-4">ⓘ {metric.why}</AppText>
      ) : null}

      {canSeek ? (
        <TouchableOpacity
          onPress={() => onSeekFrame?.(metric.userFrame as number)}
          activeOpacity={0.8}
          accessibilityRole="button"
          accessibilityLabel={`${metric.label}이 측정된 순간으로 이동`}
          className="flex-row items-center self-end mt-2 px-3 py-1.5 rounded-full bg-brand-light"
        >
          <Ionicons name="play-skip-forward-outline" size={12} color="#3BC1A8" />
          <AppText weight="bold" className="text-brand text-xs ml-1">
            이 순간 보기
          </AppText>
        </TouchableOpacity>
      ) : null}
    </View>
  );
}
```

- [ ] **Step 2: 구간 카드에 접기 패널을 단다**

`PhaseFeedback.tsx` 상단 import에 추가:

```tsx
import { useState } from 'react';
import { TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import PhaseMetricRow from './PhaseMetricRow';
```

(이미 import된 것은 중복해서 넣지 않는다. `React`는 이미 import되어 있으므로 `useState`만 더한다.)

`PhaseFeedbackProps`에 prop을 더한다:

```tsx
  /** 지표가 측정된 순간으로 이동. 리포트 화면이 내려준다. */
  onSeekFrame?: (frame: number) => void;
```

컴포넌트 시그니처를 바꾸고 상태를 더한다:

```tsx
export default function PhaseFeedback({ data, reportType = 'pro', onSeekFrame }: PhaseFeedbackProps) {
  const [metricsOpen, setMetricsOpen] = useState(false);
```

컴포넌트의 마지막 `</View>` **직전**(개선안 블록 다음)에 추가:

```tsx
      {/*
        상세 지표는 기본으로 접어둔다. 구간마다 1~2개씩이라 항상 펼쳐두면
        정성 피드백이 묻힌다. 서버가 지표를 주지 않으면 행 자체를 그리지 않는다.
      */}
      {data.metrics.length > 0 ? (
        <View className="mt-4">
          <TouchableOpacity
            onPress={() => setMetricsOpen((open) => !open)}
            activeOpacity={0.7}
            accessibilityRole="button"
            accessibilityState={{ expanded: metricsOpen }}
            className="flex-row items-center justify-between border-t border-border pt-3"
          >
            <AppText weight="medium" className="text-text-secondary text-sm">
              상세 지표 {data.metrics.length}개
            </AppText>
            <Ionicons
              name={metricsOpen ? 'chevron-up' : 'chevron-down'}
              size={16}
              color="#8E949A"
            />
          </TouchableOpacity>

          {metricsOpen
            ? data.metrics.map((metric) => (
                <PhaseMetricRow key={metric.key} metric={metric} onSeekFrame={onSeekFrame} />
              ))
            : null}
        </View>
      ) : null}
```

- [ ] **Step 3: 타입 검사**

Run: `npx tsc --noEmit`
Expected: exit 0

- [ ] **Step 4: 번들이 빌드되는지 확인한다**

Run:
```
npx expo export --platform android --output-dir /tmp/phase-metrics-check
```
Expected: `Exported:` 로 끝나고 exit 0

- [ ] **Step 5: 커밋**

```bash
git add src/features/report/components/PhaseMetricRow.tsx src/features/report/components/PhaseFeedback.tsx
git commit -m "Feat(ui): 구간별 상세 지표 접기 패널 추가"
```

---

### Task 7: "이 순간 보기" 배선

**Files:**
- Modify: `src/features/report/components/SkeletonOverlayPlayer.tsx`
- Modify: `src/features/report/screens/ReportScreen.tsx`

**Interfaces:**
- Consumes: `PhaseFeedback`의 `onSeekFrame` (Task 6), 플레이어 내부의 기존 `seekToPhase(startFrame)`
- Produces: `SkeletonOverlayPlayer`의 새 prop `seekRequest?: { frame: number; nonce: number }`

- [ ] **Step 1: 플레이어가 외부 요청에 반응하게 한다**

`SkeletonOverlayPlayer.tsx`의 props 인터페이스에 추가:

```tsx
  /**
   * 외부에서 특정 프레임으로 이동을 요청할 때 쓴다.
   * 같은 프레임을 다시 눌러도 동작해야 하므로 nonce로 변화를 알린다.
   */
  seekRequest?: { frame: number; nonce: number };
```

컴포넌트 매개변수 구조분해에 `seekRequest`를 더한다. 그리고 `seekToPhase` 정의 **아래**에 다음 effect를 추가한다:

```tsx
  // 외부(구간 지표의 "이 순간 보기")에서 온 이동 요청 처리.
  // seekToPhase는 이미 프레임 → 시간 변환과 영상 seek를 담당하므로 그대로 재사용한다.
  useEffect(() => {
    if (!seekRequest) return;
    void seekToPhase(seekRequest.frame);
    // nonce가 바뀔 때만 반응한다. frame이 같아도 다시 눌렀다면 이동해야 한다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seekRequest?.nonce]);
```

- [ ] **Step 2: 리포트 화면이 요청을 만들고 위로 스크롤한다**

`ReportScreen.tsx`에서 `useRef`를 import에 더하고(`react`에서), 컴포넌트 안에 상태를 추가한다:

```tsx
  // 구간 지표의 "이 순간 보기" → 플레이어로 이동 + 플레이어가 보이도록 스크롤.
  const scrollViewRef = useRef<ScrollView>(null);
  const [seekRequest, setSeekRequest] = useState<{ frame: number; nonce: number } | null>(null);

  const handleSeekFrame = useCallback((frame: number) => {
    setSeekRequest((prev) => ({ frame, nonce: (prev?.nonce ?? 0) + 1 }));
    scrollViewRef.current?.scrollTo({ y: 0, animated: true });
  }, []);
```

`ScrollView`에 ref를 단다:

```tsx
      <ScrollView ref={scrollViewRef} className="flex-1" showsVerticalScrollIndicator={false}>
```

`SkeletonOverlayPlayer`에 prop을 넘긴다:

```tsx
          seekRequest={seekRequest ?? undefined}
```

`PhaseFeedback` 렌더에 prop을 넘긴다:

```tsx
              <PhaseFeedback
                key={index}
                data={feedback}
                reportType={reportType}
                onSeekFrame={handleSeekFrame}
              />
```

- [ ] **Step 3: 타입 검사**

Run: `npx tsc --noEmit`
Expected: exit 0

- [ ] **Step 4: 번들 확인**

Run:
```
npx expo export --platform android --output-dir /tmp/phase-metrics-check2
```
Expected: exit 0

- [ ] **Step 5: 커밋**

```bash
git add src/features/report/components/SkeletonOverlayPlayer.tsx src/features/report/screens/ReportScreen.tsx
git commit -m "Feat(ui): 상세 지표에서 해당 프레임으로 이동"
```

---

## 통합 확인 (실기기)

코드 검증으로는 여기까지다. 아래는 분석 서버·백엔드가 모두 떠 있어야 확인할 수 있어 사용자 손이 필요하다.

- [ ] 분석 서버(5020), 백엔드(8080), PostgreSQL(5432), Redis(6379)를 띄운다
- [ ] 앱에서 새 투구를 분석한다
- [ ] 타임라인 탭의 구간 카드마다 "상세 지표 N개"가 보이는지
- [ ] 펼치면 지표가 나오고, 양호/주의 뱃지와 "차이 / 허용"이 맞는지
- [ ] "이 순간 보기"를 누르면 위로 스크롤되며 스켈레톤이 그 프레임으로 이동하는지
- [ ] 최고의 1구 비교에서 "다르지만 유리"가 나타나는지(프로 비교에서는 나오지 않아야 한다)
