# exp08 실영상 검증 노트 템플릿

이 파일은 `docs/exp08_validation_plan.md` 기준으로 실제 검증을 실행한 뒤 `outputs/exp08_service_api_validation/notes.md`에 복사해서 사용하는 템플릿입니다.

## 검증 기본 정보

- 검증 일시:
- 실행자:
- 사용자 영상: `/Users/sonjiwoon/capstone/user_data/y1.mp4`
- 프로 reference: 백엔드 DB 또는 검증 fixture의 `pro_skeleton_data`
- 서버 경로: `/Users/sonjiwoon/capstone/integreted/server`
- 응답 저장 위치: `/Users/sonjiwoon/capstone/Analysis_algorithm/outputs/exp08_service_api_validation/exp08_response.json`

## 실행 환경

- Python 버전:
- MediaPipe 설치 여부:
- 서버 주소: `http://127.0.0.1:5020`
- 사용자 skeleton 생성 방식:
- 프로 skeleton reference 개수:

## 자동 점검 결과

- 기본 검증 명령 결과:
- 엄격 모드 검증 명령 결과:
- 오류:
- 경고:

## 응답 요약

- `responseSchemaVersion`:
- `algorithmName`:
- `scoreScale`:
- `cameraView`:
- `user_data.skeleton_data` 크기:
- `players` 개수:
- Top 1 `proId`:
- Top 1 `overallScore`:

## Top 1 phaseScores 확인

| phase | score | userStartFrame | userEndFrame | proStartFrame | proEndFrame | 판단 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| leg_lift |  |  |  |  |  |  |
| stride |  |  |  |  |  |  |
| release |  |  |  |  |  |  |
| follow_through |  |  |  |  |  |  |

## normalization 확인

- 사용자 throwingSide:
- 프로 throwingSide:
- 사용자 medianBodyScale:
- 프로 medianBodyScale:
- mirror 적용 여부:

## 프론트 표시용 변환 확인

- `display_keypoints_user.json` 생성 여부:
- 선택된 프로 reference displayKeypoints 생성 여부:
- phase 매핑 포함 여부:
- 0~1 좌표 범위 이상 여부:

## 관찰 결과

- 잘 된 점:
- 이상한 점:
- 사람이 봤을 때 phase 경계가 납득 가능한가:
- 릴리즈 구간이 너무 짧게 잡히는가:
- keypoints CSV 저장 크기가 백엔드 DB에 부담스러운가:

## 판정

- 최종 판정: 통과 / 보류 / 실패
- 판정 이유:

## 다음 작업

- 통과 시:
- 보류/실패 시:
