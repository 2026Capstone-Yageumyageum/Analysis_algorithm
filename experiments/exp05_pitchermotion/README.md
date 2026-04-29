# exp05_pitchermotion

원래 실험 ID: `pitchermotion_style_exp1_y1_ryu`

## 목적

프로 선수와 사용자 스켈레톤을 같은 좌표계에 겹쳐 보고, 유사도 계산에 사용할 특징값 후보를 확인합니다.

## 입력 데이터

- 사용자 영상: `/Users/sonjiwoon/capstone/user_data/y1.mp4`
- 프로 영상: `/Users/sonjiwoon/capstone/pro_data/hyun_jin_ryu_ball_to_junior_caminero_20230923_6s.mp4`
- 결과 경로: `/Users/sonjiwoon/capstone/exp/result/pitchermotion/exp1`

## 방법

MediaPipe Pose 2D 관절 좌표를 사용했습니다. 다리 들기 시점을 기준점으로 두고, 골반 중심과 신체 크기 기준으로 정규화한 스켈레톤을 겹쳐 보았습니다. 관절 각도, 손목 높이, 보폭 이동, 몸통 기울기 그래프도 생성했습니다.

## 관찰 결과

정규화 스켈레톤 겹쳐보기와 주요 특징값 그래프를 만들 수 있었습니다. 이 결과를 통해 유사도 점수 계산 전에 어떤 특징값이 비교에 유용한지 시각적으로 확인할 수 있었습니다.

## 문제점

프로와 사용자의 릴리즈 시점이 다르게 나타났습니다. 다리 들기 기준만으로는 전체 투구 흐름을 충분히 맞추기 어렵습니다.

## 유사도 알고리즘에 주는 의미

PitcherMotion 스타일 실험은 최종 유사도 알고리즘 자체가 아니라, 유사도 계산 전 특징값과 시각화 방식을 검증하는 중간 표현입니다.

## 현재 결정

PitcherMotion 스타일 결과는 특징값 추출과 시각 검증 단계로 유지합니다.
