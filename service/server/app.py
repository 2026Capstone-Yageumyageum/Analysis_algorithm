from __future__ import annotations

import json
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from flask import Flask, jsonify, render_template, request
from werkzeug.datastructures import FileStorage
from werkzeug.exceptions import HTTPException, ServiceUnavailable
from werkzeug.utils import secure_filename

from analysis.pro_cache import cache_status, get_cached_pro_skeletons, refresh_pro_skeleton_cache
from analysis.pose import CSV_COLUMNS, extract_skeleton_data_csv_text
from analysis.similarity import compute_similarity
from analysis.speed import compute_tof_speed
from analysis.video import inspect_video


SERVER_ROOT = Path(__file__).resolve().parent
INTEGRATED_ROOT = SERVER_ROOT.parent
WEB_ROOT = INTEGRATED_ROOT / "web"
ALLOWED_EXTENSIONS = {".mp4", ".mov", ".avi", ".m4v"}
SUPPORTED_CAMERA_VIEW = "rear"
RESPONSE_SCHEMA_VERSION = "pitch_analysis_response_v1"
SIMILARITY_ALGORITHM_NAME = "body_frame_phase_direction_vector_v1"
SCORE_SCALE = "0~100"

app = Flask(
    __name__,
    template_folder=str(WEB_ROOT / "templates"),
    static_folder=str(WEB_ROOT / "static"),
)
app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024 * 1024
app.config["SECRET_KEY"] = "integrated-local-dev"


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "service": "integrated-pitch-analysis"})


@app.get("/api/schema")
def schema():
    return jsonify(
        {
            "status": "ok",
            "responseSchemaVersion": RESPONSE_SCHEMA_VERSION,
            "supportedCameraViews": [SUPPORTED_CAMERA_VIEW],
            "similarity": {
                "algorithmName": SIMILARITY_ALGORITHM_NAME,
                "scoreScale": SCORE_SCALE,
                "phases": ["leg_lift", "stride", "release", "follow_through"],
            },
            "request": {
                "similarity": {
                    "method": "POST",
                    "path": "/api/analyze/similarity",
                    "contentType": "multipart/form-data",
                    "requiredFiles": ["userVideo"],
                    "requiredFields": [],
                    "metadataField": "metadata",
                    "proSkeletonSource": "server_cache",
                },
                "speed": {
                    "method": "POST",
                    "path": "/api/measure/speed",
                    "contentType": "multipart/form-data",
                    "requiredFiles": ["video"],
                    "metadataField": "metadata",
                },
            },
            "keypointsCsvColumns": CSV_COLUMNS,
            "proSkeletonCache": cache_status(),
        }
    )


@app.get("/api/pro-skeleton-cache")
def pro_skeleton_cache():
    return jsonify(cache_status())


@app.post("/api/pro-skeleton-cache/refresh")
def refresh_pro_skeletons():
    return jsonify(refresh_pro_skeleton_cache())


@app.post("/api/analyze/similarity")
def analyze_similarity():
    user_upload = _required_file("userVideo")
    pro_skeleton_data = get_cached_pro_skeletons()
    if not pro_skeleton_data:
        raise ServiceUnavailable("프로 skeleton 캐시가 비어 있습니다. 서버 시작 시 백엔드에서 프로 데이터를 받아오도록 설정해 주세요.")
    metadata = _parse_metadata()
    _validate_similarity_metadata(metadata)
    user_metadata = _metadata_object(metadata, "user")
    video_id = str(metadata.get("videoId") or user_metadata.get("videoId") or f"user_video_{uuid4().hex[:10]}")
    skeleton_data_id = str(
        user_metadata.get("skeletonDataId")
        or user_metadata.get("skeleton_data_id")
        or f"user_skeleton_{uuid4().hex[:10]}"
    )

    with tempfile.TemporaryDirectory(prefix="integrated_pitch_") as tmp_dir_name:
        tmp_dir = Path(tmp_dir_name)
        user_path = _save_temp_upload(user_upload, tmp_dir, "user")

        user_meta = inspect_video(user_path)
        max_frames = _parse_optional_int(metadata.get("maxFrames"))
        user_csv_text, user_pose_meta = extract_skeleton_data_csv_text(user_path, max_frames=max_frames)
        players = _rank_player_matches(user_csv_text, pro_skeleton_data)

    return jsonify(
        {
            "videoId": video_id,
            "status": "completed",
            "responseSchemaVersion": RESPONSE_SCHEMA_VERSION,
            "analysisType": metadata.get("analysisType") or "pro_similarity",
            "pitchType": metadata.get("pitchType") or "직구",
            "cameraView": SUPPORTED_CAMERA_VIEW,
            "processedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
            "algorithmName": SIMILARITY_ALGORITHM_NAME,
            "scoreScale": SCORE_SCALE,
            "user_data": {
                "skeleton_data_id": skeleton_data_id,
                "skeleton_data": user_csv_text,
                "frame_count": int(user_pose_meta.get("frameCount") or user_meta.get("frameCount") or 0),
                "fps": float(user_meta.get("fps") or 0.0),
                "resolution": _format_resolution(user_meta),
            },
            "players": players,
        }
    )


@app.post("/api/measure/speed")
def measure_speed():
    upload = _required_file("video")
    metadata = _parse_metadata()
    with tempfile.TemporaryDirectory(prefix="integrated_speed_") as tmp_dir_name:
        video_path = _save_temp_upload(upload, Path(tmp_dir_name), "speed")
        video_meta = inspect_video(video_path)
        speed_result = compute_tof_speed(metadata, detected_fps=float(video_meta.get("fps") or 60.0))
    return jsonify(
        {
            "status": speed_result.get("status"),
            "videoMeta": video_meta,
            "speed": speed_result,
        }
    )


def _required_file(field_name: str) -> FileStorage:
    upload = request.files.get(field_name)
    if upload is None or not upload.filename:
        raise ValueError(f"{field_name} 파일이 필요합니다.")
    if Path(upload.filename).suffix.lower() not in ALLOWED_EXTENSIONS:
        raise ValueError(f"{field_name}은 mp4/mov/avi/m4v만 지원합니다.")
    return upload


def _save_temp_upload(upload: FileStorage, tmp_dir: Path, prefix: str) -> Path:
    safe_name = secure_filename(Path(upload.filename).name) or f"{prefix}.mp4"
    suffix = Path(safe_name).suffix.lower()
    target_path = tmp_dir / f"{prefix}_{uuid4().hex[:8]}{suffix}"
    upload.save(target_path)
    return target_path


def _parse_metadata() -> dict:
    raw_metadata = request.form.get("metadata") or "{}"
    try:
        payload = json.loads(raw_metadata)
    except json.JSONDecodeError as exc:
        raise ValueError("metadata는 JSON 문자열이어야 합니다.") from exc
    if not isinstance(payload, dict):
        raise ValueError("metadata는 JSON object여야 합니다.")
    return payload


def _validate_similarity_metadata(metadata: dict) -> None:
    camera_view = metadata.get("cameraView")
    if camera_view not in (None, "", SUPPORTED_CAMERA_VIEW):
        raise ValueError(f"cameraView는 현재 {SUPPORTED_CAMERA_VIEW}만 지원합니다.")
    for field_name in ("user", "speed"):
        _metadata_object(metadata, field_name)
    speed_metadata = _metadata_object(metadata, "speed")
    _metadata_object(speed_metadata, "user", path="metadata.speed.user")


def _metadata_object(metadata: dict, field_name: str, path: str | None = None) -> dict:
    value = metadata.get(field_name)
    if value in (None, ""):
        return {}
    if not isinstance(value, dict):
        object_path = path or f"metadata.{field_name}"
        raise ValueError(f"{object_path}는 JSON object여야 합니다.")
    return value


def _parse_optional_int(value) -> int | None:
    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _rank_player_matches(user_csv_text: str, pro_skeleton_data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for item in pro_skeleton_data:
        similarity = compute_similarity(user_csv_text, item["skeleton_data"])
        matches.append(
            {
                "analysisId": item.get("analysisId") or item.get("analysis_id"),
                "proId": item["proId"],
                "playerName": item.get("playerName") or item.get("player_name"),
                "skeletonDataId": item.get("skeletonDataId") or item.get("skeleton_data_id"),
                "overallScore": similarity.get("overallScore"),
                "phaseScores": similarity.get("phaseScores", []),
                "phaseDetection": similarity.get("phaseDetection", {}),
                "normalization": similarity.get("normalization", {}),
                "similarityStatus": similarity.get("status"),
            }
        )

    sorted_matches = sorted(matches, key=_match_sort_key, reverse=True)[:3]
    players: list[dict[str, Any]] = []
    for rank, match in enumerate(sorted_matches, start=1):
        player = {
            "rank": rank,
            "analysisId": str(match.get("analysisId") or f"analysis_{rank}"),
            "proId": match["proId"],
            "overallScore": match["overallScore"],
            "phaseScores": match["phaseScores"],
            "phaseDetection": match.get("phaseDetection", {}),
            "normalization": match.get("normalization", {}),
        }
        if match.get("playerName"):
            player["playerName"] = match["playerName"]
        if match.get("skeletonDataId"):
            player["skeletonDataId"] = match["skeletonDataId"]
        if match.get("similarityStatus"):
            player["similarityStatus"] = match["similarityStatus"]
        players.append(player)
    return players


def _match_sort_key(match: dict[str, Any]) -> float:
    score = match.get("overallScore")
    try:
        parsed = float(score)
    except (TypeError, ValueError):
        return -1.0
    return parsed if parsed == parsed else -1.0


def _format_resolution(video_meta: dict[str, Any]) -> str:
    width = int(video_meta.get("width") or 0)
    height = int(video_meta.get("height") or 0)
    return f"{width}x{height}"


@app.errorhandler(ValueError)
def handle_value_error(error: ValueError):
    return _error_response(message=str(error), code="bad_request", http_status=400)


@app.errorhandler(HTTPException)
def handle_http_exception(error: HTTPException):
    return _error_response(
        message=str(error.description),
        code=error.name.lower().replace(" ", "_"),
        http_status=int(error.code or 500),
    )


@app.errorhandler(Exception)
def handle_unexpected_error(error: Exception):
    return _error_response(
        message="분석 처리 중 서버 오류가 발생했습니다.",
        code="internal_server_error",
        http_status=500,
        detail=error.__class__.__name__,
    )


def _error_response(message: str, code: str, http_status: int, detail: str | None = None):
    payload = {
        "status": "error",
        "error": {
            "code": code,
            "message": message,
        },
    }
    if detail:
        payload["error"]["detail"] = detail
    return jsonify(payload), http_status


refresh_pro_skeleton_cache()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5020, debug=True)
