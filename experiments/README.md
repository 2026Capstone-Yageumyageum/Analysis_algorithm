# Experiments

이 폴더는 유사도 알고리즘 실험별 상세 기록을 보관하기 위한 위치입니다.

현재 단계에서는 대용량 영상 결과물을 직접 저장하지 않고, 각 실험의 설정과 관찰 결과를 문서로 남깁니다.

## 폴더명 규칙

```text
exp001_pose_model_selection/
exp002_spatial_normalization/
exp003_phase_dtw/
```

영문 폴더명은 파일 관리용이고, 문서 안에서는 한글 설명을 함께 적습니다.

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
- 다음 실험

## 주의사항

- 원본 영상과 대용량 mp4는 커밋하지 않습니다.
- 실험별 결과 파일 경로는 `/Users/sonjiwoon/capstone/exp/result` 기준으로 기록합니다.
- 논문에 쓸 판단 근거를 남기는 것을 우선합니다.
