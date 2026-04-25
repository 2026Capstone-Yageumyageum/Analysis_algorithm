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
