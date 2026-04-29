# exp04_user_temporal

원래 실험 ID: `temporal_exp2_y2_mediapipe_height`

## 목적

사용자 y2 영상에서 시간축 정규화 기준선을 만들고, 사용자 영상의 구간별 비교 필요성을 확인합니다.

## 입력 데이터

- 사용자 영상: `/Users/sonjiwoon/capstone/user_data/y2.mp4`
- 프로 영상 기준: `/Users/sonjiwoon/capstone/pro_data/hyun_jin_ryu_ball_to_junior_caminero_20230923_6s.mp4`
- 결과 경로: `/Users/sonjiwoon/capstone/exp/result/temporal/exp2/y2_a6b2b25c`

## 방법

MediaPipe Pose 2D 관절 좌표와 키 기준 정규화를 사용했습니다. 전체 시간축 정렬 가능성을 확인했습니다.

## 관찰 결과

사용자 y2 영상의 시간축 비교 기준선을 만들었습니다.

## 문제점

세로 영상 특성 때문에 관심영역 편차가 남고, 전체 영상 기준으로 정렬하기 어렵습니다.

## 유사도 알고리즘에 주는 의미

사용자 영상은 프로 영상과 준비 구간 길이, 동작 속도, 촬영 구도가 다를 수 있으므로 전체 영상 비교보다 투구 구간별 비교가 더 적합합니다.

## 현재 결정

투구 구간을 먼저 나눈 뒤 구간별 특징값 흐름을 비교하는 방식으로 정리합니다.
