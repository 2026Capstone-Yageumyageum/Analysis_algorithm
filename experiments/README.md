# Experiments

이 폴더는 유사도 알고리즘 실험별 상세 기록을 보관하기 위한 위치입니다.

현재 단계에서는 대용량 영상 결과물을 직접 저장하지 않고, 각 실험의 설정과 관찰 결과를 문서로 남깁니다.

## 폴더명 규칙

```text
exp01_pose_model/
exp02_mediapipe_height/
exp03_ryu_temporal/
```

폴더명은 실험 흐름을 보기 쉽도록 짧은 번호형으로 작성합니다. 기존 실험 ID는 각 실험 폴더의 `README.md` 첫 부분에 `원래 실험 ID`로 남깁니다.

RTMPose 기반 과거 실험은 별도 실험 폴더로 분리하지 않습니다. 현재 알고리즘 흐름은 MediaPipe 기준으로 정리하고, RTMPose는 `exp01_pose_model`에서 비교 근거로만 설명합니다.

## 현재 정리 순서

| 폴더 | 의미 |
| --- | --- |
| `exp01_pose_model` | RTMPose와 MediaPipe 비교 및 MediaPipe 기준 선택 |
| `exp02_mediapipe_height` | MediaPipe 기반 키 정규화 기준선 |
| `exp03_ryu_temporal` | 류현진 시간축 정규화 기준선 |
| `exp04_user_temporal` | 사용자 영상 시간축 정규화 기준선 |
| `exp05_pitchermotion` | PitcherMotion 스타일 시각화 1차 |
| `exp06_pitchermotion_preroll` | 표시 구간 보정 포함 PitcherMotion 스타일 시각화 |
| `exp07_phase_direction` | Phase 시작-끝 방향 벡터 기반 폼 유사도 B 실험 |

## 실험 폴더 권장 구조

```text
exp001_example/
  README.md
  config.yaml
  notes.md
```

## 기록해야 하는 내용

- 실험 목적
- 입력 영상
- 포즈 추정 모델
- 정규화 방식
- 투구 구간 분할 방식
- 시간축 정렬 방식
- 주요 산출물 경로
- 관찰 결과
- 문제점
- 현재 결정

## 주의사항

- 원본 영상과 대용량 mp4는 커밋하지 않습니다.
- 실험별 결과 파일 경로는 `/Users/sonjiwoon/capstone/exp/result` 기준으로 기록합니다.
- 논문에 쓸 판단 근거를 남기는 것을 우선합니다.
