from __future__ import annotations

import os
from unittest.mock import patch

from analysis.pro_cache import INTERNAL_API_KEY_HEADER, _read_json_from_url

# urllib은 헤더 이름을 capitalize()해서 저장한다("X-internal-api-key").
# HTTP 헤더는 대소문자를 구분하지 않으므로 백엔드는 그대로 받는다.
_STORED_NAME = INTERNAL_API_KEY_HEADER.capitalize()


class _FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self) -> bytes:
        return b"[]"


def _captured_request(env: dict[str, str]):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        return _FakeResponse()

    with patch.dict(os.environ, env, clear=False), patch("analysis.pro_cache.urllib.request.urlopen", fake_urlopen):
        _read_json_from_url("http://127.0.0.1:8080/api/internal/analysis/reference-models")
    return captured["request"]


def test_key_is_sent_when_configured() -> None:
    """코드스페이스처럼 백엔드가 키를 요구하는 환경에서는 헤더를 실어야 403을 피한다."""
    request = _captured_request({"INTERNAL_API_KEY": "secret-key"})
    assert request.get_header(_STORED_NAME) == "secret-key"


def test_no_header_when_key_is_not_configured() -> None:
    """키가 없는 로컬 개발 환경에서는 지금처럼 헤더 없이 보낸다."""
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("INTERNAL_API_KEY", None)
        request = _captured_request({})
    assert not request.has_header(_STORED_NAME)


def test_blank_key_is_treated_as_not_configured() -> None:
    """공백만 있는 값은 설정하지 않은 것으로 본다. 빈 헤더를 보내 403을 받는 것보다 낫다."""
    request = _captured_request({"INTERNAL_API_KEY": "   "})
    assert not request.has_header(_STORED_NAME)
