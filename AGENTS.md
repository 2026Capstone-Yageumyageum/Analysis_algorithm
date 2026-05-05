# AGENTS.md

## 프로젝트 목적

이 저장소는 야구 투구 영상에서 프로 선수와 사용자 간 투구 자세 유사도를 계산하기 위한 분석 알고리즘 실험을 정리하는 저장소입니다.

현재 단계의 핵심 목표는 바로 최종 유사도 점수를 구현하는 것이 아니라, 지금까지 진행한 포즈 추정, 정규화, 투구 구간 분할, 동적 시간 정렬(DTW), 시각화 실험을 논문에 사용할 수 있는 형태로 체계화하는 것입니다.

## 기본 실험 쌍

특별한 지시가 없다면 다음 영상을 기본 비교 쌍으로 사용합니다.

- 사용자 영상: `/Users/sonjiwoon/capstone/user_data/y1.mp4`
- 프로 영상: `/Users/sonjiwoon/capstone/pro_data/hyun_jin_ryu_ball_to_junior_caminero_20230923_6s.mp4`

## 현재 알고리즘 방향

현재까지의 실험 흐름상, 단순 화면 픽셀 좌표나 키 기준 정규화만으로는 카메라 시점과 원근감 차이를 충분히 줄이기 어렵습니다.

따라서 현재 유력한 방향은 다음과 같습니다.

1. MediaPipe 2D 관절 좌표를 기본 입력으로 사용합니다.
2. 좌완/우완 방향을 통일합니다.
3. 골반 중심 기준 상대좌표로 위치를 정렬합니다.
4. 몸통 길이와 신체 크기 기준으로 프레임별 크기를 정규화합니다.
5. 신체 기준 좌표계로 방향 성분을 계산합니다.
6. 준비, 다리 들기, 보폭 이동, 릴리즈, 팔로스루 등 투구 구간을 먼저 나눕니다.
7. 전체 영상이 아니라 구간별 특징값 흐름에 동적 시간 정렬(DTW)을 적용합니다.
8. 최종 유사도 특징값 후보는 관절 각도, 정규화 상대좌표, 정규화 길이, 전방/좌우 이동량입니다.

## 정리 대상

이 저장소에는 대용량 원본 영상이나 실험 산출 mp4를 직접 넣지 않습니다. 대신 아래 정보를 문서와 표로 정리합니다.

- 실험 목적
- 사용한 입력 영상 쌍
- 포즈 추정 모델
- 정규화 방식
- 투구 구간 검출 방식
- 시간축 정렬 방식
- 관찰 결과
- 문제점
- 다음 실험 방향
- 논문에 쓸 수 있는 판단 근거

## 폴더 구조

```text
Analysis_algorithm/
  README.md
  AGENTS.md
  requirements.txt
  scripts/
    run_pair_experiment.py
  src/
    analysis_algorithm/
      pose/
      normalization/
      features/
      phase/
      alignment/
      visualization/
  docs/
    experiment_protocol.md
    experiment_history.md
    current_decision.md
    paper_notes.md
  experiments/
    README.md
  results/
    summary.csv
```

## 코드 실행

현재 코드의 목적은 최종 유사도 점수를 확정하는 것이 아니라, 두 영상에서 다음 산출물을 만드는 것입니다.

- MediaPipe 기반 2D 관절 좌표
- 골반 중심, 몸통 기준, body-scale 단위의 정규화 feature
- 투구 구간 대표 프레임
- 구간별 동적 시간 정렬(DTW) 결과
- 정규화 스켈레톤 오버레이 영상

MediaPipe 호환성을 위해 Python 3.11 사용을 권장합니다. 현재 검증 기준은 `mediapipe==0.10.21`입니다.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

기본 실험 쌍으로 실행할 때는 다음 명령을 사용합니다.

```bash
python scripts/run_pair_experiment.py
```

키와 투구손을 명시하려면 다음처럼 실행합니다.

```bash
python scripts/run_pair_experiment.py \
  --pro-height-cm 191 \
  --user-height-cm 175 \
  --pro-handedness left \
  --user-handedness right
```

실행 결과는 `outputs/expN`에 생성되며, 이 폴더는 커밋하지 않습니다.

## 작업 규칙

- 이슈 키는 `YA-19`를 사용합니다.
- 커밋 메시지는 `YA-19/Tag(Scope): 요약 메시지` 형식을 따릅니다.
- 실험 기록은 기본적으로 한글로 작성합니다.
- 논문용 표현은 필요하면 `docs/paper_notes.md`에 별도로 정리합니다.
- 실험 결과는 성공/실패보다 “다음 선택에 어떤 근거가 되었는지”를 중심으로 씁니다.
- 영상 원본, 대용량 mp4, 캐시 파일은 커밋하지 않습니다.

## 현재 단계에서 하지 않을 일

- 최종 유사도 점수를 확정하지 않습니다.
- 대규모 모델 학습 코드를 추가하지 않습니다.
- 원본 영상 파일을 레포에 포함하지 않습니다.
- 검증되지 않은 실험 결과를 결론처럼 작성하지 않습니다.
