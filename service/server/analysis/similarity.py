from __future__ import annotations

import math
from io import StringIO
from typing import Any

import numpy as np
import pandas as pd

from analysis.normalization import build_body_frame_pose
from analysis.phase import detect_pitch_phases


PHASE_WEIGHTS = {
    "leg_lift": 0.25,
    "stride": 0.30,
    "release": 0.30,
    "follow_through": 0.15,
}
JOINTS_BY_PHASE = {
    "leg_lift": ("left_knee", "right_knee", "left_ankle", "right_ankle", "left_wrist", "right_wrist"),
    "stride": ("left_foot_index", "right_foot_index", "left_knee", "right_knee", "left_wrist", "right_wrist"),
    "release": ("left_shoulder", "right_shoulder", "left_elbow", "right_elbow", "left_wrist", "right_wrist"),
    "follow_through": ("left_shoulder", "right_shoulder", "left_elbow", "right_elbow", "left_wrist", "right_wrist"),
}
MIN_JOINT_CONFIDENCE = 0.05


def compute_similarity(user_csv_text: str, pro_csv_text: str) -> dict[str, Any]:
    user_df = pd.read_csv(StringIO(user_csv_text))
    pro_df = pd.read_csv(StringIO(pro_csv_text))
    if user_df.empty or pro_df.empty:
        return _unavailable_similarity("keypoints CSV에 프레임 데이터가 없습니다.")

    user_pose = build_body_frame_pose(user_df)
    pro_pose = build_body_frame_pose(pro_df)
    if user_pose.table.empty or pro_pose.table.empty:
        return _unavailable_similarity("body-frame 정규화 좌표를 만들 수 없습니다.")

    user_phases = detect_pitch_phases(user_pose.table)
    pro_phases = detect_pitch_phases(pro_pose.table)
    phase_scores = []
    weighted_total = 0.0
    weight_total = 0.0

    for phase_name, user_interval in user_phases.intervals.items():
        pro_interval = pro_phases.intervals.get(phase_name)
        if pro_interval is None:
            continue
        user_start, user_end = _phase_boundary_rows(user_pose.table, user_interval)
        pro_start, pro_end = _phase_boundary_rows(pro_pose.table, pro_interval)
        joint_rows = []
        weighted_joint_total = 0.0
        joint_weight_total = 0.0

        for joint in JOINTS_BY_PHASE[phase_name]:
            row = _joint_direction_score(user_start, user_end, pro_start, pro_end, joint)
            joint_rows.append(row)
            if row["score"] is not None:
                confidence_weight = float(row["confidenceWeight"])
                weighted_joint_total += float(row["score"]) * confidence_weight
                joint_weight_total += confidence_weight

        phase_score = round(weighted_joint_total / joint_weight_total, 2) if joint_weight_total > 0 else None
        status = "ready" if phase_score is not None else "no_valid_joint"
        if phase_score is not None:
            weight = PHASE_WEIGHTS[phase_name]
            weighted_total += phase_score * weight
            weight_total += weight

        phase_scores.append(
            {
                "phase": phase_name,
                "label": user_interval["label"],
                "score": phase_score,
                "weight": PHASE_WEIGHTS[phase_name],
                "status": status,
                "userStartFrame": int(user_start["frame_index"]),
                "userEndFrame": int(user_end["frame_index"]),
                "proStartFrame": int(pro_start["frame_index"]),
                "proEndFrame": int(pro_end["frame_index"]),
                "validJointCount": len([row for row in joint_rows if row["score"] is not None]),
                "jointWeightTotal": round(joint_weight_total, 4),
                "jointScores": joint_rows,
            }
        )

    overall = round(weighted_total / weight_total, 2) if weight_total > 0 else None
    return {
        "status": "ready" if overall is not None else "no_score",
        "algorithmName": "body_frame_phase_direction_vector_v1",
        "scoreScale": "0~100",
        "overallScore": overall,
        "phaseScores": phase_scores,
        "phaseDetection": {
            "user": {
                "representativeFrames": user_phases.representative_frames,
                "intervals": user_phases.intervals,
                "warnings": user_phases.warnings,
            },
            "pro": {
                "representativeFrames": pro_phases.representative_frames,
                "intervals": pro_phases.intervals,
                "warnings": pro_phases.warnings,
            },
        },
        "normalization": {
            "user": user_pose.summary,
            "pro": pro_pose.summary,
            "warnings": {"user": user_pose.warnings, "pro": pro_pose.warnings},
        },
        "notes": [
            "pelvis/torso/body-scale 기반 분석 좌표에서 phase별 시작-끝 관절 방향 벡터를 비교합니다.",
            "프론트 표시용 0~1 좌표와 점수 계산용 body-frame 좌표를 분리했습니다.",
            "phase 내부 세부 궤적은 아직 반영하지 않습니다.",
        ],
    }


def _phase_boundary_rows(df: pd.DataFrame, interval: dict[str, Any]) -> tuple[pd.Series, pd.Series]:
    start_row = _nearest_frame_row(df, int(interval["startFrame"]))
    end_row = _nearest_frame_row(df, int(interval["endFrame"]))
    return start_row, end_row


def _nearest_frame_row(df: pd.DataFrame, frame_index: int) -> pd.Series:
    distances = (df["frame_index"].astype(int) - frame_index).abs()
    return df.loc[int(distances.idxmin())]


def _joint_direction_score(
    user_start: pd.Series,
    user_end: pd.Series,
    pro_start: pd.Series,
    pro_end: pd.Series,
    joint: str,
) -> dict[str, Any]:
    user_confidence = _joint_boundary_confidence(user_start, user_end, joint)
    pro_confidence = _joint_boundary_confidence(pro_start, pro_end, joint)
    if min(user_confidence, pro_confidence) < MIN_JOINT_CONFIDENCE:
        return {
            "joint": joint,
            "score": None,
            "status": "low_confidence",
            "userConfidence": round(user_confidence, 4),
            "proConfidence": round(pro_confidence, 4),
            "confidenceWeight": 0.0,
        }

    user_vector = _joint_vector(user_start, user_end, joint)
    pro_vector = _joint_vector(pro_start, pro_end, joint)
    user_norm = float(np.linalg.norm(user_vector))
    pro_norm = float(np.linalg.norm(pro_vector))
    if user_norm < 1e-6 or pro_norm < 1e-6:
        return {
            "joint": joint,
            "score": None,
            "status": "too_small_motion",
            "userConfidence": round(user_confidence, 4),
            "proConfidence": round(pro_confidence, 4),
            "confidenceWeight": 0.0,
        }

    cosine = float(np.clip(np.dot(user_vector / user_norm, pro_vector / pro_norm), -1.0, 1.0))
    confidence_weight = math.sqrt(max(0.0, user_confidence) * max(0.0, pro_confidence))
    return {
        "joint": joint,
        "score": round(((cosine + 1.0) / 2.0) * 100.0, 2),
        "status": "used",
        "cosineSimilarity": round(cosine, 4),
        "userConfidence": round(user_confidence, 4),
        "proConfidence": round(pro_confidence, 4),
        "confidenceWeight": round(confidence_weight, 4),
    }


def _joint_vector(start: pd.Series, end: pd.Series, joint: str) -> np.ndarray:
    x_key = f"{joint}_body_x"
    y_key = f"{joint}_body_y"
    if x_key not in start or y_key not in start:
        return np.array([0.0, 0.0], dtype=float)
    return np.array(
        [
            _safe_float(end.get(x_key)) - _safe_float(start.get(x_key)),
            _safe_float(end.get(y_key)) - _safe_float(start.get(y_key)),
        ],
        dtype=float,
    )


def _joint_boundary_confidence(start: pd.Series, end: pd.Series, joint: str) -> float:
    confidence_key = f"{joint}_confidence"
    if confidence_key not in start:
        return 1.0
    return (_safe_float(start.get(confidence_key)) + _safe_float(end.get(confidence_key))) / 2.0


def _safe_float(value: Any) -> float:
    try:
        output = float(value)
    except (TypeError, ValueError):
        return 0.0
    return output if math.isfinite(output) else 0.0


def _unavailable_similarity(reason: str) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "algorithmName": "body_frame_phase_direction_vector_v1",
        "scoreScale": "0~100",
        "overallScore": None,
        "phaseScores": [],
        "phaseDetection": {},
        "normalization": {},
        "notes": [reason],
    }
