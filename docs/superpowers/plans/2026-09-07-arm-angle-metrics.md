# 팔 각도 지표 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 팔꿈치 굽힘각과 암슬롯을 팔이 관여하는 4구간에서 재어 기존 `phaseMetrics` 파이프라인으로 앱까지 내보낸다. 구간 지표가 8개에서 16개가 된다.

**Architecture:** 분석 서버에 각도 수학 순수 함수와 규칙 테이블을 담은 새 모듈을 두고, 기존 `build_phase_metrics`가 축 지표 목록 뒤에 각도 지표 목록을 이어붙인다. 각도에는 단위가 있으므로 계약에 `unit` 필드를 추가하고, 백엔드 DTO와 앱 타입이 이를 통과시킨다. 앱은 단위에 따라 표기 자릿수를 달리한다.

**Tech Stack:** Python 3 + pandas (분석 서버), Kotlin + Spring Boot 4 + Jackson 3 (백엔드), TypeScript + React Native/Expo (앱)

**Spec:** `docs/superpowers/specs/2026-09-07-arm-angle-metrics-design.md` (분석 서버 저장소 기준)

## Global Constraints

- 저장소 3개는 서로 다른 디렉터리다. **각 태스크의 `cd` 대상을 반드시 확인할 것.**
  - 분석 서버: `C:\Capstone\analysis\Analysis_algorithm`
  - 백엔드: `C:\Capstone\untitled\backend`
  - 앱: `C:\Capstone\Frontend`
- **`coaching_feedback.py`의 문장 생성 로직을 바꾸지 않는다.** 각도는 상세 지표에만 나오고 `feedback.good`/`bad` 문장에는 등장하지 않는다.
- **임계값:** 팔꿈치 굽힘각 `15.0`, 암슬롯 `10.0` (단위: 도)
- **`unit` 값:** 각도는 `"degree"`, 기존 축 지표는 `None`/`null`. 기존 8개에도 필드를 명시적으로 싣는다.
- **각도의 `favorableDirection`은 항상 `null`이다.** 각도 평가 경로는 `is_favorable`을 호출하지 않는다.
- **각도 반올림은 소수 첫째 자리(`round(x, 1)`)이고, status는 반올림한 값으로 판정한다.** 원값으로 판정하면 화면의 숫자와 뱃지가 어긋난다.
- **앱 표시 자릿수:** `userValue`/`proValue`는 정수(`78°`), `difference`/`threshold`는 소수 첫째 자리(`6.5°`, `±15.0°`).
- **측정 시점은 새로 만들지 않는다.** leg_lift 100%, stride 100%, acceleration 85%, follow_through 80% — 전부 기존 `AXIS_RULES`가 쓰는 시점이다.
- **앱 저장소에는 커밋하면 안 되는 더티 파일이 있다.** `app.json`, `eas.json`(사용자 편집), `.env.backup-cloudrun`(**비밀값 포함, .gitignore에 없음**). `git add .`을 절대 쓰지 말고 파일을 명시해 add할 것.
- 앱 저장소는 전체가 CRLF인데 prettier가 LF를 기대해 `eslint`가 수천 건의 노이즈를 낸다. **앱의 게이트는 `npx tsc --noEmit`과 `npx expo export`다.** eslint 결과로 판단하지 말 것.
- 커밋 메시지는 `git commit -m "..."` 한 줄로 쓴다. 여러 줄이 필요하면 파일에 써서 `-F`로 넘긴다. **PowerShell here-string(`@'...'@`)을 bash에서 쓰지 말 것** — 메시지가 깨진다.

---

### Task 1: 각도 수학 순수 함수

각도 계산만 담은 모듈을 만든다. 규칙 테이블과 파이프라인 통합은 Task 3이다.

**Files:**
- Create: `service/server/analysis/joint_angles.py`
- Test: `service/server/analysis/test_joint_angles.py`

**Interfaces:**
- Consumes: `analysis.coaching_feedback_utils.PosePoint` (필드: `x: float`, `y: float`, `frame: int | float | None`)
- Produces:
  - `elbow_flexion_degrees(shoulder: PosePoint, elbow: PosePoint, wrist: PosePoint) -> float | None`
  - `arm_slot_degrees(shoulder: PosePoint, elbow: PosePoint) -> float | None`
  - `DEGENERATE: float` (퇴화 판정 기준 `1e-9`)

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`service/server/analysis/test_joint_angles.py`를 새로 만든다:

```python
from __future__ import annotations

import math

from analysis.coaching_feedback_utils import PosePoint
from analysis.joint_angles import arm_slot_degrees, elbow_flexion_degrees


def _p(x: float, y: float) -> PosePoint:
    return PosePoint(x=x, y=y, frame=0)


def test_elbow_flexion_right_angle() -> None:
    # 팔꿈치를 원점에 두고 어깨는 위로, 손목은 옆으로 → 직각
    assert abs(elbow_flexion_degrees(_p(0.0, 3.0), _p(0.0, 0.0), _p(4.0, 0.0)) - 90.0) < 1e-9


def test_elbow_flexion_straight_arm_is_180() -> None:
    # 어깨-팔꿈치-손목이 일직선이면 180°(곧게 편 팔)
    assert abs(elbow_flexion_degrees(_p(0.0, 2.0), _p(0.0, 1.0), _p(0.0, 0.0)) - 180.0) < 1e-9


def test_arm_slot_along_torso_axis_is_zero() -> None:
    # 상완이 몸통축(+y) 방향이면 0°
    assert abs(arm_slot_degrees(_p(0.0, 0.0), _p(0.0, 1.0)) - 0.0) < 1e-9


def test_arm_slot_perpendicular_is_90() -> None:
    assert abs(arm_slot_degrees(_p(0.0, 0.0), _p(1.0, 0.0)) - 90.0) < 1e-9


def test_arm_slot_hanging_down_is_180() -> None:
    assert abs(arm_slot_degrees(_p(0.0, 0.0), _p(0.0, -1.0)) - 180.0) < 1e-9


def test_arm_slot_is_mirror_invariant() -> None:
    # 좌완/우완과 정규화 단계의 mirror_x에 무관해야 한다
    right = arm_slot_degrees(_p(0.0, 0.0), _p(1.0, 1.0))
    left = arm_slot_degrees(_p(0.0, 0.0), _p(-1.0, 1.0))
    assert abs(right - left) < 1e-9


def _rotate_scale(point: PosePoint, theta: float, scale: float) -> PosePoint:
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    return PosePoint(
        x=scale * ((point.x * cos_t) - (point.y * sin_t)),
        y=scale * ((point.x * sin_t) + (point.y * cos_t)),
        frame=point.frame,
    )


def test_elbow_flexion_survives_rotation_and_scale() -> None:
    """정규화가 각도를 보존한다는 것이 이 설계의 근거다. 반드시 검증한다.

    body-frame 정규화는 골반 중심 이동 + 몸통축 직교 회전 + 단일 스칼라 나눗셈이다.
    회전은 직교 변환이고 스케일은 등방이므로 각도는 바뀌지 않아야 한다.
    """
    shoulder, elbow, wrist = _p(0.0, 3.0), _p(0.0, 0.0), _p(4.0, 0.0)
    before = elbow_flexion_degrees(shoulder, elbow, wrist)
    after = elbow_flexion_degrees(
        _rotate_scale(shoulder, 0.7, 2.5),
        _rotate_scale(elbow, 0.7, 2.5),
        _rotate_scale(wrist, 0.7, 2.5),
    )
    assert abs(before - after) < 1e-9


def test_elbow_flexion_is_mirror_invariant() -> None:
    # 정규화 단계의 mirror_x는 x 부호를 뒤집는다. 사이각은 그대로여야 한다.
    normal = elbow_flexion_degrees(_p(0.0, 3.0), _p(0.0, 0.0), _p(4.0, 0.0))
    mirrored = elbow_flexion_degrees(_p(0.0, 3.0), _p(0.0, 0.0), _p(-4.0, 0.0))
    assert abs(normal - mirrored) < 1e-9


def test_degenerate_points_yield_none() -> None:
    # 관절이 겹쳐 보이면 각도가 정의되지 않는다
    assert elbow_flexion_degrees(_p(0.0, 0.0), _p(0.0, 0.0), _p(1.0, 0.0)) is None
    assert elbow_flexion_degrees(_p(1.0, 0.0), _p(0.0, 0.0), _p(0.0, 0.0)) is None
    assert arm_slot_degrees(_p(0.0, 0.0), _p(0.0, 0.0)) is None
```

- [ ] **Step 2: 실패를 확인한다**

```bash
cd C:/Capstone/analysis/Analysis_algorithm/service/server && ./.venv/Scripts/python.exe -c "import analysis.test_joint_angles"
```

Expected: `ModuleNotFoundError: No module named 'analysis.joint_angles'`

- [ ] **Step 3: 최소 구현을 쓴다**

`service/server/analysis/joint_angles.py`를 새로 만든다:

```python
"""관절 각도.

기존 구간 지표는 전부 "관절 한 점의 좌표"에서 나온다. 각도는 세 점이 필요해
AxisRule 구조로는 만들 수 없어 별도 모듈로 둔다.

body-frame 정규화는 골반 중심 이동 + 몸통축 직교 회전 + 단일 스칼라(body_scale)
나눗셈이다. 회전은 직교 변환이고 스케일은 등방이므로 각도는 보존된다. 그래서
좌표값과 달리 도(°) 자체가 의미를 갖는다.
"""

from __future__ import annotations

import math

from analysis.coaching_feedback_utils import PosePoint

# 벡터 길이가 이보다 짧으면 각도가 정의되지 않는다(관절이 겹쳐 보이는 경우).
DEGENERATE = 1e-9


def elbow_flexion_degrees(shoulder: PosePoint, elbow: PosePoint, wrist: PosePoint) -> float | None:
    """어깨·팔꿈치·손목이 이루는 사이각(0~180°). 180°면 팔이 곧게 편 상태."""
    upper_x, upper_y = shoulder.x - elbow.x, shoulder.y - elbow.y
    fore_x, fore_y = wrist.x - elbow.x, wrist.y - elbow.y
    if math.hypot(upper_x, upper_y) < DEGENERATE or math.hypot(fore_x, fore_y) < DEGENERATE:
        return None
    # acos(dot / |a||b|)는 두 벡터가 거의 나란할 때 수치적으로 불안정하다.
    cross = (upper_x * fore_y) - (upper_y * fore_x)
    dot = (upper_x * fore_x) + (upper_y * fore_y)
    return math.degrees(math.atan2(abs(cross), dot))


def arm_slot_degrees(shoulder: PosePoint, elbow: PosePoint) -> float | None:
    """상완(어깨→팔꿈치)이 몸통축에서 벌어진 각(0~180°).

    0°는 몸통축 방향, 90°는 몸통과 직각(사이드암), 180°는 아래로 내린 상태.

    수평이 아니라 몸통축을 기준으로 잡는 것이 핵심이다. 정규화 좌표계의 y축이 이미
    골반 중심 → 어깨 중심이므로 상체가 기울어도 자동으로 보정된다. 수평 기준으로 재면
    상체를 많이 숙이는 투수는 실제 암슬롯이 같아도 매번 다른 값이 나온다.

    x에 절댓값을 쓰는 이유는 좌완/우완에 따라, 그리고 정규화 단계의 mirror_x에 따라
    부호가 뒤집히기 때문이다.
    """
    upper_x, upper_y = elbow.x - shoulder.x, elbow.y - shoulder.y
    if math.hypot(upper_x, upper_y) < DEGENERATE:
        return None
    return math.degrees(math.atan2(abs(upper_x), upper_y))
```

- [ ] **Step 4: 통과를 확인한다**

```bash
cd C:/Capstone/analysis/Analysis_algorithm/service/server && ./.venv/Scripts/python.exe -c "import analysis.test_joint_angles as m; fs=[(n,f) for n,f in vars(m).items() if n.startswith('test_')]; [f() for n,f in fs]; print('ALL PASS', len(fs))"
```

Expected: `ALL PASS 9`

- [ ] **Step 5: 기존 테스트가 깨지지 않았는지 확인한다**

```bash
cd C:/Capstone/analysis/Analysis_algorithm/service/server && ./.venv/Scripts/python.exe -c "import analysis.test_phase_metrics as m; fs=[(n,f) for n,f in vars(m).items() if n.startswith('test_')]; [f() for n,f in fs]; print('ALL PASS', len(fs))"
```

Expected: `ALL PASS 9`

- [ ] **Step 6: 커밋**

```bash
cd C:/Capstone/analysis/Analysis_algorithm && git add service/server/analysis/joint_angles.py service/server/analysis/test_joint_angles.py && git commit -m "분석: 관절 각도 계산 함수 추가 (굽힘각, 암슬롯)"
```

---

### Task 2: 기존 축 지표에 `unit: None` 싣기

계약에 `unit`을 더하는 첫 단계. 각도가 붙기 전에 기존 8개부터 필드를 갖게 한다. 필드가 있다 없다 하는 것보다 항상 있는 편이 앱에서 다루기 쉽다.

**Files:**
- Modify: `service/server/analysis/phase_metrics.py` (`_evaluate`의 `base` 딕셔너리)
- Test: `service/server/analysis/test_phase_metrics.py` (테스트 추가)

**Interfaces:**
- Produces: `build_phase_metrics(...)`가 돌려주는 각 항목에 `"unit"` 키가 생긴다. 축 지표는 `None`.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`service/server/analysis/test_phase_metrics.py` **맨 끝에** 아래를 덧붙인다:

```python
def test_axis_metrics_carry_null_unit() -> None:
    """축 지표는 단위 없는 정규화 좌표다. 필드를 항상 실어 앱이 분기하기 쉽게 한다."""
    metrics = build_phase_metrics(_pose(0.5), _pose(0.5), _phases(), _phases())
    assert all("unit" in m for m in metrics)
    assert all(m["unit"] is None for m in metrics)
```

- [ ] **Step 2: 실패를 확인한다**

```bash
cd C:/Capstone/analysis/Analysis_algorithm/service/server && ./.venv/Scripts/python.exe -c "import analysis.test_phase_metrics as m; m.test_axis_metrics_carry_null_unit()"
```

Expected: `AssertionError`

- [ ] **Step 3: 최소 구현을 쓴다**

`phase_metrics.py`의 `_evaluate` 안 `base` 딕셔너리에 `"unit"` 한 줄을 넣는다. `"label"` 다음 줄에 둔다:

```python
    base: dict[str, Any] = {
        "phase": rule.phase,
        "key": rule.category,
        "label": rule.metric_label,
        # 축 지표는 body-frame 정규화 좌표라 단위가 없다. 각도 지표와 구분하는 값이다.
        "unit": None,
        "threshold": round(rule.threshold, 4),
        "favorableDirection": rule.favorable_direction,
        "why": rule.why,
    }
```

- [ ] **Step 4: 통과를 확인한다**

```bash
cd C:/Capstone/analysis/Analysis_algorithm/service/server && ./.venv/Scripts/python.exe -c "import analysis.test_phase_metrics as m; fs=[(n,f) for n,f in vars(m).items() if n.startswith('test_')]; [f() for n,f in fs]; print('ALL PASS', len(fs))"
```

Expected: `ALL PASS 10`

- [ ] **Step 5: 커밋**

```bash
cd C:/Capstone/analysis/Analysis_algorithm && git add service/server/analysis/phase_metrics.py service/server/analysis/test_phase_metrics.py && git commit -m "분석: 구간 지표에 unit 필드 추가 (축 지표는 null)"
```

---

### Task 3: 각도 규칙 8개를 파이프라인에 통합

이 태스크가 지표를 8개에서 16개로 늘린다.

**Files:**
- Modify: `service/server/analysis/joint_angles.py` (`AngleRule`, `ANGLE_RULES` 추가)
- Modify: `service/server/analysis/coaching_feedback_utils.py` (`joint_name`에 `throwing_shoulder` 역할 추가)
- Modify: `service/server/analysis/phase_metrics.py` (`_evaluate_angle`, `_angle_at_phase` 추가 및 `build_phase_metrics` 반환 확장)
- Test: `service/server/analysis/test_joint_angles.py` (통합 테스트 추가), `service/server/analysis/test_phase_metrics.py` (개수 단언 수정)

**Interfaces:**
- Consumes: Task 1의 `elbow_flexion_degrees`, `arm_slot_degrees`; 기존 `point_at_phase(table, phases, phase, joint, percent) -> PosePoint | None`, `joint_name(table, role) -> str`
- Produces:
  - `AngleRule` (필드: `phase`, `kind`, `percent`, `threshold`, `category`, `metric_label`, `why`)
  - `ANGLE_RULES: tuple[AngleRule, ...]` (8개)
  - `build_phase_metrics(...)`가 16개 항목을 돌려준다 (축 8개 뒤에 각도 8개)

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`service/server/analysis/test_joint_angles.py` **맨 끝에** 아래를 덧붙인다. 파일 상단의 import 줄에 필요한 것을 함께 추가한다 — 최종 import 블록은 이렇게 된다:

```python
from __future__ import annotations

import math
from types import SimpleNamespace

import pandas as pd

from analysis.coaching_feedback_utils import PosePoint
from analysis.joint_angles import ANGLE_RULES, arm_slot_degrees, elbow_flexion_degrees
from analysis.phase_metrics import build_phase_metrics
```

덧붙일 테스트:

```python
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


def _arm_pose(slot_deg: float, flex_deg: float = 90.0) -> pd.DataFrame:
    """암슬롯과 굽힘각이 정확히 지정한 값이 되도록 만든 포즈 테이블.

    모든 프레임이 같은 자세라 어느 시점을 재도 같은 값이 나온다.
    joint_name()의 throwing_side 기본값이 right이므로 right_* 컬럼을 채운다.
    confidence 컬럼을 두지 않으면 point_at_frame이 신뢰도 게이팅을 건너뛴다.
    """
    slot = math.radians(slot_deg)
    elbow_x, elbow_y = math.sin(slot), math.cos(slot)
    # 팔꿈치 → 어깨 방향에서 flex_deg만큼 돌린 곳에 손목을 둔다.
    to_shoulder = math.atan2(-elbow_y, -elbow_x)
    wrist_dir = to_shoulder + math.radians(flex_deg)
    wrist_x, wrist_y = elbow_x + math.cos(wrist_dir), elbow_y + math.sin(wrist_dir)
    return pd.DataFrame(
        [
            {
                "frame_index": float(f),
                "right_shoulder_body_x": 0.0,
                "right_shoulder_body_y": 0.0,
                "right_elbow_body_x": elbow_x,
                "right_elbow_body_y": elbow_y,
                "right_wrist_body_x": wrist_x,
                "right_wrist_body_y": wrist_y,
            }
            for f in range(0, 51)
        ]
    )


def _metric(metrics: list, key: str) -> dict:
    return next(m for m in metrics if m["key"] == key)


def test_angle_rules_cover_four_phases_with_two_metrics_each() -> None:
    assert len(ANGLE_RULES) == 8
    assert {r.phase for r in ANGLE_RULES} == {
        "leg_lift",
        "stride",
        "acceleration",
        "follow_through",
    }
    assert len({r.category for r in ANGLE_RULES}) == 8


def test_build_phase_metrics_returns_axis_and_angle_metrics() -> None:
    metrics = build_phase_metrics(_arm_pose(70.0), _arm_pose(70.0), _phases(), _phases())
    assert len(metrics) == 16
    degrees = [m for m in metrics if m["unit"] == "degree"]
    assert len(degrees) == 8
    # key는 앱이 리스트 렌더 key로 쓴다. 16개 전부 고유해야 한다.
    assert len({m["key"] for m in metrics}) == 16


def test_angle_metrics_never_report_favorable() -> None:
    """각도에는 유리한 방향이 없다. 굽힘각도 암슬롯도 '클수록 유리'가 성립하지 않는다."""
    metrics = build_phase_metrics(
        _arm_pose(50.0), _arm_pose(90.0), _phases(), _phases(), comparison_mode="best_pitch"
    )
    for metric in metrics:
        if metric["unit"] == "degree":
            assert metric["favorableDirection"] is None
            assert metric["status"] != "favorable"


def test_arm_slot_difference_at_threshold_is_good() -> None:
    # 암슬롯 허용은 10.0° — 정확히 10° 차이는 good
    metrics = build_phase_metrics(_arm_pose(80.0), _arm_pose(70.0), _phases(), _phases())
    slot = _metric(metrics, "acceleration_arm_slot")
    assert slot["unit"] == "degree"
    assert abs(slot["difference"] - 10.0) < 1e-9
    assert slot["status"] == "good"


def test_arm_slot_difference_past_threshold_is_warn() -> None:
    metrics = build_phase_metrics(_arm_pose(80.1), _arm_pose(70.0), _phases(), _phases())
    slot = _metric(metrics, "acceleration_arm_slot")
    assert slot["status"] == "warn"


def test_status_uses_rounded_value_not_raw() -> None:
    """원값으로 판정하면 화면의 숫자와 뱃지가 어긋난다.

    원 차이 10.04°는 보내는 값(소수 첫째 자리)으로는 10.0°이고 허용도 10.0°이므로
    good이어야 한다. 원값으로 판정하면 warn이 나와, 사용자는 '10.0 / 허용 10.0'인데
    주의라고 적힌 화면을 보게 된다.
    """
    metrics = build_phase_metrics(_arm_pose(80.04), _arm_pose(70.0), _phases(), _phases())
    slot = _metric(metrics, "acceleration_arm_slot")
    assert slot["difference"] == 10.0
    assert slot["status"] == "good"


def test_angle_values_are_rounded_to_one_decimal() -> None:
    metrics = build_phase_metrics(_arm_pose(70.0), _arm_pose(70.0), _phases(), _phases())
    for metric in metrics:
        if metric["unit"] == "degree" and metric["userValue"] is not None:
            assert metric["userValue"] == round(metric["userValue"], 1)
            assert metric["threshold"] == round(metric["threshold"], 1)


def test_missing_arm_joints_yield_unavailable_angles() -> None:
    empty = pd.DataFrame([{"frame_index": float(f)} for f in range(0, 51)])
    metrics = build_phase_metrics(empty, empty, _phases(), _phases())
    degrees = [m for m in metrics if m["unit"] == "degree"]
    assert len(degrees) == 8
    assert all(m["status"] == "unavailable" for m in degrees)
    assert all(m["userValue"] is None and m["difference"] is None for m in degrees)


def test_angle_metric_carries_label_why_and_frame() -> None:
    metrics = build_phase_metrics(_arm_pose(70.0), _arm_pose(70.0), _phases(), _phases())
    slot = _metric(metrics, "stride_arm_slot")
    assert slot["phase"] == "stride"
    assert slot["label"]
    assert slot["why"]
    assert slot["userFrame"] == 30  # stride 20~30의 100% 지점
```

- [ ] **Step 2: 실패를 확인한다**

```bash
cd C:/Capstone/analysis/Analysis_algorithm/service/server && ./.venv/Scripts/python.exe -c "import analysis.test_joint_angles"
```

Expected: `ImportError: cannot import name 'ANGLE_RULES' from 'analysis.joint_angles'`

- [ ] **Step 3: 규칙 테이블을 추가한다**

`joint_angles.py`의 import 블록을 아래로 바꾼다:

```python
from __future__ import annotations

import math
from dataclasses import dataclass

from analysis.coaching_feedback_utils import PosePoint
```

그리고 파일 **맨 끝에** 아래를 덧붙인다:

```python
@dataclass(frozen=True)
class AngleRule:
    """각도 지표 한 개의 규칙.

    관절 역할은 kind가 정한다 — 굽힘각은 어깨·팔꿈치·손목, 암슬롯은 어깨·팔꿈치.
    percent는 전부 기존 AXIS_RULES가 이미 쓰는 시점이다. 새 시점을 만들면 같은
    구간 안에서도 "이 순간 보기"가 지표마다 다른 프레임으로 튄다.
    """

    phase: str
    kind: str  # "elbow_flexion" | "arm_slot"
    percent: float
    threshold: float
    category: str
    metric_label: str
    why: str


ELBOW_FLEXION = "elbow_flexion"
ARM_SLOT = "arm_slot"

# 임계값 15°/10°는 코칭 통념에 기반한 판단값이다. 기존 축 지표의 임계값과 마찬가지로
# 라벨링된 데이터셋에서 나온 값이 아니므로, 실기기에서 보면서 여기서 조정한다.
ANGLE_RULES = (
    AngleRule(
        "leg_lift", ELBOW_FLEXION, 100.0, 15.0, "leg_lift_elbow_flexion", "팔꿈치 굽힘각",
        "레그 리프트 시점의 팔 접힘은 이후 팔 스윙의 출발 자세를 정합니다.",
    ),
    AngleRule(
        "leg_lift", ARM_SLOT, 100.0, 10.0, "leg_lift_arm_slot", "암슬롯(상완 기울기)",
        "이 시점의 팔 높이가 흔들리면 이후 동작 전체가 따라 흔들립니다.",
    ),
    AngleRule(
        "stride", ELBOW_FLEXION, 100.0, 15.0, "stride_elbow_flexion", "팔꿈치 굽힘각",
        "디딤발이 닿는 순간의 팔 접힘은 팔 스윙이 늦지 않았는지 보여줍니다.",
    ),
    AngleRule(
        "stride", ARM_SLOT, 100.0, 10.0, "stride_arm_slot", "암슬롯(상완 기울기)",
        "디딤발 착지 때 팔이 올라와 있어야 합니다. 늦으면 어깨에 부담이 몰립니다.",
    ),
    AngleRule(
        "acceleration", ELBOW_FLEXION, 85.0, 15.0, "acceleration_elbow_flexion", "팔꿈치 굽힘각",
        "릴리즈 직전 팔꿈치 각도는 공에 실리는 힘과 팔꿈치 부하를 함께 좌우합니다.",
    ),
    AngleRule(
        "acceleration", ARM_SLOT, 85.0, 10.0, "acceleration_arm_slot", "암슬롯(상완 기울기)",
        "암슬롯이 투구마다 흔들리면 릴리즈 포인트가 달라져 제구가 무너집니다.",
    ),
    AngleRule(
        "follow_through", ELBOW_FLEXION, 80.0, 15.0, "follow_through_elbow_flexion", "팔꿈치 굽힘각",
        "던진 뒤 팔이 자연스럽게 펴지는지는 감속이 제대로 되는지를 보여줍니다.",
    ),
    AngleRule(
        "follow_through", ARM_SLOT, 80.0, 10.0, "follow_through_arm_slot", "암슬롯(상완 기울기)",
        "마무리 팔 경로가 일정해야 어깨·팔꿈치 부담이 분산됩니다.",
    ),
)
```

- [ ] **Step 4: `joint_name`에 어깨 역할을 추가한다**

`coaching_feedback_utils.py`의 `joint_name` 안 `names` 딕셔너리에 한 줄을 넣는다. 현재 매핑에 어깨가 없어서, 그대로 두면 `"throwing_shoulder"`가 컬럼 이름으로 그대로 새어 나가 조회에 실패한다:

```python
    names = {
        "throwing_shoulder": f"{throwing_side}_shoulder",
        "throwing_wrist": f"{throwing_side}_wrist",
        "throwing_elbow": f"{throwing_side}_elbow",
        "stride_knee": f"{stride_side}_knee",
        "stride_foot": f"{stride_side}_foot_index",
    }
```

- [ ] **Step 5: 파이프라인에 각도 평가를 붙인다**

`phase_metrics.py`의 import 블록에 아래를 추가한다:

```python
from analysis.joint_angles import (
    ANGLE_RULES,
    ARM_SLOT,
    AngleRule,
    arm_slot_degrees,
    elbow_flexion_degrees,
)
```

상수 아래에 한 줄을 더한다:

```python
ANGLE_UNIT = "degree"
# 각도는 소수 첫째 자리까지만 의미가 있다. MediaPipe 2D 추정치에 그 아래 정밀도는 없다.
ANGLE_DECIMALS = 1
```

`build_phase_metrics`의 `return`을 아래로 바꾼다:

```python
    return [
        _evaluate(rule, user_pose, pro_pose, user_phases, pro_phases, comparison_mode)
        for rule in AXIS_RULES
    ] + [
        _evaluate_angle(rule, user_pose, pro_pose, user_phases, pro_phases)
        for rule in ANGLE_RULES
    ]
```

파일 **맨 끝에** 아래 두 함수를 덧붙인다:

```python
def _evaluate_angle(
    rule: AngleRule,
    user_pose: pd.DataFrame,
    pro_pose: pd.DataFrame,
    user_phases: Any,
    pro_phases: Any,
) -> dict[str, Any]:
    """각도 지표 한 개를 평가한다.

    축 지표와 분기로 섞지 않고 별도 함수로 두는 이유는 규칙 타입이 다르고 status
    규칙도 다르기 때문이다. 각도에는 유리한 방향이 없어 is_favorable을 부르지 않는다 —
    불러도 favorable_direction이 없어 항상 False지만, 부르지 않는 편이 그 사실을
    코드에 남긴다.
    """
    threshold = round(rule.threshold, ANGLE_DECIMALS)
    base: dict[str, Any] = {
        "phase": rule.phase,
        "key": rule.category,
        "label": rule.metric_label,
        "unit": ANGLE_UNIT,
        "threshold": threshold,
        "favorableDirection": None,
        "why": rule.why,
    }

    user_angle, user_frame = _angle_at_phase(rule, user_pose, user_phases)
    pro_angle, pro_frame = _angle_at_phase(rule, pro_pose, pro_phases)

    if user_angle is None or pro_angle is None:
        return {
            **base,
            "userValue": None,
            "proValue": None,
            "difference": None,
            "status": STATUS_UNAVAILABLE,
            "userFrame": None,
            "proFrame": None,
        }

    user_value = round(user_angle, ANGLE_DECIMALS)
    pro_value = round(pro_angle, ANGLE_DECIMALS)
    # 판정은 내보내는 값으로 한다. 원값으로 판정하면 화면에 실린 숫자로는 양호인데
    # 뱃지는 주의인 구간이 생긴다.
    diff = round(user_value - pro_value, ANGLE_DECIMALS)

    return {
        **base,
        "userValue": user_value,
        "proValue": pro_value,
        "difference": diff,
        "status": STATUS_GOOD if abs(diff) <= threshold else STATUS_WARN,
        "userFrame": user_frame,
        "proFrame": pro_frame,
    }


def _angle_at_phase(
    rule: AngleRule, pose: pd.DataFrame, phases: Any
) -> tuple[float | None, Any]:
    """규칙이 요구하는 관절을 모두 같은 프레임에서 뽑아 각도를 계산한다.

    신뢰도 게이팅은 point_at_frame이 관절마다 이미 한다. 가려진 관절이 하나라도
    있으면 그 점이 None으로 돌아와 자연스럽게 unavailable이 된다.
    """
    shoulder = point_at_phase(
        pose, phases, rule.phase, joint_name(pose, "throwing_shoulder"), rule.percent
    )
    elbow = point_at_phase(
        pose, phases, rule.phase, joint_name(pose, "throwing_elbow"), rule.percent
    )
    if shoulder is None or elbow is None:
        return None, None

    if rule.kind == ARM_SLOT:
        return arm_slot_degrees(shoulder, elbow), elbow.frame

    wrist = point_at_phase(
        pose, phases, rule.phase, joint_name(pose, "throwing_wrist"), rule.percent
    )
    if wrist is None:
        return None, None
    return elbow_flexion_degrees(shoulder, elbow, wrist), elbow.frame
```

- [ ] **Step 6: 기존 개수 단언을 고친다**

`test_phase_metrics.py`의 `test_missing_joint_yields_unavailable_with_null_values` 안에서 `assert len(metrics) == 8`을 아래로 바꾼다:

```python
    assert len(metrics) == 16  # 축 지표 8 + 각도 지표 8
```

- [ ] **Step 7: 통과를 확인한다**

```bash
cd C:/Capstone/analysis/Analysis_algorithm/service/server && ./.venv/Scripts/python.exe -c "
import analysis.test_joint_angles as a, analysis.test_phase_metrics as b
total=0
for m in (a,b):
    fs=[(n,f) for n,f in vars(m).items() if n.startswith('test_')]
    [f() for n,f in fs]
    total+=len(fs)
print('ALL PASS', total)
"
```

Expected: `ALL PASS 28`

- [ ] **Step 8: 다른 테스트 모듈도 회귀가 없는지 확인한다**

```bash
cd C:/Capstone/analysis/Analysis_algorithm/service/server && ./.venv/Scripts/python.exe -c "
import importlib
total=0
for name in ('test_coaching_feedback','test_normalization_body_scale','test_phase_stride_contact','test_pose_coordinates','test_similarity_scoring_scale'):
    m=importlib.import_module('analysis.'+name)
    fs=[(n,f) for n,f in vars(m).items() if n.startswith('test_')]
    [f() for n,f in fs]
    total+=len(fs)
print('ALL PASS', total)
"
```

Expected: `ALL PASS`로 끝나고 예외가 없을 것

- [ ] **Step 9: 커밋**

```bash
cd C:/Capstone/analysis/Analysis_algorithm && git add service/server/analysis/joint_angles.py service/server/analysis/phase_metrics.py service/server/analysis/coaching_feedback_utils.py service/server/analysis/test_joint_angles.py service/server/analysis/test_phase_metrics.py && git commit -m "분석: 팔 각도 지표 8개를 구간 지표 파이프라인에 통합"
```

---

### Task 4: 백엔드 `unit` 통과

`PlayerAnalysisDto`는 고정 필드만 갖는다. Jackson 3는 DTO에 선언되지 않은 필드를 조용히 버리므로, 이 한 줄이 없으면 분석 서버가 보낸 `unit`이 앱까지 도달하지 못한다.

**Files:**
- Modify: `src/main/kotlin/com/capstone/backend/domain/analysis/dto/AnalysisDto.kt` (`PhaseMetricDto`)
- Test: `src/test/kotlin/com/capstone/backend/domain/analysis/dto/PhaseMetricPassthroughTest.kt`

**Interfaces:**
- Produces: `PhaseMetricDto.unit: String?`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`PhaseMetricPassthroughTest.kt`의 `payload` 안 지표 객체에서 `"label"` 다음 줄에 `"unit": "degree",`를 넣는다. 그리고 클래스 **맨 끝에** 아래 두 테스트를 덧붙인다:

```kotlin
    @Test
    @DisplayName("각도 지표의 unit이 역직렬화된다")
    fun deserializesUnit() {
        val dto = mapper.readValue(payload, PlayerAnalysisDto::class.java)

        assertThat(dto.phaseMetrics!!.first().unit).isEqualTo("degree")
    }

    @Test
    @DisplayName("unit 없는 축 지표는 null이 된다")
    fun toleratesMissingUnit() {
        val axisOnly =
            """
            {
              "analysisId": "a1", "proId": "7", "overallScore": 79.3, "phaseScores": [],
              "phaseMetrics": [
                { "phase": "stride", "key": "stride_foot_width", "label": "디딤발 착지 폭", "status": "good" }
              ]
            }
            """.trimIndent()

        val dto = mapper.readValue(axisOnly, PlayerAnalysisDto::class.java)

        assertThat(dto.phaseMetrics!!.first().unit).isNull()
    }
```

- [ ] **Step 2: 실패를 확인한다**

```bash
cd C:/Capstone/untitled/backend && ./gradlew test --tests "*PhaseMetricPassthroughTest*" 2>&1 | tail -20
```

Expected: 컴파일 실패 — `unresolved reference: unit`

- [ ] **Step 3: 최소 구현을 쓴다**

`AnalysisDto.kt`의 `PhaseMetricDto`에서 `val label: String,` 다음 줄에 한 줄을 넣는다:

```kotlin
data class PhaseMetricDto(
    val phase: String,
    val key: String,
    val label: String,
    /** "degree"면 도(°) 단위, null이면 단위 없는 정규화 좌표. 앱이 표기를 나눈다. */
    val unit: String? = null,
    val userValue: Double? = null,
```

- [ ] **Step 4: 통과를 확인한다**

```bash
cd C:/Capstone/untitled/backend && ./gradlew test --tests "*PhaseMetricPassthroughTest*" 2>&1 | tail -20
```

Expected: `BUILD SUCCESSFUL`

- [ ] **Step 5: 전체 테스트로 회귀를 확인한다**

```bash
cd C:/Capstone/untitled/backend && ./gradlew cleanTest test 2>&1 | tail -20
```

Expected: `BUILD SUCCESSFUL` (기존 41개 + 새 2개)

- [ ] **Step 6: 커밋**

```bash
cd C:/Capstone/untitled/backend && git add src/main/kotlin/com/capstone/backend/domain/analysis/dto/AnalysisDto.kt src/test/kotlin/com/capstone/backend/domain/analysis/dto/PhaseMetricPassthroughTest.kt && git commit -m "구간 지표 DTO에 unit 필드 추가"
```

---

### Task 5: 앱 표기 함수

절대값과 판정값의 자릿수가 다르므로 순수 함수로 분리한다. 앱에는 테스트 러너가 없으므로, 이 파일만 따로 컴파일해 node로 검증한다.

**Files:**
- Create: `src/features/report/utils/formatMetric.ts`

**Interfaces:**
- Produces:
  - `DEGREE: 'degree'`
  - `formatValue(value: number, unit: string | null): string`
  - `formatJudgment(value: number, unit: string | null): string`
  - `describeDifference(difference: number, unit: string | null): string`

- [ ] **Step 1: 구현을 쓴다**

`src/features/report/utils/formatMetric.ts`를 새로 만든다:

```ts
/**
 * [formatMetric.ts]
 * 구간 상세 지표의 값 표기.
 *
 * 절대값과 판정값의 자릿수가 다르다. 절대 각도는 1도 아래가 노이즈라 정수로 줄이지만,
 * 차이는 임계값과 비교되는 값이라 자릿수를 줄이면 안 된다. 차이를 정수로 줄이면
 * 15.4°가 15°로 보이는데 허용도 15°라 같아 보이면서 뱃지는 '주의'인 구간이 생긴다.
 * 게이지 마커는 띠 밖에 있는데 문구는 같다고 말하는, 앞뒤가 맞지 않는 화면이 된다.
 */

export const DEGREE = 'degree';

/** 알 수 없는 단위가 오면 좌표 표기로 폴백한다. 화면이 죽지 않는 것이 우선이다. */
export function formatValue(value: number, unit: string | null): string {
  return unit === DEGREE ? `${Math.round(value)}°` : value.toFixed(2);
}

export function formatJudgment(value: number, unit: string | null): string {
  return unit === DEGREE ? `${value.toFixed(1)}°` : value.toFixed(2);
}

/**
 * 게이지가 방향까지 보여주므로 문구도 방향을 갖는다. 절댓값만 쓰면 마커가 왼쪽에
 * 있는데 문구는 방향이 없어 서로 다른 말을 하게 된다.
 *
 * "차이 없음" 판정은 표시에 쓰는 자릿수와 같은 자릿수로 한다. 다르면 "기준보다
 * 0.0° 큼" 같은 문구가 나온다.
 */
export function describeDifference(difference: number, unit: string | null): string {
  const magnitude = Math.abs(difference);
  const rounded = Number(unit === DEGREE ? magnitude.toFixed(1) : magnitude.toFixed(2));
  if (rounded === 0) {
    return '기준과 거의 같음';
  }
  return `기준보다 ${formatJudgment(magnitude, unit)} ${difference > 0 ? '큼' : '작음'}`;
}
```

- [ ] **Step 2: 검증 스크립트로 확인한다**

```bash
SP="C:/Users/Yun/AppData/Local/Temp/claude/C--Capstone/7c552804-392f-44d1-b747-066c6fcf4a97/scratchpad/fmt"; cd C:/Capstone/Frontend && npx tsc src/features/report/utils/formatMetric.ts --outDir "$SP" --module commonjs --target es2019 && node -e "
const m=require('$SP/formatMetric.js'); const a=require('assert'); const D='\u00B0';
a.strictEqual(m.formatValue(78.4,'degree'),'78'+D);
a.strictEqual(m.formatValue(71.9,'degree'),'72'+D);
a.strictEqual(m.formatValue(0.4231,null),'0.42');
a.strictEqual(m.formatValue(78.4,'radian'),'78.40');
a.strictEqual(m.formatJudgment(6.54,'degree'),'6.5'+D);
a.strictEqual(m.formatJudgment(15,'degree'),'15.0'+D);
a.strictEqual(m.formatJudgment(0.0712,null),'0.07');
a.strictEqual(m.describeDifference(6.5,'degree'),'기준보다 6.5'+D+' 큼');
a.strictEqual(m.describeDifference(-6.5,'degree'),'기준보다 6.5'+D+' 작음');
a.strictEqual(m.describeDifference(0.04,'degree'),'기준과 거의 같음');
a.strictEqual(m.describeDifference(0.07,null),'기준보다 0.07 큼');
a.strictEqual(m.describeDifference(0.004,null),'기준과 거의 같음');
console.log('ALL PASS 12');
"
```

Expected: `ALL PASS 12`

- [ ] **Step 3: 기존 코드가 깨지지 않았는지 확인한다**

이 태스크는 새 파일만 더한다. `PhaseMetricRow.tsx`는 아직 자기 안의 `describeDifference`를 쓰고 있고, 그대로 두는 것이 맞다 — 화면 배선은 Task 6이다. 같은 이름의 함수가 두 파일에 잠시 공존하지만 서로 부딪히지 않는다.

```bash
cd C:/Capstone/Frontend && npx tsc --noEmit; echo "EXIT=$?"
```

Expected: `EXIT=0`

- [ ] **Step 4: 커밋**

```bash
cd C:/Capstone/Frontend && git add src/features/report/utils/formatMetric.ts && git commit -m "리포트: 지표 표기 함수를 단위별로 분리"
```

---

### Task 6: 앱 배선 — `unit` 전달과 화면 반영

**Files:**
- Modify: `src/api/analysisApi.ts` (`PhaseMetricDetail`)
- Modify: `src/features/report/types/report.types.ts` (`PhaseMetric`)
- Modify: `src/features/report/utils/mapReport.ts` (`groupMetricsByPhase`)
- Modify: `src/features/report/components/PhaseMetricRow.tsx` (값 줄과 게이지 캡션)

**Interfaces:**
- Consumes: Task 5의 `formatValue`, `formatJudgment`, `describeDifference`
- Produces: `PhaseMetric.unit: string | null`이 화면까지 흐른다

- [ ] **Step 1: API 타입에 `unit`을 추가한다**

`src/api/analysisApi.ts`의 `PhaseMetricDetail`에서 `label: string;` 다음 줄에 넣는다. 기존 `userValue` 위 주석도 함께 고친다 — 이제 단위가 있을 수 있다:

```ts
export interface PhaseMetricDetail {
  phase: string;
  key: string;
  label: string;
  /** "degree"면 도(°) 단위. null이면 단위 없는 body-frame 정규화 좌표. */
  unit?: string | null;
  /** 단위는 unit이 정한다. 각도가 아니면 정규화 좌표라 화면에서 단위를 붙이지 않는다. */
  userValue: number | null;
```

- [ ] **Step 2: 화면 타입에 `unit`을 추가한다**

`src/features/report/types/report.types.ts`의 `PhaseMetric`에서 `label: string;` 다음 줄에 넣는다:

```ts
export interface PhaseMetric {
  key: string;
  label: string;
  /** "degree"면 도(°) 단위. null이면 단위 없는 정규화 좌표. */
  unit: string | null;
  userValue: number | null;
```

- [ ] **Step 3: 매퍼가 `unit`을 옮기게 한다**

`src/features/report/utils/mapReport.ts`의 `groupMetricsByPhase` 안 `list.push({ ... })`에서 `label: m.label,` 다음 줄에 넣는다:

```ts
      label: m.label,
      unit: m.unit ?? null,
```

- [ ] **Step 4: 값 줄과 게이지 캡션에 표기 함수를 적용한다**

먼저 `PhaseMetricRow.tsx` 안에 있는 **기존 `describeDifference` 함수 정의를 그 위 주석 블록까지 통째로 지운다.** Task 5의 모듈이 단위를 받는 버전을 갖고 있고, 두 개를 남겨두면 나중에 한쪽만 고치게 된다.

그리고 import를 아래로 맞춘다:

```ts
import { describeDifference, formatJudgment, formatValue } from '../utils/formatMetric';
```

값 줄(`나 ... · 기준 ...`)을 아래로 바꾼다:

```tsx
          <AppText className="text-text-secondary text-xs">
            나 {formatValue(metric.userValue, metric.unit)}  ·  기준 {formatValue(metric.proValue, metric.unit)}
          </AppText>
```

`ThresholdGauge`의 캡션 줄에 허용치를 넣는다. 지금은 `작음`/`큼`만 있는데, 허용 범위를 띠로 그려놓고 값을 문구로도 주면 게이지를 읽는 근거가 된다. `ThresholdGauge`의 props에 `unit: string | null`을 더하고 캡션을 아래로 바꾼다:

```tsx
      <View className="flex-row justify-between mt-1">
        <AppText className="text-text-secondary text-[10px]">작음</AppText>
        <AppText className="text-text-secondary text-[10px]">
          허용 ±{formatJudgment(threshold, unit)}
        </AppText>
        <AppText className="text-text-secondary text-[10px]">큼</AppText>
      </View>
```

호출부에 `unit={metric.unit}`을 넘긴다:

```tsx
          <ThresholdGauge
            difference={metric.difference}
            threshold={metric.threshold}
            unit={metric.unit}
            color={style.color}
          />
```

캡션이 허용치를 갖게 됐으므로, 아래 문구 줄에서 중복되는 `· 허용 ±...`를 뺀다:

```tsx
          <AppText weight="medium" className="text-text-primary text-xs mb-1">
            {describeDifference(metric.difference, metric.unit)}
          </AppText>
```

- [ ] **Step 5: 타입 검사로 확인한다**

```bash
cd C:/Capstone/Frontend && npx tsc --noEmit; echo "EXIT=$?"
```

Expected: `EXIT=0`

- [ ] **Step 6: 번들이 만들어지는지 확인한다**

```bash
cd C:/Capstone/Frontend && npx expo export --platform android 2>&1 | tail -5; echo "EXIT=${PIPESTATUS[0]}"
```

Expected: `Exported: dist`와 `EXIT=0`

- [ ] **Step 7: 커밋**

`git add .`을 쓰지 말 것 — `app.json`, `eas.json`, `.env.backup-cloudrun`이 딸려 들어간다.

```bash
cd C:/Capstone/Frontend && git add src/api/analysisApi.ts src/features/report/types/report.types.ts src/features/report/utils/mapReport.ts src/features/report/components/PhaseMetricRow.tsx && git commit -m "리포트: 각도 지표를 단위에 맞춰 표시"
```

---

## 완료 후 남는 일

- **실기기 확인.** 분석 서버(5020)·백엔드(8080)·PostgreSQL·Redis가 모두 떠 있어야 실제 각도를 볼 수 있다. **사용자에게 먼저 물어볼 것** — 지난번에 사용 중인 기기에 재설치해 세션을 끊은 적이 있다.
- **임계값 조정.** 대부분의 투구가 `warn`이거나 반대로 전부 `good`이면 15°/10°가 틀린 것이다. `joint_angles.py`의 `ANGLE_RULES` 한곳에서 바꾼다.
- **펼침 패널 확인.** 구간당 지표가 3~4개가 되면서 이전 스펙의 열린 항목이던 "펼친 패널이 얇다"가 해소되는지 본다.
