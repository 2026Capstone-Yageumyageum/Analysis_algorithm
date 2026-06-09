from __future__ import annotations

from io import StringIO
import math
from pathlib import Path
from typing import Any, Final

import numpy as np
import pandas as pd

from analysis.ball_release import estimate_ball_release_event
from analysis.cocking import detect_cocking_events
from analysis.normalization import build_body_frame_pose
from analysis.phase import detect_pitch_phases


JOINTS = (
    "nose",
    "left_shoulder",
    "right_shoulder",
    "left_elbow",
    "right_elbow",
    "left_wrist",
    "right_wrist",
    "left_hip",
    "right_hip",
    "left_knee",
    "right_knee",
    "left_ankle",
    "right_ankle",
    "left_foot_index",
    "right_foot_index",
)
SKELETON_EDGES = (
    ("left_shoulder", "right_shoulder"),
    ("left_hip", "right_hip"),
    ("left_shoulder", "left_elbow"),
    ("left_elbow", "left_wrist"),
    ("right_shoulder", "right_elbow"),
    ("right_elbow", "right_wrist"),
    ("left_shoulder", "left_hip"),
    ("right_shoulder", "right_hip"),
    ("left_hip", "left_knee"),
    ("left_knee", "left_ankle"),
    ("left_ankle", "left_foot_index"),
    ("right_hip", "right_knee"),
    ("right_knee", "right_ankle"),
    ("right_ankle", "right_foot_index"),
)
PHASE_LABELS = {
    "windup": "와인드업",
    "leg_lift": "레그 리프트",
    "stride": "스트라이드",
    "acceleration": "가속",
    "follow_through": "팔로스루",
}
PHASE_STEP_COUNTS = {
    "windup": 20,
    "leg_lift": 50,
    "stride": 45,
    "acceleration": 40,
    "follow_through": 35,
}
MIN_CONFIDENCE = 0.05
POSE_DISTANCE_SIGMA: Final = 0.25
FRAME_MARKER_GOOD_THRESHOLD = 78.0
FRAME_MARKER_BAD_THRESHOLD = 68.0
FRAME_MARKER_LIMIT = 3
SCENE_CUT_SCORE_THRESHOLD = 0.35
SCENE_CUT_CONFIRMATION_WINDOW = 5
MIN_CLIP_ROWS = 45


def build_resampling_preview(
    pro_keypoints_path: Path,
    user_keypoints_path: Path,
    *,
    release_events: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    pro_keypoints = _read_keypoints(pro_keypoints_path)
    user_keypoints = _read_keypoints(user_keypoints_path)
    return build_resampling_preview_from_keypoints(
        pro_keypoints=pro_keypoints,
        user_keypoints=user_keypoints,
        sources={
            "proKeypoints": str(pro_keypoints_path),
            "userKeypoints": str(user_keypoints_path),
        },
        release_events=release_events,
    )


def build_resampling_preview_from_csv_text(
    *,
    pro_csv_text: str,
    user_csv_text: str,
    sources: dict[str, Any] | None = None,
    release_events: dict[str, dict[str, Any]] | None = None,
    video_paths: dict[str, Path] | None = None,
) -> dict[str, Any]:
    return build_resampling_preview_from_keypoints(
        pro_keypoints=pd.read_csv(StringIO(pro_csv_text)),
        user_keypoints=pd.read_csv(StringIO(user_csv_text)),
        sources=sources,
        release_events=release_events,
        video_paths=video_paths,
    )


def build_resampling_preview_from_keypoints(
    *,
    pro_keypoints: pd.DataFrame,
    user_keypoints: pd.DataFrame,
    sources: dict[str, Any] | None = None,
    release_events: dict[str, dict[str, Any]] | None = None,
    video_paths: dict[str, Path] | None = None,
) -> dict[str, Any]:
    source_info = sources or {}
    release_event_info = release_events or {}
    video_path_info = video_paths or {}
    pro_keypoints, pro_clip_meta, pro_clip_warnings = _maybe_first_continuous_pitch_clip(
        pro_keypoints,
        enabled=_should_use_first_clip(source_info, "pro"),
    )
    user_keypoints, user_clip_meta, user_clip_warnings = _maybe_first_continuous_pitch_clip(
        user_keypoints,
        enabled=_should_use_first_clip(source_info, "user"),
    )
    pro_pose = build_body_frame_pose(pro_keypoints)
    user_pose = build_body_frame_pose(user_keypoints)
    preliminary_pro_phases = detect_pitch_phases(pro_pose.table)
    preliminary_user_phases = detect_pitch_phases(user_pose.table)
    pro_release_event = release_event_info.get("pro") or _estimate_ball_release_event(
        video_path=video_path_info.get("pro"),
        keypoints=pro_keypoints,
        pose_table=pro_pose.table,
        preliminary_phases=preliminary_pro_phases,
    )
    user_release_event = release_event_info.get("user") or _estimate_ball_release_event(
        video_path=video_path_info.get("user"),
        keypoints=user_keypoints,
        pose_table=user_pose.table,
        preliminary_phases=preliminary_user_phases,
    )
    pro_phases = detect_pitch_phases(pro_pose.table, release_event_override=pro_release_event)
    user_phases = detect_pitch_phases(user_pose.table, release_event_override=user_release_event)
    pro_cocking = detect_cocking_events(pro_pose.table, pro_phases.intervals)
    user_cocking = detect_cocking_events(user_pose.table, user_phases.intervals)
    release_events = {
        "pro": pro_phases.events.get("release"),
        "user": user_phases.events.get("release"),
    }

    phases = build_resampled_phase_previews(
        pro_table=pro_pose.table,
        user_table=user_pose.table,
        pro_intervals=pro_phases.intervals,
        user_intervals=user_phases.intervals,
    )
    frame_markers = _build_frame_markers(phases=phases, release_events=release_events)

    return {
        "status": "ready",
        "method": "fixed_step_pose_resampling_preview",
        "speedUsed": False,
        "coordinateSystem": "pelvis-centered torso-axis body-scale units",
        "phaseStepCounts": PHASE_STEP_COUNTS,
        "skeletonEdges": SKELETON_EDGES,
        "sources": sources or {},
        "releaseDefinition": {
            "default": "middle_of_before_exit_and_exit_frame",
            "currentFallback": "throwing_wrist_pose_proxy_midpoint_when_ball_not_detected",
            "plannedSubFrameCorrection": "wrist_ball_distance_threshold_crossing",
        },
        "releaseEvents": release_events,
        "frameMarkers": frame_markers,
        "cockingEvents": {
            "pro": pro_cocking,
            "user": user_cocking,
        },
        "phaseDetection": {
            "pro": {
                "representativeFrames": pro_phases.representative_frames,
                "intervals": pro_phases.intervals,
            },
            "user": {
                "representativeFrames": user_phases.representative_frames,
                "intervals": user_phases.intervals,
            },
        },
        "clipMeta": {
            "pro": pro_clip_meta,
            "user": user_clip_meta,
        },
        "warnings": {
            "pro": pro_clip_warnings + pro_pose.warnings + pro_phases.warnings,
            "user": user_clip_warnings + user_pose.warnings + user_phases.warnings,
        },
        "phases": phases,
    }


def build_resampled_phase_previews(
    *,
    pro_table: pd.DataFrame,
    user_table: pd.DataFrame,
    pro_intervals: dict[str, dict[str, Any]],
    user_intervals: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    phases = []
    for phase, step_count in PHASE_STEP_COUNTS.items():
        pro_interval = pro_intervals.get(phase)
        user_interval = user_intervals.get(phase)
        if pro_interval is None or user_interval is None:
            continue
        phases.append(
            _build_phase_preview(
                phase=phase,
                step_count=step_count,
                pro_table=pro_table,
                user_table=user_table,
                pro_interval=pro_interval,
                user_interval=user_interval,
            )
        )
    return phases


def _build_frame_markers(
    *,
    phases: list[dict[str, Any]],
    release_events: dict[str, dict[str, Any] | None],
) -> dict[str, list[dict[str, Any]]]:
    scored_samples = []
    for phase in phases:
        for sample in phase.get("samples", []):
            score = _safe_float(sample.get("score"), fallback=None)
            if score is None:
                continue
            scored_samples.append(
                {
                    "phase": phase.get("phase"),
                    "label": phase.get("label", phase.get("phase")),
                    "stepIndex": sample.get("stepIndex"),
                    "proFrame": _frame_value(sample.get("proFrame")),
                    "userFrame": _frame_value(sample.get("userFrame")),
                    "score": round(score, 2),
                }
            )

    good = [
        _marker_payload(item, "good")
        for item in sorted(scored_samples, key=lambda sample: sample["score"], reverse=True)
        if item["score"] >= FRAME_MARKER_GOOD_THRESHOLD
    ][:FRAME_MARKER_LIMIT]
    bad = [
        _marker_payload(item, "bad")
        for item in sorted(scored_samples, key=lambda sample: sample["score"])
        if item["score"] <= FRAME_MARKER_BAD_THRESHOLD
    ][:FRAME_MARKER_LIMIT]

    if not good and scored_samples:
        good = [_marker_payload(item, "good") for item in sorted(scored_samples, key=lambda sample: sample["score"], reverse=True)[:1]]
    if not bad and scored_samples:
        bad = [_marker_payload(item, "bad") for item in sorted(scored_samples, key=lambda sample: sample["score"])[:1]]

    return {
        "good": good,
        "bad": bad,
        "release": [_release_marker_payload(release_events)],
    }


def _marker_payload(sample: dict[str, Any], kind: str) -> dict[str, Any]:
    label = str(sample.get("label") or sample.get("phase") or "해당 구간")
    score = sample.get("score")
    if kind == "good":
        message = f"{label}에서 자세 유사도가 높은 보강 프레임입니다."
    else:
        message = f"{label}에서 자세 차이가 큰 보강 프레임입니다."
    return {
        "kind": kind,
        "phase": sample.get("phase"),
        "label": label,
        "stepIndex": sample.get("stepIndex"),
        "proFrame": sample.get("proFrame"),
        "userFrame": sample.get("userFrame"),
        "score": score,
        "message": message,
    }


def _release_marker_payload(release_events: dict[str, dict[str, Any] | None]) -> dict[str, Any]:
    pro = release_events.get("pro") or {}
    user = release_events.get("user") or {}
    return {
        "kind": "release",
        "label": "릴리즈 포인트",
        "proFrame": _frame_value(pro.get("frame")),
        "userFrame": _frame_value(user.get("frame")),
        "message": "공이 손에서 나가기 전 프레임과 나간 프레임의 midpoint입니다.",
    }


def _read_keypoints(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"keypoints CSV가 없습니다: {path}")
    return pd.read_csv(path)


def _estimate_ball_release_event(
    *,
    video_path: Path | None,
    keypoints: pd.DataFrame,
    pose_table: pd.DataFrame,
    preliminary_phases: Any,
) -> dict[str, Any] | None:
    if video_path is None:
        return None
    return estimate_ball_release_event(
        video_path=video_path,
        keypoints=keypoints,
        normalized_pose=pose_table,
        intervals=preliminary_phases.intervals,
        fallback_release_event=preliminary_phases.events.get("release"),
    )


def _maybe_first_continuous_pitch_clip(
    keypoints: pd.DataFrame,
    *,
    enabled: bool,
) -> tuple[pd.DataFrame, dict[str, Any], list[str]]:
    if not enabled:
        return keypoints, _clip_meta(keypoints, original_rows=len(keypoints), trimmed=False), []
    return _first_continuous_pitch_clip(keypoints)


def _should_use_first_clip(sources: dict[str, Any], side: str) -> bool:
    video_name = str(sources.get(f"{side}Video") or "")
    return "김광현" in video_name and "양현종" in video_name


def _first_continuous_pitch_clip(keypoints: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any], list[str]]:
    if keypoints.empty or "frame_index" not in keypoints.columns:
        return keypoints, {"trimmed": False}, []

    keypoints = keypoints.sort_values("frame_index").reset_index(drop=True)
    total_rows = len(keypoints)
    cut_row = _detect_scene_cut_row(keypoints)
    if cut_row is None or cut_row < MIN_CLIP_ROWS:
        return keypoints, _clip_meta(keypoints, original_rows=total_rows, trimmed=False), []

    clip = keypoints.iloc[:cut_row].copy().reset_index(drop=True)
    if len(clip) < MIN_CLIP_ROWS:
        return keypoints, _clip_meta(keypoints, original_rows=total_rows, trimmed=False), []

    cut_frame = int(keypoints.iloc[cut_row]["frame_index"])
    warning = f"큰 장면 전환을 감지해 첫 번째 연속 투구 구간만 사용했습니다. cutFrame={cut_frame}"
    return clip, _clip_meta(clip, original_rows=total_rows, trimmed=True, cut_frame=cut_frame), [warning]


def _detect_scene_cut_row(keypoints: pd.DataFrame) -> int | None:
    jump_score = _scene_jump_score(keypoints)
    if jump_score.empty:
        return None

    candidates = jump_score[jump_score >= SCENE_CUT_SCORE_THRESHOLD].index.to_list()
    for row_index in candidates:
        if row_index < MIN_CLIP_ROWS or len(keypoints) - row_index < MIN_CLIP_ROWS:
            continue
        window_end = min(len(jump_score), row_index + SCENE_CUT_CONFIRMATION_WINDOW)
        confirmed_count = int((jump_score.iloc[row_index:window_end] >= SCENE_CUT_SCORE_THRESHOLD).sum())
        if confirmed_count >= 2:
            return int(row_index)
    return None


def _scene_jump_score(keypoints: pd.DataFrame) -> pd.Series:
    required_columns = [
        "left_hip_x_smooth",
        "left_hip_y_smooth",
        "right_hip_x_smooth",
        "right_hip_y_smooth",
        "left_shoulder_x_smooth",
        "left_shoulder_y_smooth",
        "right_shoulder_x_smooth",
        "right_shoulder_y_smooth",
    ]
    if any(column not in keypoints.columns for column in required_columns):
        return pd.Series(dtype=float)

    pelvis_x = (_numeric_frame_series(keypoints["left_hip_x_smooth"]) + _numeric_frame_series(keypoints["right_hip_x_smooth"])) / 2.0
    pelvis_y = (_numeric_frame_series(keypoints["left_hip_y_smooth"]) + _numeric_frame_series(keypoints["right_hip_y_smooth"])) / 2.0
    shoulder_x = (_numeric_frame_series(keypoints["left_shoulder_x_smooth"]) + _numeric_frame_series(keypoints["right_shoulder_x_smooth"])) / 2.0
    shoulder_y = (_numeric_frame_series(keypoints["left_shoulder_y_smooth"]) + _numeric_frame_series(keypoints["right_shoulder_y_smooth"])) / 2.0
    body_scale = pd.Series(
        np.sqrt(((shoulder_x - pelvis_x) ** 2) + ((shoulder_y - pelvis_y) ** 2)),
        index=keypoints.index,
    ).replace(0, np.nan)
    fallback_scale = float(body_scale.replace([np.inf, -np.inf], np.nan).dropna().median() or 1.0)
    body_scale = body_scale.interpolate(limit_direction="both").fillna(fallback_scale).clip(lower=fallback_scale * 0.35)

    joint_displacements = []
    for joint in JOINTS:
        x_column = f"{joint}_x_smooth"
        y_column = f"{joint}_y_smooth"
        confidence_column = f"{joint}_confidence"
        if x_column not in keypoints.columns or y_column not in keypoints.columns:
            continue
        x_values = _numeric_frame_series(keypoints[x_column])
        y_values = _numeric_frame_series(keypoints[y_column])
        displacement = pd.Series(
            np.sqrt((x_values.diff() ** 2) + (y_values.diff() ** 2)) / body_scale,
            index=keypoints.index,
        )
        if confidence_column in keypoints.columns:
            confidence = _numeric_frame_series(keypoints[confidence_column], fallback=0.0)
            displacement = displacement.where(confidence >= 0.2)
        joint_displacements.append(displacement)

    if not joint_displacements:
        return pd.Series(dtype=float)
    median_displacement = pd.concat(joint_displacements, axis=1).median(axis=1).fillna(0.0)
    scale_change = body_scale.pct_change().abs().replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return median_displacement + scale_change


def _numeric_frame_series(values: Any, fallback: float | None = None) -> pd.Series:
    series = pd.to_numeric(values, errors="coerce").interpolate(limit_direction="both")
    if fallback is not None:
        return series.fillna(fallback)
    return series


def _clip_meta(keypoints: pd.DataFrame, *, original_rows: int, trimmed: bool, cut_frame: int | None = None) -> dict[str, Any]:
    if keypoints.empty:
        return {"trimmed": trimmed, "originalRows": original_rows, "usedRows": 0, "cutFrame": cut_frame}
    return {
        "trimmed": trimmed,
        "originalRows": original_rows,
        "usedRows": len(keypoints),
        "startFrame": int(keypoints["frame_index"].iloc[0]),
        "endFrame": int(keypoints["frame_index"].iloc[-1]),
        "cutFrame": cut_frame,
    }


def _build_phase_preview(
    *,
    phase: str,
    step_count: int,
    pro_table: pd.DataFrame,
    user_table: pd.DataFrame,
    pro_interval: dict[str, Any],
    user_interval: dict[str, Any],
) -> dict[str, Any]:
    pro_samples = _resample_table(pro_table, pro_interval, step_count)
    user_samples = _resample_table(user_table, user_interval, step_count)
    samples = []
    for step_index, (pro_sample, user_sample) in enumerate(zip(pro_samples, user_samples)):
        score = _pose_score(pro_sample["points"], user_sample["points"])
        samples.append(
            {
                "stepIndex": step_index,
                "progress": round(step_index / max(1, step_count - 1), 6),
                "proFrame": pro_sample["targetFrame"],
                "userFrame": user_sample["targetFrame"],
                "score": score,
                "proPoints": pro_sample["points"],
                "userPoints": user_sample["points"],
                "proDisplayPoints": pro_sample["displayPoints"],
                "userDisplayPoints": user_sample["displayPoints"],
            }
        )

    return {
        "phase": phase,
        "label": PHASE_LABELS.get(phase, phase),
        "stepCount": step_count,
        "proStartFrame": _frame_value(pro_interval["startFrame"]),
        "proEndFrame": _frame_value(pro_interval["endFrame"]),
        "userStartFrame": _frame_value(user_interval["startFrame"]),
        "userEndFrame": _frame_value(user_interval["endFrame"]),
        "proFrameCount": _covered_frame_count(pro_interval["startFrame"], pro_interval["endFrame"]),
        "userFrameCount": _covered_frame_count(user_interval["startFrame"], user_interval["endFrame"]),
        "samples": samples,
    }


def _resample_table(table: pd.DataFrame, interval: dict[str, Any], step_count: int) -> list[dict[str, Any]]:
    start_frame = float(interval["startFrame"])
    end_frame = float(interval["endFrame"])
    frame_floor = math.floor(min(start_frame, end_frame))
    frame_ceil = math.ceil(max(start_frame, end_frame))
    table_frames = table["frame_index"].astype(float)
    segment = table[
        (table_frames >= frame_floor) & (table_frames <= frame_ceil)
    ].sort_values("frame_index")
    if segment.empty:
        return []

    frame_values = segment["frame_index"].astype(float).to_numpy()
    target_frames = np.linspace(float(start_frame), float(end_frame), step_count)
    joint_series = {joint: _joint_series(segment, joint) for joint in JOINTS}
    display_series = {joint: _joint_display_series(segment, joint) for joint in JOINTS}
    samples = []
    for target_frame in target_frames:
        points = {}
        display_points = {}
        for joint, (x_values, y_values, confidence_values) in joint_series.items():
            points[joint] = {
                "x": _round_or_none(_interpolate(frame_values, x_values, target_frame)),
                "y": _round_or_none(_interpolate(frame_values, y_values, target_frame)),
                "confidence": _round_or_none(_interpolate(frame_values, confidence_values, target_frame, fallback=0.0)),
            }
        for joint, (x_values, y_values, confidence_values) in display_series.items():
            display_points[joint] = {
                "x": _round_or_none(_interpolate(frame_values, x_values, target_frame)),
                "y": _round_or_none(_interpolate(frame_values, y_values, target_frame)),
                "confidence": _round_or_none(_interpolate(frame_values, confidence_values, target_frame, fallback=0.0)),
            }
        samples.append({"targetFrame": round(float(target_frame), 4), "points": points, "displayPoints": display_points})
    return samples


def _joint_series(segment: pd.DataFrame, joint: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    return (
        _numeric_series(segment.get(f"{joint}_body_x")),
        _numeric_series(segment.get(f"{joint}_body_y")),
        _numeric_series(segment.get(f"{joint}_confidence"), fallback=0.0),
    )


def _joint_display_series(segment: pd.DataFrame, joint: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    image_x_column = f"{joint}_image_x"
    image_y_column = f"{joint}_image_y"
    if (
        image_x_column not in segment.columns
        or image_y_column not in segment.columns
        or "pelvis_center_x" not in segment.columns
        or "pelvis_center_y" not in segment.columns
        or "body_scale" not in segment.columns
    ):
        return _joint_series(segment, joint)

    body_scale = _numeric_series(segment["body_scale"], fallback=1.0)
    body_scale = np.where(np.isfinite(body_scale) & (np.abs(body_scale) > 1e-9), body_scale, 1.0)
    x_values = (_numeric_series(segment[image_x_column]) - _numeric_series(segment["pelvis_center_x"])) / body_scale
    y_values = -(_numeric_series(segment[image_y_column]) - _numeric_series(segment["pelvis_center_y"])) / body_scale
    if "throwing_side" in segment.columns and str(segment["throwing_side"].iloc[0]) == "left":
        x_values = x_values * -1.0
    return (
        x_values,
        y_values,
        _numeric_series(segment.get(f"{joint}_confidence"), fallback=0.0),
    )


def _numeric_series(values: Any, fallback: float | None = None) -> np.ndarray:
    if values is None:
        return np.array([], dtype=float)
    series = pd.to_numeric(values, errors="coerce").interpolate(limit_direction="both")
    if fallback is not None:
        series = series.fillna(fallback)
    return series.to_numpy(dtype=float)


def _interpolate(frames: np.ndarray, values: np.ndarray, target_frame: float, fallback: float | None = None) -> float | None:
    if len(frames) == 0 or len(values) == 0:
        return fallback
    valid = np.isfinite(frames) & np.isfinite(values)
    if not valid.any():
        return fallback
    return float(np.interp(float(target_frame), frames[valid], values[valid]))


def _pose_score(pro_points: dict[str, dict[str, float | None]], user_points: dict[str, dict[str, float | None]]) -> float | None:
    weighted_total = 0.0
    weight_total = 0.0
    for joint in JOINTS:
        pro = pro_points[joint]
        user = user_points[joint]
        pro_confidence = _safe_float(pro.get("confidence"), fallback=0.0)
        user_confidence = _safe_float(user.get("confidence"), fallback=0.0)
        if min(pro_confidence, user_confidence) < MIN_CONFIDENCE:
            continue
        pro_x = _safe_float(pro.get("x"))
        pro_y = _safe_float(pro.get("y"))
        user_x = _safe_float(user.get("x"))
        user_y = _safe_float(user.get("y"))
        if None in (pro_x, pro_y, user_x, user_y):
            continue

        distance = math.dist((pro_x, pro_y), (user_x, user_y))
        score = 100.0 * math.exp(-0.5 * ((distance / POSE_DISTANCE_SIGMA) ** 2))
        weight = math.sqrt(max(0.0, pro_confidence) * max(0.0, user_confidence))
        weighted_total += score * weight
        weight_total += weight
    if weight_total <= 0:
        return None
    return round(weighted_total / weight_total, 2)


def _safe_float(value: Any, fallback: float | None = None) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if math.isfinite(parsed) else fallback


def _round_or_none(value: float | None) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    return round(float(value), 6)


def _covered_frame_count(start_frame: Any, end_frame: Any) -> int:
    start = float(start_frame)
    end = float(end_frame)
    if not math.isfinite(start) or not math.isfinite(end):
        return 0
    return max(1, int(math.ceil(max(start, end)) - math.floor(min(start, end)) + 1))


def _frame_value(value: Any) -> int | float | None:
    parsed = _safe_float(value, fallback=None)
    if parsed is None:
        return None
    if math.isclose(parsed, round(parsed)):
        return int(round(parsed))
    return round(parsed, 4)
