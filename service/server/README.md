# Integrated Pitch Analysis Server

사용자 투구 영상과 서버에 캐싱된 프로 skeleton CSV reference 목록을 비교해 유사도 Top 3 결과를 반환하는 Flask API 서버입니다.

## 실행

MediaPipe Pose를 실제로 사용하려면 Python 3.11 환경을 권장합니다. `requirements.txt`는 Python 3.13 이상에서 MediaPipe 설치를 건너뛰도록 되어 있으므로, 그 경우 서버는 형식 검토용 fallback keypoints만 만들고 실제 스켈레톤 품질 검증에는 사용할 수 없습니다.

```bash
cd service/server
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python app.py
```

기본 주소는 `http://127.0.0.1:5020` 입니다.

## 모듈 책임

| 파일 | 책임 |
| --- | --- |
| `app.py` | Flask 엔드포인트, 사용자 영상 요청 검증, 프로 skeleton 캐시 사용, 임시 파일 처리, Top 3 JSON 응답 조립 |
| `analysis/pro_cache.py` | 서버 시작/갱신 시 백엔드 또는 로컬 파일에서 프로 skeleton reference 목록 로드 |
| `analysis/pose.py` | MediaPipe Pose 기반 사용자 skeleton CSV 생성과 CSV 컬럼 정의 |
| `analysis/normalization.py` | pelvis/torso/body-scale 기반 분석용 body-frame 좌표 생성 |
| `analysis/phase.py` | 후면 영상 기준 keypoints 기반 phase detection v1 |
| `analysis/similarity.py` | phase별 시작-끝 방향 벡터 점수와 `overallScore` 계산 |
| `analysis/speed.py` | 릴리즈/도착 프레임과 실제 거리 기반 TOF 구속 계산 |
| `analysis/video.py` | 영상 fps, frameCount, width, height, duration 메타데이터 추출 |

## 주요 API

### `GET /api/schema`

백엔드/프론트 연동용 스키마 메타데이터를 반환합니다.

- `responseSchemaVersion`
- 지원 카메라 방향
- 유사도 알고리즘명과 점수 범위
- 요청 필드 요약
- `keypointsCsvColumns`

### `GET /api/pro-skeleton-cache`

현재 Python 서버 메모리에 올라온 프로 skeleton reference 캐시 상태를 반환합니다.

- `status`: `ready`, `empty`, `error`
- `count`: 캐시된 프로 reference 수
- `source`: `PRO_SKELETON_DATA_URL` 또는 `PRO_SKELETON_DATA_FILE`
- `players`: 캐시된 reference 요약

### `POST /api/pro-skeleton-cache/refresh`

서버 환경변수 기준으로 프로 skeleton reference를 다시 로드합니다.

### `POST /api/analyze/similarity`

`multipart/form-data` 요청입니다.

- `userVideo`: 사용자 투구 영상 파일
- `metadata`: 분석 설정 JSON 문자열

현재 `metadata.cameraView`는 `rear`만 지원합니다. 다른 값을 보내면 `400` 오류를 반환합니다.
`metadata.user`, `metadata.speed`는 값이 있을 경우 JSON object여야 하며, 잘못된 타입은 `400` 오류로 처리합니다.

프로 skeleton reference는 요청마다 보내지 않습니다. 서버 시작 시 아래 환경변수 중 하나로 캐싱합니다.

- `PRO_SKELETON_DATA_URL`: 백엔드 프로 skeleton 목록 API
- `PRO_SKELETON_DATA_FILE`: 로컬 검증용 프로 skeleton 목록 JSON 파일

응답에는 사용자 `user_data.skeleton_data`와 `overallScore` 기준 상위 3개 `players` 결과가 포함됩니다.

현재 유사도 계산은 다음 순서입니다.

```text
사용자 skeleton CSV 생성
-> 프로 skeleton CSV 목록 순회
-> pelvis/torso/body-scale 기반 분석 좌표 생성
-> 후면 영상 기준 keypoints 기반 phase detection v1
-> phase별 시작-끝 body-frame 방향 벡터 비교
-> phase별 가중 평균으로 overallScore 계산
-> overallScore 기준 Top 3 반환
```

응답에는 백엔드 저장 편의를 위해 다음 값을 포함합니다.

- `algorithmName`
- `user_data.skeleton_data_id`
- `user_data.skeleton_data`
- `players[].overallScore`
- `players[].phaseScores`
- `players[].phaseDetection`
- `players[].normalization`

오류가 발생하면 백엔드가 처리하기 쉽도록 다음 JSON 형태로 반환합니다.

```json
{
  "status": "error",
  "error": {
    "code": "bad_request",
    "message": "userVideo 파일이 필요합니다."
  }
}
```

### `POST /api/measure/speed`

단일 영상에 대해 릴리즈 프레임과 도착 프레임 기반 구속을 계산합니다.

- `video`: 구속 측정 영상 파일
- `metadata`: `releaseFrame`, `arrivalFrame`, `targetDistanceM`, `releaseExtensionM`, `fps`

계산 조건은 `arrivalFrame > releaseFrame`, `fps > 0`, `targetDistanceM - releaseExtensionM > 0`입니다. 조건을 만족하지 않으면 `status: invalid`로 내려갑니다.
OpenCV가 영상 fps를 읽지 못해 `videoMeta.fps`가 `0`이면, 구속 계산은 요청 metadata의 `fps`를 우선 사용하고 없을 경우 내부 기본값 `60.0`을 fallback으로 사용합니다.

## 저장 정책

업로드된 사용자 영상은 임시 디렉터리에서 처리하고 요청 종료 후 삭제됩니다. 응답의 `user_data.skeleton_data`는 백엔드 DB 저장용 사용자 skeleton CSV 원문입니다. 프로 skeleton CSV는 백엔드 DB의 reference 데이터로 관리하고 Python 서버 시작/갱신 시 캐시에 로드합니다.

## 현재 한계

이 서버는 서비스 연동용 v1 후보입니다. exp08 실영상 검증에서 기본 계약과 strict 검증은 통과했지만, 일부 phase는 최소 길이 fallback 보정으로 확장됩니다. 따라서 fallback이 들어간 phase 경계는 시각 검토가 필요합니다. 특히 Python 3.13 이상 환경에서는 MediaPipe가 설치되지 않을 수 있으므로, 실제 분석 검증은 Python 3.11 기반 가상환경에서 진행해야 합니다.
