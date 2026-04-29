from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

import pandas as pd

from analysis_algorithm.alignment.phase_dtw import align_feature_sequences
from analysis_algorithm.features.motion_features import extract_motion_features
from analysis_algorithm.phase.detection import detect_pitching_phases
from analysis_algorithm.pose.mediapipe_extractor import MediaPipePoseEstimator
from analysis_algorithm.visualization.normalized_overlay import (
    build_motion_table,
    render_dtw_overlay_video,
    render_normalized_overlay_video,
)


@dataclass
class VideoAnalysisResult:
    label: str
    video_path: Path
    output_dir: Path
    keypoints_path: Path
    features_path: Path
    motion_table_path: Path
    keypoints_df: pd.DataFrame
    features_df: pd.DataFrame
    motion_table: pd.DataFrame
    metadata: dict[str, Any]
    phase_frames: dict[str, int | None]
    warnings: list[str]
    fps: float
    frame_count: int


def create_next_experiment_dir(output_root: Path) -> Path:
    output_root.mkdir(parents=True, exist_ok=True)
    existing_numbers = []
    for child in output_root.iterdir():
        if child.is_dir() and child.name.startswith("exp") and child.name[3:].isdigit():
            existing_numbers.append(int(child.name[3:]))
    experiment_dir = output_root / f"exp{max(existing_numbers, default=0) + 1}"
    experiment_dir.mkdir(parents=True, exist_ok=False)
    return experiment_dir


def analyze_video(
    video_path: Path,
    output_dir: Path,
    label: str,
    height_cm: float | None = None,
    handedness: str | None = None,
) -> VideoAnalysisResult:
    if not video_path.exists():
        raise FileNotFoundError(f"Video does not exist: {video_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    estimator = MediaPipePoseEstimator()
    pose_result = estimator.process_video(video_path)
    if pose_result.keypoints_df.empty:
        raise RuntimeError(f"No keypoints were extracted from {video_path}")

    feature_result = extract_motion_features(
        pose_result.keypoints_df,
        fps=pose_result.fps,
        handedness_override=handedness,
        input_height_cm=height_cm,
    )
    phase_result = detect_pitching_phases(
        keypoints_df=pose_result.keypoints_df,
        features_df=feature_result.features_df,
        metadata=feature_result.metadata,
    )
    motion_table = build_motion_table(
        label=label,
        keypoints_df=pose_result.keypoints_df,
        features_df=feature_result.features_df,
        metadata=feature_result.metadata,
        phase_frames=phase_result.representative_frames,
        fps=pose_result.fps,
    )

    keypoints_path = output_dir / "keypoints.csv"
    features_path = output_dir / "features.csv"
    motion_table_path = output_dir / "motion_table.csv"
    pose_result.keypoints_df.to_csv(keypoints_path, index=False)
    feature_result.features_df.to_csv(features_path, index=False)
    motion_table.to_csv(motion_table_path, index=False)

    warnings = pose_result.warnings + feature_result.warnings + phase_result.warnings
    summary = {
        "label": label,
        "video_path": str(video_path),
        "pose_model": estimator.model_name,
        "fps": pose_result.fps,
        "frame_count": pose_result.frame_count,
        "phase_frames": phase_result.representative_frames,
        "metadata": feature_result.metadata,
        "warnings": warnings,
        "outputs": {
            "keypoints": str(keypoints_path),
            "features": str(features_path),
            "motion_table": str(motion_table_path),
        },
    }
    write_json(output_dir / "summary.json", summary)

    return VideoAnalysisResult(
        label=label,
        video_path=video_path,
        output_dir=output_dir,
        keypoints_path=keypoints_path,
        features_path=features_path,
        motion_table_path=motion_table_path,
        keypoints_df=pose_result.keypoints_df,
        features_df=feature_result.features_df,
        motion_table=motion_table,
        metadata=feature_result.metadata,
        phase_frames=phase_result.representative_frames,
        warnings=warnings,
        fps=pose_result.fps,
        frame_count=pose_result.frame_count,
    )


def run_pair_experiment(
    pro_video: Path,
    user_video: Path,
    output_root: Path,
    pro_height_cm: float | None = None,
    user_height_cm: float | None = None,
    pro_handedness: str | None = None,
    user_handedness: str | None = None,
    render_overlay: bool = True,
) -> dict[str, Any]:
    experiment_dir = create_next_experiment_dir(output_root)
    pro_result = analyze_video(
        video_path=pro_video,
        output_dir=experiment_dir / "pro",
        label="pro",
        height_cm=pro_height_cm,
        handedness=pro_handedness,
    )
    user_result = analyze_video(
        video_path=user_video,
        output_dir=experiment_dir / "user",
        label="user",
        height_cm=user_height_cm,
        handedness=user_handedness,
    )

    alignment = align_feature_sequences(
        left_features_df=pro_result.features_df,
        right_features_df=user_result.features_df,
        left_phase_frames=pro_result.phase_frames,
        right_phase_frames=user_result.phase_frames,
    )
    alignment_path = experiment_dir / "phase_dtw_alignment.json"
    write_json(alignment_path, alignment)

    overlay_outputs: dict[str, str | None] = {"normalized_overlay": None, "phase_dtw_overlay": None}
    if render_overlay:
        normalized_overlay_path = experiment_dir / "normalized_overlay.mp4"
        if render_normalized_overlay_video(
            left_table=pro_result.motion_table,
            right_table=user_result.motion_table,
            output_path=normalized_overlay_path,
            left_label="pro",
            right_label="user",
        ):
            overlay_outputs["normalized_overlay"] = str(normalized_overlay_path)

        phase_dtw_overlay_path = experiment_dir / "phase_dtw_overlay.mp4"
        if render_dtw_overlay_video(
            left_table=pro_result.motion_table,
            right_table=user_result.motion_table,
            aligned_pairs=alignment.get("aligned_pairs", []),
            output_path=phase_dtw_overlay_path,
            left_label="pro",
            right_label="user",
        ):
            overlay_outputs["phase_dtw_overlay"] = str(phase_dtw_overlay_path)

    summary = {
        "experiment_id": experiment_dir.name,
        "experiment_type": "phase_aware_similarity_preparation",
        "purpose": "Prepare normalized 2D pose features and phase-wise DTW alignment before final similarity scoring.",
        "inputs": {"pro_video": str(pro_video), "user_video": str(user_video)},
        "outputs": {
            "experiment_dir": str(experiment_dir),
            "pro": str(pro_result.output_dir),
            "user": str(user_result.output_dir),
            "alignment": str(alignment_path),
            **overlay_outputs,
        },
        "pose_model": "MediaPipe Pose",
        "normalization": "height optional, pelvis-centered body-frame, body-scale units, handedness mirroring",
        "phase_method": "heuristic setup/leg_lift/stride/release/follow_through detection",
        "alignment_status": alignment.get("status"),
        "aligned_pair_count": alignment.get("aligned_pair_count"),
        "phase_alignments": alignment.get("phase_alignments"),
        "warnings": {"pro": pro_result.warnings, "user": user_result.warnings},
        "note": "No final similarity score is produced in this phase.",
    }
    write_json(experiment_dir / "summary.json", summary)
    return summary


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(make_json_safe(payload), ensure_ascii=False, indent=2), encoding="utf-8")


def make_json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): make_json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [make_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [make_json_safe(item) for item in value]
    if hasattr(value, "item"):
        return value.item()
    return value
