#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="/Users/sonjiwoon/capstone/Analysis_algorithm"
SERVER_URL="${SERVER_URL:-http://127.0.0.1:5020}"
OUTPUT_DIR="${OUTPUT_DIR:-${REPO_ROOT}/outputs/exp08_service_api_validation}"
USER_VIDEO="${USER_VIDEO:-/Users/sonjiwoon/capstone/user_data/y1.mp4}"
PRO_KEYPOINTS_CSV="${PRO_KEYPOINTS_CSV:-${REPO_ROOT}/outputs/exp6/pro/keypoints.csv}"
PRO_SKELETON_DATA_JSON="${PRO_SKELETON_DATA_JSON:-${OUTPUT_DIR}/pro_skeleton_data.json}"
RESPONSE_JSON="${OUTPUT_DIR}/exp08_response.json"

mkdir -p "${OUTPUT_DIR}"

echo "[1/6] Checking schema endpoint"
curl -sS "${SERVER_URL}/api/schema" > "${OUTPUT_DIR}/schema.json"

echo "[2/6] Preparing pro_skeleton_data"
python3 - "${PRO_KEYPOINTS_CSV}" "${PRO_SKELETON_DATA_JSON}" <<'PY'
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

csv_path = Path(sys.argv[1])
json_path = Path(sys.argv[2])
if not csv_path.exists():
    raise SystemExit(f"프로 skeleton CSV가 없습니다: {csv_path}")

csv_text = csv_path.read_text(encoding="utf-8")
rows = list(csv.DictReader(csv_text.splitlines()))
fps = 30.0
if len(rows) >= 2:
    try:
        t0 = float(rows[0].get("time_sec") or 0)
        t1 = float(rows[1].get("time_sec") or 0)
        if t1 > t0:
            fps = round(1.0 / (t1 - t0), 3)
    except ValueError:
        pass

payload = [
    {
        "proId": "123123213",
        "playerName": "류현진",
        "skeletonDataId": "pro_skeleton_ryu_exp6",
        "skeleton_data": csv_text,
        "frameCount": len(rows),
        "fps": fps,
        "resolution": "1280x720",
    }
]
json_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
PY

echo "[3/7] Refreshing server pro skeleton cache"
curl -sS -X POST "${SERVER_URL}/api/pro-skeleton-cache/refresh" > "${OUTPUT_DIR}/pro_cache_refresh.json"
python3 - "${OUTPUT_DIR}/pro_cache_refresh.json" "${PRO_SKELETON_DATA_JSON}" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
pro_json = Path(sys.argv[2])
if int(payload.get("count") or 0) <= 0:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    raise SystemExit(
        "프로 skeleton cache가 비어 있습니다. 서버를 시작할 때 "
        f"PRO_SKELETON_DATA_FILE={pro_json} 환경변수를 지정한 뒤 다시 실행해 주세요."
    )
PY

echo "[4/7] Requesting similarity analysis"
curl -sS \
  -X POST "${SERVER_URL}/api/analyze/similarity" \
  -F "userVideo=@${USER_VIDEO}" \
  -F 'metadata={
    "videoId":"y1",
    "analysisType":"pro_similarity",
    "pitchType":"직구",
    "cameraView":"rear",
    "user":{"videoId":"y1"}
  }' \
  > "${RESPONSE_JSON}"

echo "[5/7] Splitting response payload"
python3 - "${RESPONSE_JSON}" "${OUTPUT_DIR}" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

response_path = Path(sys.argv[1])
output_dir = Path(sys.argv[2])
payload = json.loads(response_path.read_text(encoding="utf-8"))

if payload.get("status") == "error":
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    raise SystemExit("API returned error response.")

user_data = payload.get("user_data") or {}
(output_dir / "keypoints_user.csv").write_text(user_data.get("skeleton_data", ""), encoding="utf-8")
(output_dir / "players.json").write_text(json.dumps(payload.get("players") or [], ensure_ascii=False, indent=2), encoding="utf-8")
PY

echo "[6/7] Validating response contract"
python3 "${REPO_ROOT}/scripts/validate_pitch_analysis_response.py" "${RESPONSE_JSON}" \
  > "${OUTPUT_DIR}/exp08_validation_stdout.txt"

echo "[7/7] Validating response contract in strict mode"
if python3 "${REPO_ROOT}/scripts/validate_pitch_analysis_response.py" "${RESPONSE_JSON}" --strict \
  > "${OUTPUT_DIR}/exp08_validation_strict_stdout.txt"; then
  echo "strict validation passed"
else
  echo "strict validation failed; see ${OUTPUT_DIR}/exp08_validation_strict_stdout.txt"
fi

echo "[extra] Building displayKeypoints reference JSON"
python3 "${REPO_ROOT}/scripts/keypoints_csv_to_display_keypoints.py" \
  --csv "${OUTPUT_DIR}/keypoints_user.csv" \
  --phase-json "${RESPONSE_JSON}" \
  --target user \
  --output "${OUTPUT_DIR}/display_keypoints_user.json"

python3 "${REPO_ROOT}/scripts/keypoints_csv_to_display_keypoints.py" \
  --csv "${PRO_KEYPOINTS_CSV}" \
  --phase-json "${RESPONSE_JSON}" \
  --target pro \
  --output "${OUTPUT_DIR}/display_keypoints_top_pro.json"

if [[ ! -f "${OUTPUT_DIR}/notes.md" ]]; then
  cat > "${OUTPUT_DIR}/notes.md" <<'MD'
# exp08 실영상 검증 노트

`experiments/exp08_service_api_scaffold/validation_notes_template.md`를 기준으로 이 파일을 채웁니다.

## 자동 생성 파일

- `schema.json`
- `pro_cache_refresh.json`
- `exp08_response.json`
- `exp08_validation_stdout.txt`
- `exp08_validation_strict_stdout.txt`
- `keypoints_user.csv`
- `pro_skeleton_data.json`
- `players.json`
- `display_keypoints_user.json`
- `display_keypoints_top_pro.json`
MD
fi

echo "Done. Outputs saved to ${OUTPUT_DIR}"
