# exp02_mediapipe_height

원래 실험 ID: `spatial_exp15_ryu_mediapipe_envelope`

## 목적

MediaPipe 기준으로 류현진 영상의 공간 정규화 기준선을 다시 만들고, 키 기준 정규화의 한계를 확인합니다.

## 입력 데이터

- 프로 영상: `/Users/sonjiwoon/capstone/pro_data/hyun_jin_ryu_ball_to_junior_caminero_20230923_6s.mp4`
- 결과 경로: `/Users/sonjiwoon/capstone/exp/result/spatial/exp15/hyun_jin_ryu_ball_to_junior_caminero_20230923_6s_d799fa53`

## 방법

MediaPipe Pose 2D 관절 좌표를 사용하고, 키 기준 공간 정규화를 적용했습니다. 입력은 투수 전신이 안정적으로 보이는 것을 우선했습니다.

## 관찰 결과

MediaPipe 기준 공간 정규화의 최신 기준선을 만들 수 있었습니다.

## 문제점

키 기준 정규화만으로는 카메라 시점 차이, 원근감, 투수의 전후 이동에 따른 화면상 크기 변화를 충분히 줄이지 못했습니다.

## 유사도 알고리즘에 주는 의미

키 기준 정규화는 공간 정규화의 기본 출발점이지만, 최종 유사도 비교에서는 골반 중심 상대좌표와 몸통/신체 크기 기준 보정을 함께 고려해야 합니다.

## 현재 결정

현재 공간 정규화는 키 기준에서 출발하되, 이후 신체 구조 기준 정규화를 함께 사용하는 방향으로 정리합니다.
