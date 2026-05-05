# exp06_pitchermotion_preroll

원래 실험 ID: `pitchermotion_style_exp2_y1_ryu_preroll`

## 목적

다리 들기 기준 정렬은 유지하되, 앞부분 표시 구간을 포함해 프로와 사용자 투구 동작을 더 해석하기 쉽게 보여줍니다.

## 입력 데이터

- 사용자 영상: `/Users/sonjiwoon/capstone/user_data/y1.mp4`
- 프로 영상: `/Users/sonjiwoon/capstone/pro_data/hyun_jin_ryu_ball_to_junior_caminero_20230923_6s.mp4`
- 결과 경로: `/Users/sonjiwoon/capstone/exp/result/pitchermotion/exp2`

## 방법

MediaPipe Pose 2D 관절 좌표를 사용했습니다. 다리 들기를 기준점으로 두고, 골반 중심과 신체 크기 기준 정규화를 적용했습니다. 분석 기준과 표시 기준을 분리해 다리 들기 전 구간도 함께 볼 수 있게 했습니다.

## 관찰 결과

정규화 스켈레톤과 특징값 그래프를 더 해석하기 쉬운 형태로 볼 수 있었습니다. 다리 들기 전 준비 동작 길이가 프로와 사용자 사이에서 크게 다르다는 점도 확인했습니다.

## 문제점

준비 구간 길이와 릴리즈 시점 차이가 커서, 단일 기준점 정렬만으로는 전체 투구 동작 비교가 충분하지 않습니다.

## 유사도 알고리즘에 주는 의미

분석 기준과 표시 기준을 분리해야 합니다. 또한 최종 비교에서는 전체 영상을 한 번에 맞추기보다 투구 구간별 특징값 흐름을 비교해야 합니다.

## 현재 결정

이 실험은 유사도 계산 전 시각화/특징값 추출 기준으로 유지하고, 시간축 비교는 구간별 정렬을 사용하는 방향으로 정리합니다.
