"""HTTP 응답 조립이 계산 결과를 잃지 않는지 검증한다.

app.py는 응답에 실을 필드를 화이트리스트로 다시 조립한다(_rank_player_matches).
목록에 없는 키는 조용히 사라진다. 그래서 분석이 값을 제대로 계산해도 앱까지
도달하지 못하고, 계산 쪽 테스트는 전부 통과하기 때문에 아무도 눈치채지 못한다.

실제로 phaseMetrics가 이 방식으로 사라져 있었다. 같은 일이 반복되지 않도록
경계 자체를 테스트한다.
"""

from __future__ import annotations

from typing import Any

import app as flask_app


PHASE_METRIC = {
    "phase": "acceleration",
    "key": "acceleration_arm_slot",
    "label": "암슬롯(상완 기울기)",
    "unit": "degree",
    "userValue": 78.4,
    "proValue": 71.9,
    "difference": 6.5,
    "threshold": 10.0,
    "status": "good",
    "favorableDirection": None,
    "why": "암슬롯이 투구마다 흔들리면 릴리즈 포인트가 달라집니다.",
    "userJoints": ["right_shoulder", "right_elbow"],
    "proJoints": ["left_shoulder", "left_elbow"],
    "userFrame": 62,
    "proFrame": 58,
}


def _fake_similarity(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    return {
        "overallScore": 80.0,
        "phaseScores": [],
        "release": {},
        "feedback": {"good": [], "bad": []},
        "phaseMetrics": [PHASE_METRIC],
    }


def _rank_with_fake_similarity() -> list[dict[str, Any]]:
    """compute_similarity를 가짜로 바꿔 응답 조립만 떼어 본다."""
    original_similarity = flask_app.compute_similarity
    original_release = flask_app.estimate_user_release_event
    flask_app.compute_similarity = _fake_similarity
    flask_app.estimate_user_release_event = lambda *_a, **_k: None
    try:
        return flask_app._rank_player_matches(
            "user-csv",
            [{"proId": "7", "analysisId": "a1", "skeleton_data": "pro-csv"}],
        )
    finally:
        flask_app.compute_similarity = original_similarity
        flask_app.estimate_user_release_event = original_release


def test_response_keeps_phase_metrics() -> None:
    players = _rank_with_fake_similarity()

    assert len(players) == 1
    metrics = players[0].get("phaseMetrics")
    assert metrics, "phaseMetrics가 응답 조립 과정에서 사라졌다"
    assert metrics[0]["key"] == "acceleration_arm_slot"


def test_response_keeps_every_phase_metric_field() -> None:
    """필드 하나라도 빠지면 앱에서 그 기능이 조용히 죽는다.

    unit이 없으면 각도가 좌표처럼 표기되고, userFrame이 없으면 '이 순간 보기'가
    사라지며, threshold가 없으면 게이지가 그려지지 않는다.
    """
    metric = _rank_with_fake_similarity()[0]["phaseMetrics"][0]

    for field_name, expected in PHASE_METRIC.items():
        assert field_name in metric, f"{field_name}이(가) 응답에서 빠졌다"
        assert metric[field_name] == expected, f"{field_name} 값이 바뀌었다"


def test_response_tolerates_missing_phase_metrics() -> None:
    """구버전 계산 결과(phaseMetrics 없음)에서도 조립이 깨지지 않아야 한다."""
    original_similarity = flask_app.compute_similarity
    original_release = flask_app.estimate_user_release_event
    flask_app.compute_similarity = lambda *_a, **_k: {
        "overallScore": 80.0,
        "phaseScores": [],
        "release": {},
        "feedback": {"good": [], "bad": []},
    }
    flask_app.estimate_user_release_event = lambda *_a, **_k: None
    try:
        players = flask_app._rank_player_matches(
            "user-csv", [{"proId": "7", "skeleton_data": "pro-csv"}]
        )
    finally:
        flask_app.compute_similarity = original_similarity
        flask_app.estimate_user_release_event = original_release

    assert players[0]["phaseMetrics"] == []
