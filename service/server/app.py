from __future__ import annotations

import json
import os
import re
import tempfile
import time
import unicodedata
from pathlib import Path
from typing import Any
from urllib.parse import quote
from uuid import uuid4

from flask import Flask, Response, jsonify, render_template, request, send_file
from werkzeug.datastructures import FileStorage
from werkzeug.exceptions import HTTPException, ServiceUnavailable
from werkzeug.utils import secure_filename

from analysis.pro_cache import cache_status, get_cached_pro_skeletons, refresh_pro_skeleton_cache
from analysis.pose import CSV_COLUMNS, extract_skeleton_data_csv_text
from analysis.resampling_preview import build_resampling_preview, build_resampling_preview_from_csv_text
from analysis.similarity import compute_similarity, estimate_user_release_event
from analysis.speed import compute_tof_speed
from analysis.video import inspect_video


SERVER_ROOT = Path(__file__).resolve().parent
INTEGRATED_ROOT = SERVER_ROOT.parent
PROJECT_ROOT = INTEGRATED_ROOT.parent
WEB_ROOT = INTEGRATED_ROOT / "web"
OPENAPI_SPEC_PATH = PROJECT_ROOT / "docs" / "openapi.yaml"
CAPSTONE_ROOT = PROJECT_ROOT.parent
PRO_VIDEO_DIR = CAPSTONE_ROOT / "pro_data"
PREVIEW_PRO_VIDEO_DIR = Path(os.getenv("PREVIEW_PRO_VIDEO_DIR") or PRO_VIDEO_DIR / "crop")
CROP2_PRO_VIDEO_DIR = Path(os.getenv("CROP2_PRO_VIDEO_DIR") or PRO_VIDEO_DIR / "crop2")
USER_VIDEO_DIR = CAPSTONE_ROOT / "user_data"
DEFAULT_RESAMPLING_PRO_KEYPOINTS = PROJECT_ROOT / "outputs" / "exp6" / "pro" / "keypoints.csv"
DEFAULT_RESAMPLING_USER_KEYPOINTS = PROJECT_ROOT / "outputs" / "exp6" / "user" / "keypoints.csv"
DEFAULT_PRO_SKELETON_DATA_FILE = PROJECT_ROOT / "outputs" / "pro_skeleton_data_20260601" / "pro_skeleton_data.json"
ALLOWED_EXTENSIONS = {".mp4", ".mov", ".avi", ".m4v"}
PREVIEW_VIDEO_LIMIT = 20
PREVIEW_ANALYSIS_MIN_FRAMES = 360
SUPPORTED_CAMERA_VIEW = "rear"
RESPONSE_SCHEMA_VERSION = "pitch_analysis_response_v1"
SIMILARITY_ALGORITHM_NAME = "fixed_step_pose_resampling_v1"
SCORE_SCALE = "0~100"
PUBLIC_PHASE_SCORE_FIELDS = (
    "phase",
    "label",
    "score",
    "userStartFrame",
    "userEndFrame",
    "proStartFrame",
    "proEndFrame",
)

app = Flask(
    __name__,
    template_folder=str(WEB_ROOT / "templates"),
    static_folder=str(WEB_ROOT / "static"),
)
app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024 * 1024
app.config["SECRET_KEY"] = "integrated-local-dev"
app.json.sort_keys = False


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "service": "integrated-pitch-analysis"})


@app.get("/api/docs")
def swagger_docs():
    html = """<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <title>Integrated Pitch Analysis API Docs</title>
  <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css">
  <style>
    body { margin: 0; background: #f7f4ec; }
    .swagger-ui .topbar { display: none; }
  </style>
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
  <script>
    window.addEventListener("load", () => {
      window.ui = SwaggerUIBundle({
        url: "/api/openapi.yaml",
        dom_id: "#swagger-ui",
        deepLinking: true,
        presets: [SwaggerUIBundle.presets.apis],
        layout: "BaseLayout"
      });
    });
  </script>
</body>
</html>"""
    return Response(html, mimetype="text/html")


@app.get("/api/openapi.yaml")
def openapi_yaml():
    return send_file(OPENAPI_SPEC_PATH, mimetype="application/yaml")


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
                "phases": ["windup", "leg_lift", "stride", "acceleration", "follow_through"],
                "releaseDetection": {
                    "default": "나가기 전 프레임과 나간 프레임의 중간값",
                    "currentFallback": "공 탐지 실패 시 손목 기반 proxy midpoint",
                    "plannedSubFrameCorrection": "손목-공 거리 threshold crossing",
                },
            },
            "request": {
                "similarity": {
                    "method": "POST",
                    "path": "/api/analyze",
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


@app.get("/api/experiments/video-options")
def experiment_video_options():
    return jsonify(
        {
            "status": "ok",
            "limit": PREVIEW_VIDEO_LIMIT,
            "directories": {
                "pro": str(PREVIEW_PRO_VIDEO_DIR),
                "user": str(USER_VIDEO_DIR),
            },
            "proVideos": _video_options(PREVIEW_PRO_VIDEO_DIR, limit=PREVIEW_VIDEO_LIMIT),
            "userVideos": _video_options(
                USER_VIDEO_DIR,
                limit=PREVIEW_VIDEO_LIMIT,
                preferred_names=("y1.mp4", "y2.mp4", "y3.mp4", "i1.mp4", "i2.mp4", "i3.mp4", "i4.mp4", "i5.mp4"),
            ),
        }
    )


@app.get("/api/experiments/crop2-skeletons")
def experiment_crop2_skeletons():
    requested_max_frames = _parse_optional_int(request.args.get("maxFrames")) or PREVIEW_ANALYSIS_MIN_FRAMES
    analysis_max_frames = _preview_analysis_max_frames(requested_max_frames)
    items = []
    for path in _video_paths(CROP2_PRO_VIDEO_DIR, limit=PREVIEW_VIDEO_LIMIT):
        meta = inspect_video(path)
        csv_text, pose_meta = extract_skeleton_data_csv_text(
            path,
            max_frames=analysis_max_frames,
            sample_evenly=True,
            focus_motion=True,
        )
        payload = build_resampling_preview_from_csv_text(
            pro_csv_text=csv_text,
            user_csv_text=csv_text,
            sources={
                "mode": "crop2_skeleton_video",
                "proVideo": path.name,
                "proSource": "pro_data/crop2",
                "playerName": unicodedata.normalize("NFC", path.stem),
            },
            video_paths={"pro": path},
        )
        items.append(
            {
                "id": path.name,
                "filename": path.name,
                "label": unicodedata.normalize("NFC", path.stem),
                "videoMeta": meta,
                "poseMeta": pose_meta,
                "videoSource": _preview_video_source_payload("crop2", path.name),
                "phaseDetection": payload.get("phaseDetection", {}),
                "releaseEvents": payload.get("releaseEvents", {}),
                "cockingEvents": payload.get("cockingEvents", {}),
                "warnings": payload.get("warnings", {}),
                "phases": payload.get("phases", []),
            }
        )
    return jsonify(
        {
            "status": "ok",
            "directory": str(CROP2_PRO_VIDEO_DIR),
            "requestedMaxFrames": requested_max_frames,
            "analysisMaxFrames": analysis_max_frames,
            "items": items,
        }
    )


@app.get("/api/experiments/video/<side>/<path:filename>")
def experiment_video_file(side: str, filename: str):
    video_path = _preview_video_file_path(side, filename)
    return send_file(video_path, conditional=True)


@app.get("/api/experiments/pro-skeleton-options")
def experiment_pro_skeleton_options():
    items, source = _load_pro_skeleton_preview_items()
    return jsonify(
        {
            "status": "ok",
            "source": str(source) if source is not None else "cache",
            "players": [_pro_skeleton_option(item) for item in items],
        }
    )


@app.post("/api/experiments/pro-skeleton-preview")
def experiment_pro_skeleton_preview():
    items, source = _load_pro_skeleton_preview_items()
    selected_id = str(request.form.get("proSkeletonOption") or request.form.get("proId") or "").strip()
    item = _select_pro_skeleton_item(items, selected_id)
    if item is None:
        raise ValueError("선택한 pro skeleton 데이터를 찾지 못했습니다.")

    csv_text = str(item.get("skeleton_data") or "")
    if not csv_text.strip():
        raise ValueError("선택한 pro skeleton 데이터가 비어 있습니다.")

    meta = _pro_skeleton_video_meta(item)
    payload = build_resampling_preview_from_csv_text(
        pro_csv_text=csv_text,
        user_csv_text=csv_text,
        sources={
            "mode": "pro_skeleton_data",
            "source": str(source) if source is not None else "cache",
            "proId": str(item.get("proId") or ""),
            "playerName": str(item.get("playerName") or item.get("proId") or ""),
            "skeletonDataId": str(item.get("skeletonDataId") or item.get("skeleton_data_id") or ""),
            "sourceVideo": str(item.get("sourceVideo") or ""),
        },
    )
    payload["method"] = "pro_skeleton_data_preview"
    payload["videoMeta"] = {"pro": meta, "user": meta}
    payload["videoSources"] = {
        "pro": _preview_video_source_payload("pro", str(item.get("sourceVideo") or "")),
        "user": None,
    }
    return jsonify(payload)


@app.get("/api/experiments/resampling-preview")
def resampling_preview():
    return jsonify(
        build_resampling_preview(
            pro_keypoints_path=DEFAULT_RESAMPLING_PRO_KEYPOINTS,
            user_keypoints_path=DEFAULT_RESAMPLING_USER_KEYPOINTS,
        )
    )


@app.post("/api/experiments/resampling-preview")
def uploaded_resampling_preview():
    pro_upload = _optional_file("proVideo")
    user_upload = _optional_file("userVideo")
    pro_selected_path = _selected_video_path("proVideoOption", PREVIEW_PRO_VIDEO_DIR)
    user_selected_path = _selected_video_path("userVideoOption", USER_VIDEO_DIR)
    metadata = _parse_metadata()
    requested_max_frames = _parse_optional_int(metadata.get("maxFrames") or request.form.get("maxFrames"))
    analysis_max_frames = _preview_analysis_max_frames(requested_max_frames)
    pro_trim = _preview_trim_seconds(metadata, "pro")
    user_trim = _preview_trim_seconds(metadata, "user")
    if pro_upload is None and pro_selected_path is None:
        raise ValueError("선수 영상 업로드 또는 pro_data 영상 선택이 필요합니다.")
    if user_upload is None and user_selected_path is None:
        raise ValueError("사용자 영상 업로드 또는 user_data 영상 선택이 필요합니다.")

    pro_source = _preview_source(upload=pro_upload, selected_path=pro_selected_path, folder_label="pro_data")
    user_source = _preview_source(upload=user_upload, selected_path=user_selected_path, folder_label="user_data")

    with tempfile.TemporaryDirectory(prefix="resampling_preview_", ignore_cleanup_errors=True) as tmp_dir_name:
        tmp_dir = Path(tmp_dir_name)
        pro_path = _save_temp_upload(pro_upload, tmp_dir, "pro") if pro_upload else pro_selected_path
        user_path = _save_temp_upload(user_upload, tmp_dir, "user") if user_upload else user_selected_path
        if pro_path is None or user_path is None:
            raise ValueError("미리보기 영상 경로를 확인하지 못했습니다.")

        pro_meta = inspect_video(pro_path)
        user_meta = inspect_video(user_path)
        pro_csv_text, pro_pose_meta = extract_skeleton_data_csv_text(
            pro_path,
            max_frames=analysis_max_frames,
            sample_evenly=True,
            start_sec=pro_trim["startSec"],
            end_sec=pro_trim["endSec"],
            focus_motion=True,
        )
        user_csv_text, user_pose_meta = extract_skeleton_data_csv_text(
            user_path,
            max_frames=analysis_max_frames,
            sample_evenly=True,
            start_sec=user_trim["startSec"],
            end_sec=user_trim["endSec"],
            focus_motion=True,
        )

        payload = build_resampling_preview_from_csv_text(
            pro_csv_text=pro_csv_text,
            user_csv_text=user_csv_text,
            sources={
                "mode": _preview_mode(pro_source, user_source),
                "proVideo": pro_source["name"],
                "userVideo": user_source["name"],
                "proSource": pro_source["source"],
                "userSource": user_source["source"],
            },
            video_paths={
                "pro": pro_path,
                "user": user_path,
            },
        )
    payload["videoMeta"] = {
        "pro": pro_meta,
        "user": user_meta,
    }
    payload["poseMeta"] = {
        "pro": pro_pose_meta,
        "user": user_pose_meta,
    }
    payload["previewFrameLimit"] = {
        "requestedMaxFrames": requested_max_frames,
        "analysisMaxFrames": analysis_max_frames,
        "minimumAnalysisFrames": PREVIEW_ANALYSIS_MIN_FRAMES,
    }
    payload["previewTrim"] = {
        "pro": pro_pose_meta.get("trim", {}),
        "user": user_pose_meta.get("trim", {}),
    }
    payload["videoSources"] = {
        "pro": _preview_video_source_payload("pro", pro_source["name"]) if pro_source["source"] != "upload" else None,
        "user": _preview_video_source_payload("user", user_source["name"]) if user_source["source"] != "upload" else None,
    }
    return jsonify(payload)


@app.post("/api/analyze")
def analyze_similarity():
    user_upload = _required_file("userVideo")
    metadata = _parse_metadata()
    _validate_similarity_metadata(metadata)
    # 비교 대상 결정:
    #  - metadata.referenceSkeletons 가 있으면 그 골격들과 비교한다(예: 내 "최고의 1구").
    #  - 없으면 기존대로 서버 프로 캐시와 비교한다(하위호환).
    reference_skeletons = _parse_reference_skeletons(metadata)
    if reference_skeletons is not None:
        pro_skeleton_data = reference_skeletons
    else:
        pro_skeleton_data = get_cached_pro_skeletons()
        if not pro_skeleton_data:
            raise ServiceUnavailable("프로 skeleton 캐시가 비어 있습니다. 서버 시작 시 백엔드에서 프로 데이터를 받아오도록 설정해 주세요.")
    user_metadata = _metadata_object(metadata, "user")
    video_id = str(metadata.get("videoId") or user_metadata.get("videoId") or f"user_video_{uuid4().hex[:10]}")
    skeleton_data_id = str(
        user_metadata.get("skeletonDataId")
        or user_metadata.get("skeleton_data_id")
        or f"user_skeleton_{uuid4().hex[:10]}"
    )

    with tempfile.TemporaryDirectory(prefix="integrated_pitch_", ignore_cleanup_errors=True) as tmp_dir_name:
        tmp_dir = Path(tmp_dir_name)
        user_path = _save_temp_upload(user_upload, tmp_dir, "user")

        user_meta = inspect_video(user_path)
        max_frames = _parse_optional_int(metadata.get("maxFrames"))
        # 앱 트리머로 선택한 구간(초)이 있으면 그 구간만 분석한다(없으면 전체).
        user_trim = _preview_trim_seconds(metadata, "user")
        _t_extract = time.perf_counter()
        user_csv_text, user_pose_meta = extract_skeleton_data_csv_text(
            user_path,
            max_frames=max_frames,
            sample_evenly=True,  # max_frames 지정 시 (트림된) 구간 전체에서 균등 샘플링
            start_sec=user_trim["startSec"],
            end_sec=user_trim["endSec"],
            focus_motion=True,
        )
        _extract_sec = time.perf_counter() - _t_extract
        _t_rank = time.perf_counter()
        # 최고의 1구 비교(referenceSkeletons 주입)면 피드백 문구/방향성 해석을 best_pitch 모드로.
        comparison_mode = "best_pitch" if reference_skeletons is not None else "pro"
        players = _rank_player_matches(
            user_csv_text,
            pro_skeleton_data,
            user_video_path=user_path,
            comparison_mode=comparison_mode,
        )
        _rank_sec = time.perf_counter() - _t_rank
        print(
            f"[TIMING] pose_extract={_extract_sec:.1f}s "
            f"(frames={user_pose_meta.get('frameCount')}, source={user_pose_meta.get('sourceFrameCount')}, "
            f"res={_format_resolution(user_meta)}) | "
            f"rank={_rank_sec:.1f}s (pros={len(pro_skeleton_data)}) | "
            f"total={_extract_sec + _rank_sec:.1f}s",
            flush=True,
        )

    return jsonify(
        {
            "videoId": video_id,
            "status": "completed",
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
    with tempfile.TemporaryDirectory(prefix="integrated_speed_", ignore_cleanup_errors=True) as tmp_dir_name:
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
    upload = _optional_file(field_name)
    if upload is None:
        raise ValueError(f"{field_name} 파일이 필요합니다.")
    return upload


def _optional_file(field_name: str) -> FileStorage | None:
    upload = request.files.get(field_name)
    if upload is None or not upload.filename:
        return None
    if Path(upload.filename).suffix.lower() not in ALLOWED_EXTENSIONS:
        raise ValueError(f"{field_name}은 mp4/mov/avi/m4v만 지원합니다.")
    return upload


def _save_temp_upload(upload: FileStorage, tmp_dir: Path, prefix: str) -> Path:
    safe_name = secure_filename(Path(upload.filename).name) or f"{prefix}.mp4"
    suffix = Path(safe_name).suffix.lower()
    target_path = tmp_dir / f"{prefix}_{uuid4().hex[:8]}{suffix}"
    upload.save(target_path)
    return target_path


def _video_options(directory: Path, *, limit: int, preferred_names: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    videos = _video_paths(directory, limit=limit, preferred_names=preferred_names)
    return [
        {
            "id": path.name,
            "filename": path.name,
            "label": unicodedata.normalize("NFC", path.stem),
            "sizeBytes": path.stat().st_size,
        }
        for path in videos[:limit]
    ]


def _video_paths(directory: Path, *, limit: int, preferred_names: tuple[str, ...] = ()) -> list[Path]:
    if not directory.exists():
        return []
    videos = [
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in ALLOWED_EXTENSIONS
    ]
    preferred_order = {name: index for index, name in enumerate(preferred_names)}
    videos.sort(key=lambda path: (preferred_order.get(path.name, len(preferred_order)), _natural_sort_key(path.name)))
    return videos[:limit]


def _load_pro_skeleton_preview_items() -> tuple[list[dict[str, Any]], Path | None]:
    candidates = []
    env_file = os.getenv("PRO_SKELETON_DATA_FILE", "").strip()
    if env_file:
        candidates.append(Path(env_file))
    candidates.append(DEFAULT_PRO_SKELETON_DATA_FILE)

    for path in candidates:
        if not path.exists() or not path.is_file():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        items = _extract_pro_skeleton_items(payload)
        if items:
            return items, path

    return get_cached_pro_skeletons(), None


def _extract_pro_skeleton_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        values = payload
    elif isinstance(payload, dict):
        values = []
        for key in ("pro_skeleton_data", "proSkeletonData", "pro_keypoints", "players", "items", "data"):
            candidate = payload.get(key)
            if isinstance(candidate, list):
                values = candidate
                break
    else:
        values = []

    items = []
    for item in values:
        if not isinstance(item, dict):
            continue
        pro_id = item.get("proId") or item.get("pro_id") or item.get("id")
        csv_text = item.get("skeleton_data") or item.get("skeletonData") or item.get("keypointsCsvText")
        if not pro_id or not isinstance(csv_text, str) or not csv_text.strip():
            continue
        normalized = dict(item)
        normalized["proId"] = str(pro_id)
        normalized["skeleton_data"] = csv_text
        if "playerName" not in normalized and "player_name" in normalized:
            normalized["playerName"] = normalized["player_name"]
        if "skeletonDataId" not in normalized and "skeleton_data_id" in normalized:
            normalized["skeletonDataId"] = normalized["skeleton_data_id"]
        items.append(normalized)
    return items


def _pro_skeleton_option(item: dict[str, Any]) -> dict[str, Any]:
    pro_id = str(item.get("proId") or "")
    player_name = str(item.get("playerName") or pro_id)
    return {
        "id": pro_id,
        "label": player_name,
        "proId": pro_id,
        "playerName": player_name,
        "skeletonDataId": item.get("skeletonDataId") or item.get("skeleton_data_id"),
        "frameCount": item.get("frameCount"),
        "fps": item.get("fps"),
        "resolution": item.get("resolution"),
        "sourceVideo": item.get("sourceVideo"),
    }


def _select_pro_skeleton_item(items: list[dict[str, Any]], selected_id: str) -> dict[str, Any] | None:
    if not items:
        return None
    if not selected_id:
        return items[0]
    for item in items:
        identifiers = {
            str(item.get("proId") or ""),
            str(item.get("skeletonDataId") or item.get("skeleton_data_id") or ""),
            str(item.get("sourceVideo") or ""),
        }
        if selected_id in identifiers:
            return item
    return None


def _pro_skeleton_video_meta(item: dict[str, Any]) -> dict[str, Any]:
    resolution = str(item.get("resolution") or "0x0")
    width_text, _, height_text = resolution.partition("x")
    return {
        "videoId": item.get("sourceVideo") or item.get("proId"),
        "frameCount": item.get("frameCount"),
        "fps": item.get("fps"),
        "width": _parse_optional_int(width_text) or 0,
        "height": _parse_optional_int(height_text) or 0,
    }


def _natural_sort_key(value: str) -> list[Any]:
    parts = re.split(r"(\d+)", value.lower())
    return [int(part) if part.isdigit() else part for part in parts]


def _selected_video_path(field_name: str, directory: Path) -> Path | None:
    selected_name = str(request.form.get(field_name) or "").strip()
    if not selected_name:
        return None
    candidate = _resolve_video_filename(directory, selected_name)
    if candidate is None:
        raise ValueError(f"{field_name} 영상이 폴더 안에 없습니다.")
    return candidate


def _preview_video_file_path(side: str, filename: str) -> Path:
    directories = {"pro": PREVIEW_PRO_VIDEO_DIR, "user": USER_VIDEO_DIR, "crop2": CROP2_PRO_VIDEO_DIR}
    directory = directories.get(side)
    if directory is None:
        raise ValueError("side는 pro, user, crop2만 허용합니다.")
    video_path = _resolve_video_filename(directory, filename)
    if video_path is None:
        raise ValueError("요청한 영상을 찾지 못했습니다.")
    return video_path


def _resolve_video_filename(directory: Path, filename: str) -> Path | None:
    selected_name = str(filename or "").strip()
    if not selected_name or Path(selected_name).name != selected_name:
        return None
    if Path(selected_name).suffix.lower() not in ALLOWED_EXTENSIONS:
        return None

    base = directory.resolve()
    candidate = (directory / selected_name).resolve()
    if candidate.is_relative_to(base) and candidate.exists() and candidate.is_file():
        return candidate

    normalized_name = unicodedata.normalize("NFC", selected_name)
    if not directory.exists():
        return None
    for path in directory.iterdir():
        if not path.is_file() or path.suffix.lower() not in ALLOWED_EXTENSIONS:
            continue
        if unicodedata.normalize("NFC", path.name) == normalized_name:
            return path.resolve()
    return None


def _preview_video_source_payload(side: str, filename: str) -> dict[str, str] | None:
    if not filename:
        return None
    try:
        video_path = _preview_video_file_path(side, filename)
    except ValueError:
        return None
    version = video_path.stat().st_mtime_ns
    return {
        "side": side,
        "filename": filename,
        "url": f"/api/experiments/video/{side}/{quote(filename)}?v={version}",
    }


def _preview_source(*, upload: FileStorage | None, selected_path: Path | None, folder_label: str) -> dict[str, str]:
    if upload is not None:
        return {
            "source": "upload",
            "name": secure_filename(upload.filename or "video") or "video",
        }
    if selected_path is not None:
        return {
            "source": folder_label,
            "name": selected_path.name,
        }
    return {"source": "unknown", "name": "unknown"}


def _preview_mode(pro_source: dict[str, str], user_source: dict[str, str]) -> str:
    if pro_source["source"] == "upload" and user_source["source"] == "upload":
        return "uploaded_videos"
    if pro_source["source"] != "upload" and user_source["source"] != "upload":
        return "folder_videos"
    return "mixed_videos"


def _preview_analysis_max_frames(requested_max_frames: int | None) -> int | None:
    if requested_max_frames is None:
        return None
    return max(requested_max_frames, PREVIEW_ANALYSIS_MIN_FRAMES)


def _preview_trim_seconds(metadata: dict[str, Any], side: str) -> dict[str, float | None]:
    start_value = metadata.get(f"{side}TrimStartSec") or request.form.get(f"{side}TrimStartSec")
    end_value = metadata.get(f"{side}TrimEndSec") or request.form.get(f"{side}TrimEndSec")
    start_sec = _parse_optional_float(start_value)
    end_sec = _parse_optional_float(end_value)
    if start_sec is not None and end_sec is not None and end_sec <= start_sec:
        raise ValueError(f"{side} 트림 끝초는 시작초보다 커야 합니다.")
    return {"startSec": start_sec, "endSec": end_sec}


def _parse_metadata() -> dict:
    raw_metadata = request.form.get("metadata") or "{}"
    try:
        payload = json.loads(raw_metadata)
    except json.JSONDecodeError as exc:
        raise ValueError("metadata는 JSON 문자열이어야 합니다.") from exc
    if not isinstance(payload, dict):
        raise ValueError("metadata는 JSON object여야 합니다.")
    return payload


def _parse_reference_skeletons(metadata: dict) -> list[dict[str, Any]] | None:
    """metadata.referenceSkeletons → [{proId, skeleton_data}] 정규화.

    필드가 아예 없으면 None(=프로 캐시 비교)을 반환하고,
    값이 있으나 유효한 항목이 없으면 ValueError를 던진다.
    """
    raw = metadata.get("referenceSkeletons")
    if raw in (None, ""):
        return None
    if not isinstance(raw, list):
        raise ValueError("referenceSkeletons는 JSON 배열이어야 합니다.")
    items: list[dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        pro_id = entry.get("proId") or entry.get("pro_id") or entry.get("id")
        csv_text = entry.get("skeleton_data") or entry.get("skeletonData")
        if pro_id is None or not isinstance(csv_text, str) or not csv_text.strip():
            continue
        items.append({"proId": str(pro_id), "skeleton_data": csv_text})
    if not items:
        raise ValueError("referenceSkeletons에 유효한 골격 데이터가 없습니다.")
    return items


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


def _parse_optional_float(value) -> float | None:
    if value in (None, ""):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _rank_player_matches(
    user_csv_text: str,
    pro_skeleton_data: list[dict[str, Any]],
    *,
    user_video_path: Path | None = None,
    comparison_mode: str = "pro",
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    # 사용자 릴리즈 이벤트는 프로와 무관하게 동일하므로 한 번만 계산해 재사용한다.
    # (기존에는 프로마다 compute_similarity가 user_video를 다시 디코딩해 N배 느렸음)
    _t_rel = time.perf_counter()
    user_release_event = estimate_user_release_event(user_csv_text, user_video_path)
    _rel_sec = time.perf_counter() - _t_rel
    user_release_events = {"user": user_release_event} if user_release_event else None
    _t_loop = time.perf_counter()
    for item in pro_skeleton_data:
        similarity = compute_similarity(
            user_csv_text,
            item["skeleton_data"],
            release_events=user_release_events,
            comparison_mode=comparison_mode,
        )
        matches.append(
            {
                "analysisId": item.get("analysisId") or item.get("analysis_id"),
                "proId": item["proId"],
                "overallScore": similarity.get("overallScore"),
                "phaseScores": similarity.get("phaseScores", []),
                "release": similarity.get("release", {}),
                "feedback": similarity.get("feedback", {"good": [], "bad": []}),
            }
        )

    _loop_sec = time.perf_counter() - _t_loop
    _pros = len(pro_skeleton_data) or 1
    print(
        f"[TIMING] rank breakdown: user_release(1x)={_rel_sec:.1f}s | "
        f"per-pro loop={_loop_sec:.1f}s (avg {_loop_sec / _pros:.2f}s/pro x{len(pro_skeleton_data)})",
        flush=True,
    )

    # 전 프로를 점수순으로 반환한다(결과 페이지의 전 선수 비교 + 마이페이지 프로별 추이용).
    # 결과 화면의 상위 N 노출은 프론트에서 처리한다.
    sorted_matches = sorted(matches, key=_match_sort_key, reverse=True)
    players: list[dict[str, Any]] = []
    for index, match in enumerate(sorted_matches, start=1):
        player = {
            "analysisId": str(match.get("analysisId") or f"analysis_{index}"),
            "proId": str(match["proId"]),
            "overallScore": match["overallScore"],
            "phaseScores": _compact_phase_scores(match.get("phaseScores")),
            "release": _compact_release(match.get("release")),
            "feedback": _compact_feedback(match.get("feedback")),
        }
        players.append(player)
    return players


def _compact_phase_scores(phase_scores: Any) -> list[dict[str, Any]]:
    if not isinstance(phase_scores, list):
        return []
    return [_compact_phase_score(item) for item in phase_scores if isinstance(item, dict)]


def _compact_phase_score(phase_score: dict[str, Any]) -> dict[str, Any]:
    return {field_name: phase_score.get(field_name) for field_name in PUBLIC_PHASE_SCORE_FIELDS}


def _compact_release(release: Any) -> dict[str, Any]:
    if not isinstance(release, dict):
        release = {}
    return {
        "proFrame": release.get("proFrame"),
        "userFrame": release.get("userFrame"),
        "pro": _compact_release_event(release.get("pro")),
        "user": _compact_release_event(release.get("user")),
        "timing": _compact_release_timing(release.get("timing")),
        "point": _compact_release_point(release.get("point")),
    }


def _compact_release_event(event: Any) -> dict[str, Any]:
    if not isinstance(event, dict):
        return {
            "frame": None,
            "beforeFrame": None,
            "exitFrame": None,
            "method": "unknown",
            "status": "unknown",
            "source": "unknown",
        }
    return {
        "frame": event.get("frame"),
        "beforeFrame": event.get("beforeFrame"),
        "exitFrame": event.get("exitFrame"),
        "method": str(event.get("method") or "unknown"),
        "status": str(event.get("status") or "unknown"),
        "source": str(event.get("source") or "unknown"),
    }


def _compact_release_timing(timing: Any) -> dict[str, Any]:
    if not isinstance(timing, dict):
        timing = {}
    return {
        "proPitchPercent": timing.get("proPitchPercent"),
        "userPitchPercent": timing.get("userPitchPercent"),
        "differencePercent": timing.get("differencePercent"),
        "message": str(timing.get("message") or "릴리즈 타이밍을 계산하지 못했습니다."),
    }


def _compact_release_point(point: Any) -> dict[str, Any]:
    if not isinstance(point, dict):
        point = {}
    return {
        "difference": point.get("difference"),
        "heightDifference": point.get("heightDifference"),
        "sideDifference": point.get("sideDifference"),
        "message": str(point.get("message") or "릴리즈 포인트를 계산하지 못했습니다."),
    }


def _compact_feedback(feedback: Any) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(feedback, dict):
        return {"good": [], "bad": []}
    return {
        "good": _compact_feedback_items(feedback.get("good")),
        "bad": _compact_feedback_items(feedback.get("bad")),
    }


def _compact_feedback_items(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    compacted = []
    for item in items:
        if not isinstance(item, dict):
            continue
        compacted.append(
            {
                "phase": item.get("phase"),
                "message": item.get("message"),
                "evidence": item.get("evidence") if isinstance(item.get("evidence"), dict) else {},
            }
        )
    return compacted


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
    import traceback

    traceback.print_exc()  # 디버그: 실제 원인 traceback을 터미널에 출력
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
