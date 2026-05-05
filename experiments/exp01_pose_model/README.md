# exp01_pose_model

원래 실험 ID: `prior_pose_model_review`

## 목적

초기 실험에서 RTMPose와 MediaPipe를 모두 사용한 흐름을 정리하고, 스켈레톤 추출 정확도 관점에서 현재 기준 모델을 MediaPipe로 선택한 이유를 남깁니다.

## 입력 데이터

- 사용자 영상: `/Users/sonjiwoon/capstone/user_data/y1.mp4`
- 프로 영상: `/Users/sonjiwoon/capstone/pro_data/hyun_jin_ryu_ball_to_junior_caminero_20230923_6s.mp4`
- 참고 기록: `/Users/sonjiwoon/capstone/prior_exp/2026-04-10_root_pitch_experiments/result/experiment_journal.md`

## 방법

초기 실험 저널과 `exp/summary.csv`를 기준으로 MediaPipe와 RTMPose 사용 기록을 비교했습니다. 비교 기준은 관절이 실제 팔, 다리, 몸통 위치에 얼마나 안정적으로 붙는지와 투구 동작 중 뼈대가 얼마나 덜 깨지는지였습니다.

## 관찰 결과

초기에는 환경 문제 때문에 RTMPose 결과가 많이 남아 있지만, 시각적으로 확인했을 때 MediaPipe가 투수의 팔, 다리, 몸통 관절을 더 자연스럽게 잡는 경우가 많았습니다. RTMPose는 일부 구간에서 관절 연결이 어색하거나, 투구 동작 중 스켈레톤이 튀는 문제가 더 크게 보였습니다.

이후 공간 정규화, 시간축 정렬, PitcherMotion 스타일 시각화 실험은 MediaPipe 2D 관절 좌표를 중심으로 이어졌습니다.

## 문제점

RTMPose 결과에서는 일부 투구 구간에서 관절 연결이 어색하게 튀거나, 팔과 다리 위치가 실제 관절과 다르게 잡히는 문제가 있었습니다. 특히 투구처럼 팔이 빠르게 움직이고 자기폐색이 생기는 동작에서는 스켈레톤 추출 오류가 후속 정규화와 시간축 비교 전체에 영향을 줍니다.

## 유사도 알고리즘에 주는 의미

유사도 알고리즘의 입력은 포즈 추정 결과이므로, 스켈레톤이 실제 관절에 안정적으로 붙지 않으면 이후 정규화나 동적 시간 정렬을 적용해도 의미 있는 비교가 어렵습니다. 따라서 이 실험은 유사도 알고리즘에서 가장 먼저 포즈 추정 안정성을 확보해야 한다는 근거가 됩니다.

## 현재 결정

현재 유사도 알고리즘 정리는 MediaPipe 2D 관절 좌표를 기준으로 진행합니다. 선택 이유는 MediaPipe가 현재 실험 영상에서 RTMPose보다 스켈레톤 추출이 더 안정적이고, 관절 위치가 더 자연스럽게 잡힌다고 판단했기 때문입니다.
