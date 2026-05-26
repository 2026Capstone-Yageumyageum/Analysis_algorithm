# 현재 알고리즘 방향성

## 현재 결론

현재까지의 실험을 바탕으로, 프로 선수와 사용자 투구 자세 유사도 비교는 다음 방향으로 진행합니다.

```text
MediaPipe 2D 관절 좌표
-> 좌완/우완 방향 통일
-> 골반 중심 기준 상대좌표
-> 몸통 길이와 신체 크기 기준 정규화
-> 신체 기준 좌표계 방향 성분 계산
-> 투구 구간 분할
-> phase별 시작-끝 방향 벡터 비교
-> 관절 confidence 기반 phase 점수 가중 평균
-> phase별 가중 평균으로 전체 점수 계산
```

구간별 동적 시간 정렬(DTW), phase 내부 방향 변화 흐름, 관절 각도, 상대좌표, 정규화 길이, 전방-좌우 이동 특징값 비교는 다음 고도화 후보로 보관합니다. 현재 서비스 API v1에는 phase 시작-끝 방향 벡터 기반 점수를 먼저 연결합니다.

## 이 방향을 선택한 이유

- RTMPose와 MediaPipe를 모두 실험했지만, 현재 정리 기준은 MediaPipe입니다. 이유는 MediaPipe가 실험 영상에서 관절 위치를 더 자연스럽게 잡고 스켈레톤 추출이 더 안정적이라고 판단했기 때문입니다.
- 스켈레톤 추출 오류는 이후 정규화와 시간축 정렬 전체에 전파되므로, 포즈 추정 안정성이 유사도 알고리즘의 첫 번째 조건입니다.
- 원본 화면 픽셀 좌표는 카메라 시점, 영상 해상도, 선수 위치 변화에 취약합니다.
- 키 기준 정규화는 현재 공간 정규화의 출발점입니다.
- 다만 키 기준 정규화만으로는 전후 이동과 원근감 변화까지 충분히 보정하지 못했습니다.
- 전체 영상에 동적 시간 정렬(DTW)을 바로 적용하면 유사하지 않은 구간을 억지로 맞추는 문제가 있었습니다.
- 투구 구간을 먼저 나누면 다리 들기, 보폭 이동, 릴리즈 등 같은 의미의 동작끼리 비교할 수 있습니다.
- 골반 중심 상대좌표와 몸통/신체 크기 정규화는 화면 위치보다 신체 구조 중심의 비교를 가능하게 합니다.
- 현재 첫 정량화 후보로는 phase 시작-끝 방향 벡터 기반 B 실험을 진행했습니다. 이 방식은 속도와 이동량 크기를 줄이고 동작 방향만 비교할 수 있지만, phase 내부의 궤적 변화는 반영하지 못합니다.
- 서비스 API 연동 단계에서는 원본 영상 저장을 피하고, Python 서버가 반환하는 사용자 `user_data.skeleton_data`, Top 3 `players` 점수 JSON만 백엔드 DB에 저장하는 방향으로 정리합니다.
- 프로 선수 skeleton CSV는 백엔드 DB의 reference 데이터로 저장하고, Python 서버 시작/갱신 시 프로 skeleton 목록 API를 통해 캐싱합니다.
- 프론트 표시는 백엔드가 사용자/pro skeleton CSV를 표시용 JSON으로 파싱한 뒤, 사용자가 기기에 저장한 원본 영상 또는 프로 영상 자산 위에 skeleton을 그리는 방식으로 진행합니다.

## 아직 해결되지 않은 문제

- 자기폐색 구간에서 팔/다리 뼈대가 깨지는 문제
- 후면/측면 영상 간 시점 차이
- 투구 구간 검출의 안정성. 현재 v1은 최소 길이 fallback으로 strict 검증을 통과했지만, fallback이 들어간 phase 경계는 시각 검토가 필요합니다.
- 릴리즈 시점 자동 검출의 신뢰도
- 가속 phase가 너무 짧게 잡히면 릴리즈 직전 방향 벡터 점수가 불안정해지는 문제. 현재는 최소 길이 fallback을 적용했습니다.
- 최종 유사도 점수의 특징값 가중치 결정

## 서비스 연동 문서

- `docs/service_api_contract.md`: 백엔드 서버와 Python 분석 서버 사이의 요청/응답 계약
- `docs/openapi.yaml`: 서비스 API 엔드포인트와 응답 스키마 OpenAPI 초안
- `docs/backend_integration_guide.md`: 백엔드 DB 저장 구조와 프론트 DTO 변환 규칙
- `docs/service_handoff_checklist.md`: 백엔드/프론트/Python 서버 인수인계 체크리스트
- `docs/keypoints_csv_schema.md`: `skeleton_data` 저장 스키마
- `docs/scoring_policy.md`: phase별 점수와 overallScore 계산 정책
- `docs/frontend_skeleton_rendering.md`: 프론트 skeleton 표시용 데이터 구조
- `docs/service_response_mock.md`: 백엔드/프론트 연동용 목업 응답과 5프레임 CSV 예시
- `docs/exp08_validation_plan.md`: 실제 영상 기반 exp08 검증 절차와 합격/보류 기준
- `docs/goal_status.md`: `/goal` 요구사항별 진행 상태와 남은 검증 항목
- `idea.md`: 유사도 알고리즘 고도화 중 떠오른 아이디어 기록
