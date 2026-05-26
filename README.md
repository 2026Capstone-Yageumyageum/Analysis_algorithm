# Analysis Algorithm

프로 선수와 사용자 투구 영상을 비교하기 위한 유사도 알고리즘 실험 저장소입니다.

현재 단계에서는 유사도 알고리즘 v1을 서비스 API에 붙일 수 있는 수준으로 정리하는 데 집중합니다.

## 현재 서비스 v1 기준

서비스 연동 후보는 다음 기준으로 정리합니다.

- MediaPipe 2D 관절 좌표 추출
- 좌완/우완 방향 통일
- 골반 중심, 몸통 기준, body-scale 단위 정규화
- setup, leg lift, stride, release, follow-through 구간 분할
- phase별 시작-끝 body-frame 방향 벡터 비교
- 관절 confidence 기반 phase 점수 가중 평균
- phase별 가중 평균 기반 `overallScore`
- 원본 영상 미저장, 사용자 skeleton CSV와 Top 3 점수 JSON 저장

DTW, phase 내부 흐름 비교, 정규화 스켈레톤 오버레이 영상은 과거 실험 또는 다음 고도화 후보로 보관합니다. 현재 서비스 API v1 계산식에는 포함하지 않습니다.

## 서비스 API 연동 방향

현재 서비스 연동 방향은 다음과 같습니다.

- 사용자 영상과 프로 skeleton reference는 후면 촬영 기준으로 비교합니다.
- 원본 영상은 서버에 장기 저장하지 않습니다.
- Python 서버는 사용자 영상 처리 후 `user_data.skeleton_data`, `user_data.keypointsCsvText`, frame 정보, 프로 reference Top 3 비교 결과를 반환합니다.
- 백엔드는 사용자 skeleton CSV를 DB에 저장하고, 프로 skeleton CSV는 reference 데이터로 관리합니다.
- 백엔드는 프론트 조회 시 사용자/pro skeleton CSV를 표시용 skeleton JSON으로 변환합니다.
- 프론트는 사용자가 기기에 저장한 원본 영상 위에 skeleton을 그립니다.

관련 문서:

- `docs/service_api_contract.md`
- `docs/openapi.yaml`
- `docs/backend_integration_guide.md`
- `docs/service_handoff_checklist.md`
- `docs/keypoints_csv_schema.md`
- `docs/scoring_policy.md`
- `docs/frontend_skeleton_rendering.md`
- `docs/service_response_mock.md`
- `docs/exp08_validation_plan.md`
- `docs/goal_status.md`
- `idea.md`

서비스 코드 위치:

- `service/server`
- `service/web`

주요 구현 파일:

- `service/server/app.py`
- `service/server/analysis/pose.py`
- `service/server/analysis/normalization.py`
- `service/server/analysis/phase.py`
- `service/server/analysis/similarity.py`
- `service/server/analysis/speed.py`
- `service/server/analysis/video.py`

프론트 표시용 keypoints 변환 참조 구현:

- `scripts/keypoints_csv_to_display_keypoints.py`

서비스 응답 검증 참조 구현:

- `scripts/validate_pitch_analysis_response.py`
- `scripts/run_exp08_service_validation.sh`

## 서비스 API 실행

레포 안에 포함된 서비스 API 스캐폴드는 `service/server`에서 실행합니다.

```bash
cd service/server
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python app.py
```

기본 주소는 `http://127.0.0.1:5020` 입니다. 프로 skeleton reference는 `PRO_SKELETON_DATA_URL` 또는 `PRO_SKELETON_DATA_FILE`로 서버 시작/갱신 시 캐싱합니다.

## 기본 실행

Python 3.11 사용을 권장합니다.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/run_pair_experiment.py
```

기본 입력 쌍은 다음과 같습니다.

- 프로 영상: `/Users/sonjiwoon/capstone/pro_data/hyun_jin_ryu_ball_to_junior_caminero_20230923_6s.mp4`
- 사용자 영상: `/Users/sonjiwoon/capstone/user_data/y1.mp4`

실행 결과는 `outputs/expN`에 저장되며, 이 폴더는 커밋하지 않습니다.

---

# ⚾ 기여 가이드라인 (Contributing Guidelines)

일관된 코드 품질과 효율적인 협업을 위해 아래 규칙을 준수해 주세요.

---

## 1. 브랜치 전략 (Branching Strategy)

우리는 **Git Flow**를 단순화한 방식을 사용합니다.

* `issue_key/`: 모든 브랜치 앞에 붙여야하는 Jira 이슈 키입니다.
* `main`: 언제든 배포 가능한 상태의 안정적인 브랜치입니다.
* `develop`: 다음 버전을 위해 개발이 진행되는 통합 브랜치입니다.
* `feature/기능명`: 새로운 기능 개발이나 버그 수정을 위한 브랜치입니다.
    * 예: `feature/login-api`, `feature/pitch-analysis-model`
* `hotfix/버그명`: 배포된 버전에서 급하게 수정이 필요한 경우 사용합니다.

## **예시**
* `issue_key/feature/기능명`
---

## 2. 커밋 컨벤션 (Commit Convention)

커밋 메시지는 아래의 형식을 반드시 지켜주세요.

### **형식**
`issue_key/Tag(Scope): 요약 메시지`

### **태그(Tag) 종류**
| 태그 | 설명 |
| :--- | :--- |
| **Feat** | 새로운 기능 추가 |
| **Fix** | 버그 수정 |
| **Docs** | 문서 수정 (README, Wiki 등) |
| **Style** | 코드 포맷팅, 세미콜론 누락 등 (코드 변경 없음) |
| **Refactor** | 코드 리팩토링 |
| **Test** | 테스트 코드 추가 및 수정 |
| **Chore** | 빌드 업무, 패키지 매니저 설정, 단순 작업 |

### **스코프 (Scope) 종류**
| 파트 |  스코프 종류 | 설명 |
| :--- | :---| :---|
| **FrontEnd** | web, ui, store, hook 등 | 프론트엔드의 각 분야 |
| **BackEnd** | api, db, auth, dto 등 | 백엔드의 각 분야 |
| **AI/Analysis** | model, data, preprocess, inference 등 | 분석 과정의 각 분야 |
| **Common** | infra, ci, env | 개발 환경 등 기타 분야 |

### **예시**
* `issue_key/Feat(api): 피칭 폼 분석 결과 API 연동`
* `issue_key/Fix(ui): 모바일 화면에서 영상 업로드 버튼 깨짐 수정`
* `issue_key/Docs: 분석 모델 서빙 방법 README 업데이트`

---

## 3. 이슈 및 풀 리퀘스트 (Issue & PR)

### **이슈 생성 (Issue)**
* 새로운 작업을 시작하기 전 반드시 이슈를 생성합니다.
* Jira를 사용하여 이슈를 생성합니다.

### **풀 리퀘스트 (Pull Request)**
* 모든 코드는 PR을 통해 `develop` 브랜치로 병합됩니다.
* 최소 **1명 이상의 리뷰어**에게 승인(Approve)을 받아야 Merge할 수 있습니다.
* PR 제목은 커밋 메시지 컨벤션과 동일하게 작성합니다.

---

## 4. 코드 스타일 (Code Style)

각 레포지토리의 특성에 맞는 린터(Linter)와 포맷터(Formatter)를 사용합니다.

* **Frontend (React/TypeScript):** ESLint, Prettier
* **Backend (Kotlin/Spring):** ktlint
* **AI/Analysis (Python):** Black, Flake8

---

## 5. 문의 및 커뮤니케이션

프로젝트 진행 중 궁금한 점이 있다면 아래 채널을 이용해 주세요.
* **Jira:** 기술적인 문제나 기능 제안
* **Notion:** 자유로운 의견 교환

---
