# exp03_ryu_temporal

원래 실험 ID: `temporal_exp1_ryu_mediapipe_height`

## 목적

류현진 프로 영상에서 시간축 정규화 실험의 기준선을 만듭니다.

## 입력 데이터

- 프로 영상: `/Users/sonjiwoon/capstone/pro_data/hyun_jin_ryu_ball_to_junior_caminero_20230923_6s.mp4`
- 결과 경로: `/Users/sonjiwoon/capstone/exp/result/temporal/exp1/hyun_jin_ryu_ball_to_junior_caminero_20230923_6s_08abc2ff`

## 방법

MediaPipe Pose 2D 관절 좌표와 키 기준 정규화를 사용해 시간축 비교를 준비했습니다.

## 관찰 결과

류현진 영상의 시간축 정규화 목적 기준 결과를 만들었습니다.

## 문제점

이 단계에서는 동적 시간 정렬(DTW)이 안정적으로 연결되지 않았습니다. 전체 영상을 한 번에 비교하면 의미가 다른 구간끼리 맞춰질 위험이 있습니다.

## 유사도 알고리즘에 주는 의미

시간축 정규화는 단순히 전체 프레임을 맞추는 방식보다, 투구 구간을 먼저 나눈 뒤 같은 의미의 구간끼리 비교하는 방식이 필요합니다.

## 현재 결정

전체 영상 단위 시간축 정렬은 핵심 방법으로 두지 않고, 구간별 비교로 넘어갑니다.
