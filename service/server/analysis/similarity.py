from __future__ import annotations

import math
import os
from io import StringIO
from pathlib import Path
from typing import Any

import pandas as pd

from analysis.ball_release import estimate_ball_release_event
from analysis.feedback import build_analysis_feedback
from analysis.normalization import build_body_frame_pose
from analysis.phase import detect_pitch_phases
from analysis.resampling_preview import build_resampled_phase_previews


ALGORITHM_NAME = "fixed_step_pose_resampling_v1"
PHASE_WEIGHTS = {
    "windup": 0.10,
    "leg_lift": 0.20,
    "stride": 0.25,
    "acceleration": 0.30,
    "follow_through": 0.15,
}


def estimate_user_release_event(
    user_csv_text: str,
    user_video_path: Path | None,
) -> dict[str, Any] | None:
    """사용자 영상의 릴리즈 이벤트를 한 번만 계산한다.

    릴리즈 이벤트는 비교 대상 프로와 무관하게 동일하므로, 프로별 루프에서
    매번 영상을 다시 디코딩(cv2.VideoCapture)하지 않도록 미리 한 번 구해
    compute_similarity(release_events=...)로 재사용한다.
    """
    if user_video_path is None:
        return None
    user_df = pd.read_csv(StringIO(user_csv_text))
    if user_df.empty:
        return None
    user_pose = build_body_frame_pose(user_df)
    if user_pose.table.empty:
        return None
    preliminary_user_phases = detect_pitch_phases(user_pose.table)
    return _estimate_release_event(
        video_path=user_video_path,
        keypoints=user_df,
        pose_table=user_pose.table,
        preliminary_phases=preliminary_user_phases,
    )


def compute_similarity(
    user_csv_text: str,
    pro_csv_text: str,
    *,
    user_video_path: Path | None = None,
    pro_video_path: Path | None = None,
    release_events: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    user_df = pd.read_csv(StringIO(user_csv_text))
    pro_df = pd.read_csv(StringIO(pro_csv_text))
    if user_df.empty or pro_df.empty:
        return _unavailable_similarity("keypoints CSV에 프레임 데이터가 없습니다.")

    user_pose = build_body_frame_pose(user_df)
    pro_pose = build_body_frame_pose(pro_df)
    if user_pose.table.empty or pro_pose.table.empty:
        return _unavailable_similarity("body-frame 정규화 좌표를 만들 수 없습니다.")

    release_event_info = release_events or {}
    preliminary_user_phases = detect_pitch_phases(user_pose.table)
    preliminary_pro_phases = detect_pitch_phases(pro_pose.table)
    user_release_event = release_event_info.get("user") or _estimate_release_event(
        video_path=user_video_path,
        keypoints=user_df,
        pose_table=user_pose.table,
        preliminary_phases=preliminary_user_phases,
    )
    pro_release_event = release_event_info.get("pro") or _estimate_release_event(
        video_path=pro_video_path,
        keypoints=pro_df,
        pose_table=pro_pose.table,
        preliminary_phases=preliminary_pro_phases,
    )
    user_phases = detect_pitch_phases(user_pose.table, release_event_override=user_release_event)
    pro_phases = detect_pitch_phases(pro_pose.table, release_event_override=pro_release_event)
    phase_previews = build_resampled_phase_previews(
        pro_table=pro_pose.table,
        user_table=user_pose.table,
        pro_intervals=pro_phases.intervals,
        user_intervals=user_phases.intervals,
    )
    phase_scores = [_phase_score_from_preview(phase) for phase in phase_previews]
    overall = _weighted_overall_score(phase_scores)
    analysis_feedback = build_analysis_feedback(
        user_pose=user_pose.table,
        pro_pose=pro_pose.table,
        user_phases=user_phases,
        pro_phases=pro_phases,
        phase_scores=phase_scores,
    )

    return {
        "status": "ready" if overall is not None else "no_score",
        "algorithmName": ALGORITHM_NAME,
        "scoreScale": "0~100",
        "overallScore": overall,
        "phaseScores": phase_scores,
        "release": analysis_feedback["release"],
        "feedback": analysis_feedback["feedback"],
        "phaseDetection": {
            "user": {
                "representativeFrames": user_phases.representative_frames,
                "intervals": user_phases.intervals,
                "events": user_phases.events,
                "warnings": user_phases.warnings,
            },
            "pro": {
                "representativeFrames": pro_phases.representative_frames,
                "intervals": pro_phases.intervals,
                "events": pro_phases.events,
                "warnings": pro_phases.warnings,
            },
        },
        "normalization": {
            "user": user_pose.summary,
            "pro": pro_pose.summary,
            "warnings": {"user": user_pose.warnings, "pro": pro_pose.warnings},
        },
        "notes": [
            "phase 내부를 고정 step으로 리샘플링한 뒤 같은 진행률의 skeleton 자세 거리를 비교합니다.",
            "속도 자체는 점수에 반영하지 않고, phase별 자세 흐름만 비교합니다.",
            "메인 API는 캐시된 pro skeleton CSV를 사용하므로 공 기반 release가 없으면 손목 기반 proxy midpoint를 사용합니다.",
        ],
    }


def _estimate_release_event(
    *,
    video_path: Path | None,
    keypoints: pd.DataFrame,
    pose_table: pd.DataFrame,
    preliminary_phases: Any,
) -> dict[str, Any] | None:
    if video_path is None:
        return None
    # 공 픽셀 기반 릴리즈 "정밀화"는 고해상도 프레임을 랜덤 시킹하며 처리해 매우 비싸다(수십~백수십초).
    # BALL_RELEASE_DETECTION=0 이면 건너뛰고 phase 기반 릴리즈로 폴백한다(타이밍 정밀도만 소폭 하락).
    if os.getenv("BALL_RELEASE_DETECTION", "1").strip() == "0":
        return None
    try:
        return estimate_ball_release_event(
            video_path=video_path,
            keypoints=keypoints,
            normalized_pose=pose_table,
            intervals=preliminary_phases.intervals,
            fallback_release_event=preliminary_phases.events.get("release"),
        )
    except Exception:
        return None


def _phase_score_from_preview(phase: dict[str, Any]) -> dict[str, Any]:
    scores = [
        float(sample["score"])
        for sample in phase.get("samples", [])
        if _safe_float(sample.get("score")) is not None
    ]
    phase_name = str(phase.get("phase") or "")
    phase_score = round(sum(scores) / len(scores), 2) if scores else None
    return {
        "phase": phase_name,
        "label": phase.get("label"),
        "score": phase_score,
        "weight": PHASE_WEIGHTS.get(phase_name, 0.0),
        "status": "ready" if phase_score is not None else "no_valid_step",
        "userStartFrame": phase.get("userStartFrame"),
        "userEndFrame": phase.get("userEndFrame"),
        "proStartFrame": phase.get("proStartFrame"),
        "proEndFrame": phase.get("proEndFrame"),
        "stepCount": phase.get("stepCount"),
        "validStepCount": len(scores),
        "scoreMethod": "fixed_step_pose_distance",
    }


def _weighted_overall_score(phase_scores: list[dict[str, Any]]) -> float | None:
    weighted_total = 0.0
    weight_total = 0.0
    for phase in phase_scores:
        score = _safe_float(phase.get("score"))
        weight = _safe_float(phase.get("weight")) or 0.0
        if score is None or weight <= 0:
            continue
        weighted_total += score * weight
        weight_total += weight
    return round(weighted_total / weight_total, 2) if weight_total > 0 else None


def _safe_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _unavailable_similarity(reason: str) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "algorithmName": ALGORITHM_NAME,
        "scoreScale": "0~100",
        "overallScore": None,
        "phaseScores": [],
        "release": {},
        "feedback": {"good": [], "bad": []},
        "phaseDetection": {},
        "normalization": {},
        "notes": [reason],
    }
