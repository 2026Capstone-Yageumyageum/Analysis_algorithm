from __future__ import annotations

import argparse
import csv
import json
import math
import os
from pathlib import Path
import sys
from typing import Any

import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
SERVICE_SERVER_ROOT = REPO_ROOT / "service" / "server"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
if str(SERVICE_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_SERVER_ROOT))

from analysis_algorithm.alignment.phase_dtw import constrained_dtw_path  # noqa: E402


DEFAULT_EXP_DIR = REPO_ROOT / "outputs" / "exp6"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "outputs" / "exp09_resampling_vs_pose_dtw"

PHASE_STEP_COUNTS = {
    "windup": 20,
    "leg_lift": 50,
    "stride": 45,
    "acceleration": 40,
    "follow_through": 35,
}
PHASE_WEIGHTS = {
    "windup": 0.10,
    "leg_lift": 0.20,
    "stride": 0.25,
    "acceleration": 0.30,
    "follow_through": 0.15,
}
POINT_SPECS = {
    "windup": (
        {"key": "throwing_shoulder", "side": "throwing", "joint": "shoulder"},
        {"key": "throwing_elbow", "side": "throwing", "joint": "elbow"},
        {"key": "throwing_wrist", "side": "throwing", "joint": "wrist"},
        {"key": "glove_shoulder", "side": "glove", "joint": "shoulder"},
        {"key": "glove_elbow", "side": "glove", "joint": "elbow"},
        {"key": "glove_wrist", "side": "glove", "joint": "wrist"},
        {"key": "hip_center", "kind": "center", "joints": ("left_hip", "right_hip")},
        {"key": "shoulder_center", "kind": "center", "joints": ("left_shoulder", "right_shoulder")},
    ),
    "leg_lift": (
        {"key": "throwing_elbow", "side": "throwing", "joint": "elbow"},
        {"key": "throwing_wrist", "side": "throwing", "joint": "wrist"},
        {"key": "glove_elbow", "side": "glove", "joint": "elbow"},
        {"key": "glove_wrist", "side": "glove", "joint": "wrist"},
        {"key": "stride_knee", "side": "stride", "joint": "knee"},
        {"key": "stride_ankle", "side": "stride", "joint": "ankle"},
        {"key": "stride_foot", "side": "stride", "joint": "foot_index"},
        {"key": "trail_knee", "side": "trail", "joint": "knee"},
    ),
    "stride": (
        {"key": "throwing_shoulder", "side": "throwing", "joint": "shoulder"},
        {"key": "throwing_elbow", "side": "throwing", "joint": "elbow"},
        {"key": "throwing_wrist", "side": "throwing", "joint": "wrist"},
        {"key": "stride_knee", "side": "stride", "joint": "knee"},
        {"key": "stride_ankle", "side": "stride", "joint": "ankle"},
        {"key": "stride_foot", "side": "stride", "joint": "foot_index"},
        {"key": "trail_knee", "side": "trail", "joint": "knee"},
        {"key": "trail_ankle", "side": "trail", "joint": "ankle"},
    ),
    "acceleration": (
        {"key": "throwing_shoulder", "side": "throwing", "joint": "shoulder"},
        {"key": "throwing_elbow", "side": "throwing", "joint": "elbow"},
        {"key": "throwing_wrist", "side": "throwing", "joint": "wrist"},
        {"key": "glove_shoulder", "side": "glove", "joint": "shoulder"},
        {"key": "glove_elbow", "side": "glove", "joint": "elbow"},
        {"key": "glove_wrist", "side": "glove", "joint": "wrist"},
        {"key": "shoulder_center", "kind": "center", "joints": ("left_shoulder", "right_shoulder")},
    ),
    "follow_through": (
        {"key": "throwing_shoulder", "side": "throwing", "joint": "shoulder"},
        {"key": "throwing_elbow", "side": "throwing", "joint": "elbow"},
        {"key": "throwing_wrist", "side": "throwing", "joint": "wrist"},
        {"key": "glove_shoulder", "side": "glove", "joint": "shoulder"},
        {"key": "glove_elbow", "side": "glove", "joint": "elbow"},
        {"key": "glove_wrist", "side": "glove", "joint": "wrist"},
        {"key": "shoulder_center", "kind": "center", "joints": ("left_shoulder", "right_shoulder")},
    ),
}
MIN_CONFIDENCE = 0.05
POSE_DISTANCE_SIGMA = 0.55


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare fixed-step pose resampling and pose-only phase DTW on existing motion tables."
    )
    parser.add_argument("--pro-motion-table", type=Path, default=DEFAULT_EXP_DIR / "pro" / "motion_table.csv")
    parser.add_argument("--user-motion-table", type=Path, default=DEFAULT_EXP_DIR / "user" / "motion_table.csv")
    parser.add_argument("--alignment-json", type=Path, default=DEFAULT_EXP_DIR / "phase_dtw_alignment.json")
    parser.add_argument("--pro-keypoints", type=Path, default=DEFAULT_EXP_DIR / "pro" / "keypoints.csv")
    parser.add_argument("--user-keypoints", type=Path, default=DEFAULT_EXP_DIR / "user" / "keypoints.csv")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--phase-source",
        choices=["service", "alignment"],
        default="service",
        help="Use current service phase detection from keypoints, or reuse an existing alignment JSON.",
    )
    parser.add_argument("--sigma", type=float, default=POSE_DISTANCE_SIGMA)
    parser.add_argument("--min-confidence", type=float, default=MIN_CONFIDENCE)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.phase_source == "service":
        missing = [path for path in (args.pro_keypoints, args.user_keypoints) if not path.exists()]
        if missing:
            for path in missing:
                print(f"Missing required input: {path}", file=sys.stderr)
            return 1
        pro_motion, user_motion, phase_infos, phase_source_meta = load_service_phase_inputs(args.pro_keypoints, args.user_keypoints)
    else:
        missing = [path for path in (args.pro_motion_table, args.user_motion_table, args.alignment_json) if not path.exists()]
        if missing:
            for path in missing:
                print(f"Missing required input: {path}", file=sys.stderr)
            return 1
        pro_motion = pd.read_csv(args.pro_motion_table)
        user_motion = pd.read_csv(args.user_motion_table)
        alignment = json.loads(args.alignment_json.read_text(encoding="utf-8"))
        phase_infos = [
            phase_info
            for item in alignment.get("phase_alignments", [])
            if isinstance(item, dict)
            for phase_info in [normalize_alignment_phase_info(item)]
            if phase_info is not None
        ]
        phase_source_meta = {
            "phase_source": "alignment_json",
            "phase_boundaries_source": str(args.alignment_json),
            "warnings": [],
        }

    config = {
        "phase_step_counts": PHASE_STEP_COUNTS,
        "phase_weights": PHASE_WEIGHTS,
        "min_confidence": args.min_confidence,
        "pose_distance_sigma_body_units": args.sigma,
        "pose_score_formula": "100 * exp(-0.5 * (joint_distance_body_units / sigma)^2)",
        "speed_used": False,
    }
    fixed_step = compute_fixed_step_similarity(
        pro_motion=pro_motion,
        user_motion=user_motion,
        phase_infos=phase_infos,
        min_confidence=args.min_confidence,
        sigma=args.sigma,
    )
    pose_dtw = compute_pose_dtw_similarity(
        pro_motion=pro_motion,
        user_motion=user_motion,
        phase_infos=phase_infos,
        min_confidence=args.min_confidence,
        sigma=args.sigma,
    )

    payload = {
        "experiment_type": "pose_resampling_vs_pose_dtw",
        "inputs": {
            "pro_motion_table": str(args.pro_motion_table) if args.phase_source == "alignment" else None,
            "user_motion_table": str(args.user_motion_table) if args.phase_source == "alignment" else None,
            "pro_keypoints": str(args.pro_keypoints) if args.phase_source == "service" else None,
            "user_keypoints": str(args.user_keypoints) if args.phase_source == "service" else None,
            **phase_source_meta,
        },
        "config": config,
        "fixed_step_resampling": fixed_step,
        "pose_dtw": pose_dtw,
        "comparison": build_comparison_summary(fixed_step, pose_dtw),
        "notes": [
            "두 방식 모두 body-frame 좌표의 자세만 비교하며 speed feature는 사용하지 않습니다.",
            "fixed_step_resampling은 phase 진행률을 고정 step으로 맞춘 뒤 같은 step끼리 비교합니다.",
            "pose_dtw는 phase 안에서 자세 벡터가 가까운 프레임쌍을 DTW로 찾은 뒤 같은 점수식으로 비교합니다.",
        ],
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.output_dir / "comparison.json", payload)
    write_phase_scores_csv(args.output_dir / "phase_scores.csv", fixed_step, pose_dtw)
    write_detail_csv(args.output_dir / "fixed_step_step_scores.csv", fixed_step["details"])
    write_detail_csv(args.output_dir / "pose_dtw_pair_scores.csv", pose_dtw["details"])
    write_report(args.output_dir / "report.md", payload)

    print(f"output_dir: {args.output_dir}")
    print(f"phase_source: {phase_source_meta['phase_source']}")
    print(f"fixed_step_overall: {fixed_step['overall_score']}")
    print(f"pose_dtw_overall: {pose_dtw['overall_score']}")
    return 0


def normalize_alignment_phase_info(item: dict[str, Any]) -> dict[str, Any] | None:
    phase_aliases = {
        "setup": "windup",
        "release": "acceleration",
    }
    phase = phase_aliases.get(str(item.get("phase")), str(item.get("phase")))
    if phase not in PHASE_STEP_COUNTS:
        return None
    return {**item, "phase": phase}


def load_service_phase_inputs(
    pro_keypoints_path: Path,
    user_keypoints_path: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, list[dict[str, Any]], dict[str, Any]]:
    from analysis.normalization import build_body_frame_pose
    from analysis.phase import detect_pitch_phases

    pro_keypoints = pd.read_csv(pro_keypoints_path)
    user_keypoints = pd.read_csv(user_keypoints_path)
    pro_pose = build_body_frame_pose(pro_keypoints)
    user_pose = build_body_frame_pose(user_keypoints)
    pro_phases = detect_pitch_phases(pro_pose.table)
    user_phases = detect_pitch_phases(user_pose.table)
    phase_infos = []
    for phase in PHASE_STEP_COUNTS:
        pro_interval = pro_phases.intervals.get(phase)
        user_interval = user_phases.intervals.get(phase)
        if pro_interval is None or user_interval is None:
            continue
        phase_infos.append(
            {
                "phase": phase,
                "left_start_frame": int(pro_interval["startFrame"]),
                "left_end_frame": int(pro_interval["endFrame"]),
                "right_start_frame": int(user_interval["startFrame"]),
                "right_end_frame": int(user_interval["endFrame"]),
                "left_frame_count": int(pro_interval["endFrame"]) - int(pro_interval["startFrame"]) + 1,
                "right_frame_count": int(user_interval["endFrame"]) - int(user_interval["startFrame"]) + 1,
            }
        )

    return (
        pro_pose.table,
        user_pose.table,
        phase_infos,
        {
            "phase_source": "service_phase_detection_v1",
            "phase_boundaries_source": "service/server/analysis/phase.py",
            "warnings": {
                "pro": pro_pose.warnings + pro_phases.warnings,
                "user": user_pose.warnings + user_phases.warnings,
            },
        },
    )


def compute_fixed_step_similarity(
    pro_motion: pd.DataFrame,
    user_motion: pd.DataFrame,
    phase_infos: list[dict[str, Any]],
    min_confidence: float,
    sigma: float,
) -> dict[str, Any]:
    phase_scores: list[dict[str, Any]] = []
    details: list[dict[str, Any]] = []

    for phase_info in phase_infos:
        phase = str(phase_info["phase"])
        specs = POINT_SPECS[phase]
        step_count = PHASE_STEP_COUNTS[phase]
        pro_samples = resample_phase(pro_motion, phase_info, "left", specs, step_count)
        user_samples = resample_phase(user_motion, phase_info, "right", specs, step_count)
        phase_result = score_sample_sequences(
            phase=phase,
            pro_samples=pro_samples,
            user_samples=user_samples,
            specs=specs,
            min_confidence=min_confidence,
            sigma=sigma,
        )
        phase_scores.append(
            {
                "method": "fixed_step_resampling",
                "phase": phase,
                "score": phase_result["score"],
                "status": phase_result["status"],
                "step_count": step_count,
                "valid_sample_count": phase_result["valid_sample_count"],
                "valid_joint_sample_count": phase_result["valid_joint_sample_count"],
                "mean_pose_distance": phase_result["mean_pose_distance"],
                "pro_frame_count": int(phase_info.get("left_frame_count") or 0),
                "user_frame_count": int(phase_info.get("right_frame_count") or 0),
            }
        )
        details.extend(phase_result["details"])

    return summarize_method("fixed_step_resampling", phase_scores, details)


def compute_pose_dtw_similarity(
    pro_motion: pd.DataFrame,
    user_motion: pd.DataFrame,
    phase_infos: list[dict[str, Any]],
    min_confidence: float,
    sigma: float,
) -> dict[str, Any]:
    pro_lookup = build_row_lookup(pro_motion)
    user_lookup = build_row_lookup(user_motion)
    phase_scores: list[dict[str, Any]] = []
    details: list[dict[str, Any]] = []

    for phase_info in phase_infos:
        phase = str(phase_info["phase"])
        specs = POINT_SPECS[phase]
        pro_segment = phase_segment(pro_motion, phase_info, "left")
        user_segment = phase_segment(user_motion, phase_info, "right")
        pro_matrix = build_pose_matrix(pro_segment, specs)
        user_matrix = build_pose_matrix(user_segment, specs)
        if pro_matrix is None or user_matrix is None:
            phase_scores.append(
                {
                    "method": "pose_dtw",
                    "phase": phase,
                    "score": None,
                    "status": "insufficient_pose_matrix",
                    "aligned_pair_count": 0,
                    "valid_pair_count": 0,
                    "valid_joint_sample_count": 0,
                    "mean_pose_distance": None,
                    "pro_frame_count": int(len(pro_segment)),
                    "user_frame_count": int(len(user_segment)),
                }
            )
            continue

        path_indices, band, fallback_used = constrained_dtw_path(pro_matrix, user_matrix)
        pro_frames = pro_segment["frame_index"].astype(int).to_numpy()
        user_frames = user_segment["frame_index"].astype(int).to_numpy()
        pair_rows: list[dict[str, Any]] = []
        for pair_index, (pro_index, user_index) in enumerate(path_indices):
            pro_frame = int(pro_frames[pro_index])
            user_frame = int(user_frames[user_index])
            score_row = score_pose_pair(
                phase=phase,
                sample_index=pair_index,
                pro_row=pro_lookup[pro_frame],
                user_row=user_lookup[user_frame],
                specs=specs,
                min_confidence=min_confidence,
                sigma=sigma,
                pro_frame=pro_frame,
                user_frame=user_frame,
            )
            pair_rows.append(score_row)
            details.append({"method": "pose_dtw", **score_row})

        phase_result = aggregate_score_rows(pair_rows)
        phase_scores.append(
            {
                "method": "pose_dtw",
                "phase": phase,
                "score": phase_result["score"],
                "status": phase_result["status"],
                "aligned_pair_count": len(path_indices),
                "valid_pair_count": phase_result["valid_sample_count"],
                "valid_joint_sample_count": phase_result["valid_joint_sample_count"],
                "mean_pose_distance": phase_result["mean_pose_distance"],
                "band": int(band),
                "fallback_used": bool(fallback_used),
                "pro_frame_count": int(len(pro_segment)),
                "user_frame_count": int(len(user_segment)),
            }
        )

    return summarize_method("pose_dtw", phase_scores, details)


def resample_phase(
    motion_table: pd.DataFrame,
    phase_info: dict[str, Any],
    side_prefix: str,
    specs: tuple[dict[str, Any], ...],
    step_count: int,
) -> list[dict[str, Any]]:
    segment = phase_segment(motion_table, phase_info, side_prefix)
    if segment.empty:
        return []

    start_frame = float(phase_info[f"{side_prefix}_start_frame"])
    end_frame = float(phase_info[f"{side_prefix}_end_frame"])
    target_frames = np.linspace(start_frame, end_frame, step_count) if step_count > 1 else np.array([start_frame])
    frames = segment["frame_index"].astype(float).to_numpy()
    samples: list[dict[str, Any]] = []
    point_series = {spec["key"]: build_point_series(segment, spec) for spec in specs}

    for step_index, target_frame in enumerate(target_frames):
        points = {}
        for spec in specs:
            x_values, y_values, confidence_values = point_series[spec["key"]]
            points[spec["key"]] = {
                "x": interpolate_values(frames, x_values, target_frame),
                "y": interpolate_values(frames, y_values, target_frame),
                "confidence": interpolate_values(frames, confidence_values, target_frame, fallback=0.0),
            }
        samples.append(
            {
                "step_index": step_index,
                "target_frame": round(float(target_frame), 4),
                "progress": round(float(step_index / max(1, step_count - 1)), 6),
                "points": points,
            }
        )
    return samples


def phase_segment(motion_table: pd.DataFrame, phase_info: dict[str, Any], side_prefix: str) -> pd.DataFrame:
    start_frame = int(phase_info[f"{side_prefix}_start_frame"])
    end_frame = int(phase_info[f"{side_prefix}_end_frame"])
    frame_values = motion_table["frame_index"].astype(int)
    return motion_table[(frame_values >= start_frame) & (frame_values <= end_frame)].sort_values("frame_index").reset_index(drop=True)


def build_pose_matrix(segment: pd.DataFrame, specs: tuple[dict[str, Any], ...]) -> np.ndarray | None:
    if len(segment) < 2:
        return None
    columns = []
    for spec in specs:
        x_values, y_values, _ = build_point_series(segment, spec)
        columns.extend([x_values, y_values])
    matrix_df = pd.DataFrame({index: column for index, column in enumerate(columns)})
    matrix_df = matrix_df.apply(pd.to_numeric, errors="coerce").interpolate(axis=0, limit_direction="both").fillna(0.0)
    matrix = matrix_df.to_numpy(dtype=float)
    if matrix.ndim != 2 or matrix.shape[0] < 2:
        return None
    return matrix


def build_point_series(segment: pd.DataFrame, spec: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    points = [resolve_point(row, spec) for _, row in segment.iterrows()]
    x_values = pd.Series([point[0] if point else np.nan for point in points], dtype="float64")
    y_values = pd.Series([point[1] if point else np.nan for point in points], dtype="float64")
    confidence_values = pd.Series([point[2] if point else 0.0 for point in points], dtype="float64")
    return (
        x_values.interpolate(limit_direction="both").to_numpy(dtype=float),
        y_values.interpolate(limit_direction="both").to_numpy(dtype=float),
        confidence_values.interpolate(limit_direction="both").fillna(0.0).to_numpy(dtype=float),
    )


def resolve_point(row: pd.Series, spec: dict[str, Any]) -> tuple[float, float, float] | None:
    if spec.get("kind") == "center":
        joints = tuple(spec["joints"])
        points = [joint_point(row, joint) for joint in joints]
        if any(point is None for point in points):
            return None
        x = float(sum(point[0] for point in points if point) / len(points))
        y = float(sum(point[1] for point in points if point) / len(points))
        confidence = float(sum(point[2] for point in points if point) / len(points))
        return x, y, confidence

    side = resolve_side(row, str(spec["side"]))
    if side is None:
        return None
    return joint_point(row, f"{side}_{spec['joint']}")


def resolve_side(row: pd.Series, side_kind: str) -> str | None:
    throwing_side = normalized_side(row.get("throwing_side"))
    stride_side = normalized_side(row.get("stride_side"))
    if side_kind == "throwing":
        return throwing_side
    if side_kind == "glove":
        return opposite_side(throwing_side)
    if side_kind == "stride":
        return stride_side
    if side_kind == "trail":
        return opposite_side(stride_side)
    return None


def normalized_side(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    return text if text in {"left", "right"} else None


def opposite_side(side: str | None) -> str | None:
    if side == "left":
        return "right"
    if side == "right":
        return "left"
    return None


def joint_point(row: pd.Series, joint: str) -> tuple[float, float, float] | None:
    x = safe_float(row.get(f"{joint}_body_x"))
    y = safe_float(row.get(f"{joint}_body_y"))
    confidence = safe_float(row.get(f"{joint}_confidence"), fallback=0.0)
    if x is None or y is None or confidence is None:
        return None
    return x, y, confidence


def score_sample_sequences(
    phase: str,
    pro_samples: list[dict[str, Any]],
    user_samples: list[dict[str, Any]],
    specs: tuple[dict[str, Any], ...],
    min_confidence: float,
    sigma: float,
) -> dict[str, Any]:
    score_rows = []
    for sample_index, (pro_sample, user_sample) in enumerate(zip(pro_samples, user_samples)):
        score_row = score_point_sets(
            phase=phase,
            sample_index=sample_index,
            pro_points=pro_sample["points"],
            user_points=user_sample["points"],
            specs=specs,
            min_confidence=min_confidence,
            sigma=sigma,
            pro_frame=pro_sample["target_frame"],
            user_frame=user_sample["target_frame"],
        )
        score_rows.append(score_row)
    aggregate = aggregate_score_rows(score_rows)
    aggregate["details"] = [{"method": "fixed_step_resampling", **row} for row in score_rows]
    return aggregate


def score_pose_pair(
    phase: str,
    sample_index: int,
    pro_row: pd.Series,
    user_row: pd.Series,
    specs: tuple[dict[str, Any], ...],
    min_confidence: float,
    sigma: float,
    pro_frame: int,
    user_frame: int,
) -> dict[str, Any]:
    pro_points = {}
    user_points = {}
    for spec in specs:
        pro_point = resolve_point(pro_row, spec)
        user_point = resolve_point(user_row, spec)
        pro_points[spec["key"]] = point_dict(pro_point)
        user_points[spec["key"]] = point_dict(user_point)
    return score_point_sets(
        phase=phase,
        sample_index=sample_index,
        pro_points=pro_points,
        user_points=user_points,
        specs=specs,
        min_confidence=min_confidence,
        sigma=sigma,
        pro_frame=pro_frame,
        user_frame=user_frame,
    )


def score_point_sets(
    phase: str,
    sample_index: int,
    pro_points: dict[str, dict[str, float | None]],
    user_points: dict[str, dict[str, float | None]],
    specs: tuple[dict[str, Any], ...],
    min_confidence: float,
    sigma: float,
    pro_frame: float | int,
    user_frame: float | int,
) -> dict[str, Any]:
    weighted_total = 0.0
    weight_total = 0.0
    distances: list[float] = []
    valid_points = 0

    for spec in specs:
        key = spec["key"]
        pro = pro_points.get(key, {})
        user = user_points.get(key, {})
        pro_confidence = safe_float(pro.get("confidence"), fallback=0.0) or 0.0
        user_confidence = safe_float(user.get("confidence"), fallback=0.0) or 0.0
        pro_x = safe_float(pro.get("x"))
        pro_y = safe_float(pro.get("y"))
        user_x = safe_float(user.get("x"))
        user_y = safe_float(user.get("y"))
        if min(pro_confidence, user_confidence) < min_confidence:
            continue
        if None in (pro_x, pro_y, user_x, user_y):
            continue

        distance = float(math.dist((pro_x, pro_y), (user_x, user_y)))
        score = pose_distance_to_score(distance, sigma=sigma)
        weight = math.sqrt(max(0.0, pro_confidence) * max(0.0, user_confidence))
        weighted_total += score * weight
        weight_total += weight
        distances.append(distance)
        valid_points += 1

    sample_score = round(weighted_total / weight_total, 2) if weight_total > 0 else None
    return {
        "phase": phase,
        "sample_index": sample_index,
        "pro_frame": pro_frame,
        "user_frame": user_frame,
        "score": sample_score,
        "valid_point_count": valid_points,
        "weight_total": round(weight_total, 4),
        "mean_pose_distance": round(float(np.mean(distances)), 6) if distances else None,
        "status": "ready" if sample_score is not None else "no_valid_points",
    }


def aggregate_score_rows(score_rows: list[dict[str, Any]]) -> dict[str, Any]:
    weighted_total = 0.0
    weight_total = 0.0
    distances: list[float] = []
    valid_sample_count = 0
    valid_joint_sample_count = 0

    for row in score_rows:
        score = safe_float(row.get("score"))
        weight = safe_float(row.get("weight_total"), fallback=0.0) or 0.0
        if score is None or weight <= 0:
            continue
        weighted_total += score * weight
        weight_total += weight
        valid_sample_count += 1
        valid_joint_sample_count += int(row.get("valid_point_count") or 0)
        distance = safe_float(row.get("mean_pose_distance"))
        if distance is not None:
            distances.append(distance)

    return {
        "score": round(weighted_total / weight_total, 2) if weight_total > 0 else None,
        "status": "ready" if weight_total > 0 else "no_valid_samples",
        "valid_sample_count": valid_sample_count,
        "valid_joint_sample_count": valid_joint_sample_count,
        "mean_pose_distance": round(float(np.mean(distances)), 6) if distances else None,
    }


def summarize_method(method: str, phase_scores: list[dict[str, Any]], details: list[dict[str, Any]]) -> dict[str, Any]:
    weighted_total = 0.0
    weight_total = 0.0
    for row in phase_scores:
        phase = str(row.get("phase"))
        score = safe_float(row.get("score"))
        if score is None:
            continue
        weight = PHASE_WEIGHTS.get(phase, 0.0)
        weighted_total += score * weight
        weight_total += weight
    return {
        "method": method,
        "overall_score": round(weighted_total / weight_total, 2) if weight_total > 0 else None,
        "phase_scores": phase_scores,
        "details": details,
    }


def build_comparison_summary(fixed_step: dict[str, Any], pose_dtw: dict[str, Any]) -> dict[str, Any]:
    fixed_score = safe_float(fixed_step.get("overall_score"))
    dtw_score = safe_float(pose_dtw.get("overall_score"))
    delta = None if fixed_score is None or dtw_score is None else round(dtw_score - fixed_score, 2)
    return {
        "fixed_step_overall_score": fixed_score,
        "pose_dtw_overall_score": dtw_score,
        "pose_dtw_minus_fixed_step": delta,
        "interpretation": (
            "DTW 점수가 더 높다면 phase 내부 타이밍 어긋남을 DTW가 흡수한 것으로 해석할 수 있습니다."
            if delta is not None and delta > 0
            else "고정 step 점수가 더 높거나 비슷하다면 진행률 기준 비교만으로도 충분히 정렬된 것으로 볼 수 있습니다."
        ),
    }


def pose_distance_to_score(distance: float, sigma: float) -> float:
    if not math.isfinite(distance) or sigma <= 0:
        return 0.0
    return round(100.0 * math.exp(-0.5 * ((distance / sigma) ** 2)), 2)


def point_dict(point: tuple[float, float, float] | None) -> dict[str, float | None]:
    if point is None:
        return {"x": None, "y": None, "confidence": 0.0}
    return {"x": point[0], "y": point[1], "confidence": point[2]}


def interpolate_values(frames: np.ndarray, values: np.ndarray, target_frame: float, fallback: float | None = None) -> float | None:
    if len(frames) == 0:
        return fallback
    finite_mask = np.isfinite(frames) & np.isfinite(values)
    if not finite_mask.any():
        return fallback
    return float(np.interp(float(target_frame), frames[finite_mask], values[finite_mask]))


def build_row_lookup(table: pd.DataFrame) -> dict[int, pd.Series]:
    return {int(row["frame_index"]): row for _, row in table.iterrows()}


def safe_float(value: Any, fallback: float | None = None) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if math.isfinite(parsed) else fallback


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(make_json_safe(payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_phase_scores_csv(path: Path, fixed_step: dict[str, Any], pose_dtw: dict[str, Any]) -> None:
    rows = fixed_step["phase_scores"] + pose_dtw["phase_scores"]
    fieldnames = sorted({key for row in rows for key in row})
    write_csv(path, rows, fieldnames)


def write_detail_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = (
        "method",
        "phase",
        "sample_index",
        "pro_frame",
        "user_frame",
        "score",
        "valid_point_count",
        "weight_total",
        "mean_pose_distance",
        "status",
    )
    write_csv(path, rows, fieldnames)


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | tuple[str, ...]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(make_json_safe(row) for row in rows)


def write_report(path: Path, payload: dict[str, Any]) -> None:
    fixed_step = payload["fixed_step_resampling"]
    pose_dtw = payload["pose_dtw"]
    comparison = payload["comparison"]
    inputs = payload["inputs"]
    lines = [
        "# 고정 step 리샘플링 vs pose-only DTW 비교",
        "",
        "## 목적",
        "",
        "속도 feature를 제외하고 자세만 비교할 때, phase 진행률 기준 고정 step 리샘플링과 phase 내부 DTW 정렬 중 어떤 방식이 더 적절한지 확인합니다.",
        "",
        "## 입력 기준",
        "",
        f"- phase source: {inputs.get('phase_source')}",
        f"- phase boundaries: {inputs.get('phase_boundaries_source')}",
        "",
        "## 전체 결과",
        "",
        f"- 고정 step 리샘플링 overall: {fixed_step['overall_score']}",
        f"- pose-only DTW overall: {pose_dtw['overall_score']}",
        f"- DTW - 고정 step: {comparison['pose_dtw_minus_fixed_step']}",
        "",
        "## Phase별 결과",
        "",
        "| phase | fixed step | pose-only DTW | 차이(DTW-fixed) |",
        "| --- | ---: | ---: | ---: |",
    ]
    fixed_by_phase = {row["phase"]: row for row in fixed_step["phase_scores"]}
    dtw_by_phase = {row["phase"]: row for row in pose_dtw["phase_scores"]}
    for phase in PHASE_STEP_COUNTS:
        fixed_score = safe_float(fixed_by_phase.get(phase, {}).get("score"))
        dtw_score = safe_float(dtw_by_phase.get(phase, {}).get("score"))
        delta = None if fixed_score is None or dtw_score is None else round(dtw_score - fixed_score, 2)
        lines.append(f"| {phase} | {format_score(fixed_score)} | {format_score(dtw_score)} | {format_score(delta)} |")

    lines.extend(
        [
            "",
            "## Phase 프레임 수",
            "",
            "| phase | pro frames | user frames | fixed steps | DTW pairs |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for phase in PHASE_STEP_COUNTS:
        fixed_row = fixed_by_phase.get(phase, {})
        dtw_row = dtw_by_phase.get(phase, {})
        lines.append(
            "| "
            f"{phase} | "
            f"{fixed_row.get('pro_frame_count', '-')} | "
            f"{fixed_row.get('user_frame_count', '-')} | "
            f"{fixed_row.get('step_count', '-')} | "
            f"{dtw_row.get('aligned_pair_count', '-')} |"
        )

    lines.extend(
        [
            "",
            "## 해석",
            "",
            f"- {comparison['interpretation']}",
            "- fixed step 방식은 각 phase를 동일한 진행률의 자세 sequence로 바꾼 뒤 같은 step끼리 비교합니다.",
            "- pose-only DTW 방식은 phase 안에서 자세 벡터가 가까운 프레임쌍을 먼저 찾고, 같은 점수식으로 자세 차이를 계산합니다.",
            "- 둘 다 skeleton 좌표만 사용하며, 관절 속도 feature는 사용하지 않았습니다.",
        "",
            "## 주의",
            "",
            "- phase 탐지 경계가 흔들리면 두 비교 방식 모두 영향을 받습니다.",
            "- 특정 phase의 원본 프레임 수가 기준 step보다 매우 적으면 fixed step은 보간 비중이 커지고, DTW는 정렬 pair가 제한됩니다.",
        "",
            "## Phase Detection Warnings",
            "",
            *format_warnings(inputs.get("warnings")),
            "",
            "## 산출물",
            "",
            "- `comparison.json`: 전체 비교 결과",
            "- `phase_scores.csv`: method/phase별 요약 점수",
            "- `fixed_step_step_scores.csv`: 고정 step별 자세 점수",
            "- `pose_dtw_pair_scores.csv`: DTW 정렬 pair별 자세 점수",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def format_score(value: float | None) -> str:
    return "-" if value is None else f"{value:.2f}"


def format_warnings(warnings: Any) -> list[str]:
    if not warnings:
        return ["- 없음"]
    if isinstance(warnings, dict):
        lines: list[str] = []
        for label, items in warnings.items():
            if not items:
                lines.append(f"- {label}: 없음")
            elif isinstance(items, list):
                lines.extend(f"- {label}: {item}" for item in items)
            else:
                lines.append(f"- {label}: {items}")
        return lines
    if isinstance(warnings, list):
        return [f"- {item}" for item in warnings] or ["- 없음"]
    return [f"- {warnings}"]


def make_json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): make_json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [make_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [make_json_safe(item) for item in value]
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    return value


if __name__ == "__main__":
    os.environ.setdefault("PYTHONWARNINGS", "ignore")
    raise SystemExit(main())
