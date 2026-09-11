from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


# 백엔드 내부 API 공유 키 헤더. 백엔드 SecurityConfig.INTERNAL_API_KEY_HEADER와 같아야 한다.
INTERNAL_API_KEY_HEADER = "X-Internal-Api-Key"

_CACHE: list[dict[str, Any]] = []
_CACHE_META: dict[str, Any] = {
    "status": "empty",
    "source": None,
    "count": 0,
    "refreshedAt": None,
    "warning": "PRO_SKELETON_DATA_URL 또는 PRO_SKELETON_DATA_FILE이 설정되지 않았습니다.",
}


def refresh_pro_skeleton_cache() -> dict[str, Any]:
    """Load pro skeleton references from backend URL or local fixture file."""
    source_url = os.getenv("PRO_SKELETON_DATA_URL", "").strip()
    source_file = os.getenv("PRO_SKELETON_DATA_FILE", "").strip()

    source = source_url or source_file or None
    if not source:
        _set_cache([], source=None, status="empty", warning="프로 skeleton 데이터 소스가 설정되지 않았습니다.")
        return cache_status()

    try:
        raw_payload = _read_json_from_url(source_url) if source_url else _read_json_from_file(Path(source_file))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
        _set_cache([], source=source, status="error", warning=f"프로 skeleton 데이터 로드 실패: {exc}")
        return cache_status()

    items = _extract_items(raw_payload)
    normalized_items = _normalize_items(items)
    _set_cache(
        normalized_items,
        source=source,
        status="ready" if normalized_items else "empty",
        warning=None if normalized_items else "프로 skeleton 데이터가 비어 있습니다.",
    )
    return cache_status()


def get_cached_pro_skeletons() -> list[dict[str, Any]]:
    return list(_CACHE)


def cache_status() -> dict[str, Any]:
    return {
        **_CACHE_META,
        "players": [
            {
                "proId": item.get("proId"),
                "playerName": item.get("playerName"),
                "skeletonDataId": item.get("skeletonDataId"),
                "frameCount": item.get("frameCount"),
                "fps": item.get("fps"),
                "resolution": item.get("resolution"),
            }
            for item in _CACHE[:20]
        ],
    }


def _request_headers() -> dict[str, str]:
    """백엔드 내부 API 요청 헤더. INTERNAL_API_KEY가 있으면 공유 키를 싣는다.

    백엔드는 키가 설정된 환경(코드스페이스)에서 이 헤더가 없는 내부 API 요청을 403으로 막는다.
    키가 없는 로컬 개발 환경에서는 지금처럼 헤더 없이 보낸다.
    """
    headers = {"Accept": "application/json"}
    key = os.getenv("INTERNAL_API_KEY", "").strip()
    if key:
        headers[INTERNAL_API_KEY_HEADER] = key
    return headers


def _read_json_from_url(url: str) -> Any:
    request = urllib.request.Request(url, headers=_request_headers())
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            body = response.read().decode("utf-8")
    except urllib.error.URLError as exc:
        raise OSError(f"백엔드 프로 skeleton 요청 실패: {exc}") from exc
    return json.loads(body)


def _read_json_from_file(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"프로 skeleton 파일이 없습니다: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_items(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in ("pro_skeleton_data", "proSkeletonData", "pro_keypoints", "players", "items", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return []


def _normalize_items(items: list[Any]) -> list[dict[str, Any]]:
    normalized_items: list[dict[str, Any]] = []
    for item in items:
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
        normalized_items.append(normalized)
    return normalized_items


def _set_cache(items: list[dict[str, Any]], *, source: str | None, status: str, warning: str | None) -> None:
    global _CACHE, _CACHE_META
    _CACHE = items
    _CACHE_META = {
        "status": status,
        "source": source,
        "count": len(items),
        "refreshedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "warning": warning,
    }
