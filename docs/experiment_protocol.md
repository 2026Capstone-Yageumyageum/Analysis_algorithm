# 유사도 알고리즘 실험 기록 프로토콜

## 목적

이 문서는 프로 선수와 사용자 투구 자세 유사도 측정 알고리즘을 만들기 위해 진행한 실험을 일관된 방식으로 기록하기 위한 기준입니다.

논문에 사용할 수 있도록 각 실험은 단순 결과물이 아니라 다음 질문에 답해야 합니다.

```text
이 실험이 안정적인 투구 자세 비교 알고리즘에 어떤 근거를 제공했는가?
```

## 기본 입력

기본 비교 쌍은 다음과 같습니다.

- 사용자 영상: `/Users/sonjiwoon/capstone/user_data/y1.mp4`
- 프로 영상: `/Users/sonjiwoon/capstone/pro_data/hyun_jin_ryu_ball_to_junior_caminero_20230923_6s.mp4`

다른 입력을 사용하는 경우 반드시 `results/summary.csv`와 실험 노트에 기록합니다.

## 실험 분류

실험은 다음 분류 중 하나로 정리합니다. 표의 왼쪽 값은 요약표에 쓰는 영문 코드이고, 오른쪽 설명은 팀원이 읽는 기준입니다.

| 분류 코드 | 설명 |
| --- | --- |
| `pose_model` | MediaPipe, RTMPose, MotionBERT 등 포즈 추정 모델 비교 |
| `roi_preprocess` | 자르기, 마스킹, 투수 관심영역 등 입력 영상 전처리 |
| `skeleton_stability` | 자기폐색, 관절 튐, 뼈대 깨짐 문제 분석 |
| `spatial_normalization` | 키, 골반 중심, 몸통 길이, 신체 기준 좌표계 기반 공간 정규화 |
| `phase_detection` | 준비, 다리 들기, 보폭 이동, 릴리즈 등 투구 구간 구분 |
| `temporal_alignment` | 전체 동적 시간 정렬(DTW), 구간별 동적 시간 정렬(DTW), 정규화 프레임 정렬 |
| `visualization` | 겹쳐보기 영상, 구간별 영상, PitcherMotion 스타일 시각화 |
| `similarity_feature` | 유사도 계산에 사용할 특징값 후보 설계 |

## 실험 노트 템플릿

각 실험은 가능하면 아래 구조를 따릅니다.

```markdown
# 실험 ID

## 목적

## 입력 데이터

## 방법

## 관찰 결과

## 문제점

## 유사도 알고리즘에 주는 의미

## 다음 실험
```

## 요약표 규칙

전역 요약표는 `results/summary.csv`에 둡니다.

필수 컬럼은 다음과 같습니다.

```text
date,experiment_id,category,purpose,user_video,pro_video,pose_model,normalization,phase_method,alignment_method,source_result,output_reference,observation,problem,decision,next_step,status
```

## 판단 기준

실험 해석은 아래 기준을 우선합니다.

- 뼈대가 관절에 안정적으로 붙는가?
- 투구 구간이 사람이 보기에도 납득 가능한 위치에서 나뉘는가?
- 정규화 후 카메라 시점/원근감 영향이 줄었는가?
- 동적 시간 정렬(DTW)이 의미 있는 동작끼리 정렬하는가?
- 시각화 결과가 논문 그림이나 설명에 사용할 수 있을 정도로 해석 가능한가?
- 최종 유사도 특징값으로 사용했을 때 원본 화면 픽셀 좌표보다 더 안정적인가?

## 실패 기록 규칙

실패한 실험도 삭제하지 않습니다. 실패 이유가 다음 알고리즘 선택의 근거가 되면 논문에 사용할 수 있습니다.

예시:

- 전체 영상 동적 시간 정렬(DTW)은 다리 들기 이후 릴리즈까지 안정적으로 이어지지 않았다.
- 키 기준 정규화만으로는 원근감과 전후 이동에 따른 크기 변화를 충분히 줄이지 못했다.
- MediaPipe 3D world 좌표는 정량 지표보다 시각 검토에서 뼈대 방향 문제가 커서 폐기했다.
