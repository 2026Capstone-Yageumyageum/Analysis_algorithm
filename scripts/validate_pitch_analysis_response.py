from __future__ import annotations

import argparse
import csv
import json
import math
from io import StringIO
from pathlib import Path
from typing import Any


EXPECTED_SCHEMA_VERSION = "pitch_analysis_response_v1"
EXPECTED_ALGORITHM = "body_frame_phase_direction_vector_v1"
EXPECTED_PHASES = {"leg_lift", "stride", "release", "follow_through"}
EXPECTED_REPRESENTATIVES = {"setup", "leg_lift", "stride", "release", "follow_through"}
TOP_LEVEL_REQUIRED_FIELDS = {
    "videoId",
    "status",
    "responseSchemaVersion",
    "analysisType",
    "pitchType",
    "cameraView",
    "processedAt",
    "algorithmName",
    "scoreScale",
    "user_data",
    "players",
}
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
IMPUTED_JOINTS = (
    "left_elbow",
    "right_elbow",
    "left_wrist",
    "right_wrist",
    "left_knee",
    "right_knee",
    "left_ankle",
    "right_ankle",
    "left_foot_index",
    "right_foot_index",
)
QUALITY_COLUMNS = {
    "pitcher_com_x_smooth",
    "pitcher_com_y_smooth",
    "pitcher_detected",
    "normalised_frame",
    "no_missing_frames_flag",
    "smooth_com_flag",
}
REQUIRED_KEYPOINT_COLUMNS = set(
    ["frame_index", "time_sec"]
    + [column for joint in JOINTS for column in (f"{joint}_x", f"{joint}_y", f"{joint}_confidence")]
    + [f"{joint}_imputed_flag" for joint in IMPUTED_JOINTS]
    + [column for joint in JOINTS for column in (f"{joint}_x_smooth", f"{joint}_y_smooth")]
) | QUALITY_COLUMNS


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a pitch analysis API response JSON file.")
    parser.add_argument("response_json", type=Path)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail when any phase score is not ready. Default only reports it as a warning.",
    )
    return parser.parse_args()


def validate_response(payload: dict[str, Any], *, strict: bool = False) -> dict[str, list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    _validate_required_top_level(payload, errors)
    _expect(payload.get("status") == "completed", "status가 completed가 아닙니다.", errors)
    _expect(
        payload.get("responseSchemaVersion") == EXPECTED_SCHEMA_VERSION,
        f"responseSchemaVersion이 {EXPECTED_SCHEMA_VERSION}가 아닙니다.",
        errors,
    )
    _expect(payload.get("cameraView") == "rear", "cameraView가 rear가 아닙니다.", errors)
    _expect(payload.get("algorithmName") == EXPECTED_ALGORITHM, "algorithmName이 예상 값과 다릅니다.", errors)
    _expect(payload.get("scoreScale") == "0~100", "scoreScale이 0~100이 아닙니다.", errors)
    _expect(isinstance(payload.get("videoId"), str) and bool(payload.get("videoId")), "videoId가 비어 있습니다.", errors)
    _validate_user_data(payload.get("user_data"), errors)
    _validate_players(payload.get("players"), errors, warnings, strict=strict)

    return {"errors": errors, "warnings": warnings}


def _validate_required_top_level(payload: dict[str, Any], errors: list[str]) -> None:
    missing = TOP_LEVEL_REQUIRED_FIELDS.difference(payload)
    _expect(not missing, f"최상위 응답 필드 누락: {sorted(missing)}", errors)


def _validate_overall_score(value: Any, errors: list[str]) -> None:
    if not _is_finite_number(value):
        errors.append("overallScore가 숫자가 아닙니다.")
        return
    _expect(0 <= float(value) <= 100, "overallScore가 0~100 범위를 벗어났습니다.", errors)


def _validate_user_data(value: Any, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append("user_data가 object가 아닙니다.")
        return
    _expect(isinstance(value.get("skeleton_data_id"), str), "user_data.skeleton_data_id가 문자열이 아닙니다.", errors)
    _expect(isinstance(value.get("frame_count"), int), "user_data.frame_count가 정수가 아닙니다.", errors)
    _expect(_is_finite_number(value.get("fps")), "user_data.fps가 유한한 숫자가 아닙니다.", errors)
    _expect(isinstance(value.get("resolution"), str), "user_data.resolution이 문자열이 아닙니다.", errors)
    _validate_keypoints_csv(value.get("skeleton_data"), "user_data.skeleton_data", errors)
    _validate_keypoints_csv(value.get("keypointsCsvText"), "user_data.keypointsCsvText", errors)
    _expect(
        value.get("skeleton_data") == value.get("keypointsCsvText"),
        "user_data.skeleton_data와 user_data.keypointsCsvText가 다릅니다.",
        errors,
    )


def _validate_players(value: Any, errors: list[str], warnings: list[str], *, strict: bool) -> None:
    if not isinstance(value, list):
        errors.append("players가 array가 아닙니다.")
        return
    _expect(0 < len(value) <= 3, "players는 1~3개여야 합니다.", errors)
    previous_score: float | None = None
    for index, player in enumerate(value):
        if not isinstance(player, dict):
            errors.append(f"players[{index}]가 object가 아닙니다.")
            continue
        _expect(player.get("rank") == index + 1, f"players[{index}].rank가 순서와 맞지 않습니다.", errors)
        _expect(isinstance(player.get("analysisId"), str), f"players[{index}].analysisId가 문자열이 아닙니다.", errors)
        _expect(isinstance(player.get("proId"), str), f"players[{index}].proId가 문자열이 아닙니다.", errors)
        _validate_overall_score(player.get("overallScore"), errors)
        current_score = float(player["overallScore"]) if _is_finite_number(player.get("overallScore")) else None
        if previous_score is not None and current_score is not None:
            _expect(previous_score >= current_score, "players가 overallScore 내림차순으로 정렬되지 않았습니다.", errors)
        if current_score is not None:
            previous_score = current_score
        _validate_phase_scores(player.get("phaseScores"), errors, warnings, strict=strict, path=f"players[{index}].phaseScores")
        if "phaseDetection" in player:
            _validate_phase_detection(player.get("phaseDetection"), errors)
        if "normalization" in player:
            _validate_normalization(player.get("normalization"), errors)


def _validate_pose_meta(value: Any, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append("poseMeta가 object가 아닙니다.")
        return
    for target in ("user", "pro"):
        meta = value.get(target)
        if not isinstance(meta, dict):
            errors.append(f"poseMeta.{target}가 없습니다.")
            continue
        _expect(meta.get("status") == "ready", f"poseMeta.{target}.status가 ready가 아닙니다.", errors)
        _expect(
            meta.get("poseModel") == "MediaPipe Pose",
            f"poseMeta.{target}.poseModel이 MediaPipe Pose가 아닙니다.",
            errors,
        )


def _validate_phase_detection(value: Any, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append("phaseDetection이 object가 아닙니다.")
        return
    for target in ("user", "pro"):
        frames = ((value.get(target) or {}).get("representativeFrames") or {})
        if not isinstance(frames, dict):
            errors.append(f"phaseDetection.{target}.representativeFrames가 object가 아닙니다.")
            continue
        missing = EXPECTED_REPRESENTATIVES.difference(frames)
        _expect(not missing, f"phaseDetection.{target}에 대표 프레임 누락: {sorted(missing)}", errors)
        for phase_name in EXPECTED_REPRESENTATIVES.intersection(frames):
            _expect(
                isinstance(frames.get(phase_name), int),
                f"phaseDetection.{target}.representativeFrames.{phase_name}가 정수 프레임이 아닙니다.",
                errors,
            )


def _validate_normalization(value: Any, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append("normalization이 object가 아닙니다.")
        return
    for target in ("user", "pro"):
        meta = value.get(target)
        if not isinstance(meta, dict):
            errors.append(f"normalization.{target}가 없습니다.")
            continue
        _expect(
            meta.get("method") == "pelvis_torso_body_scale_2d_v1",
            f"normalization.{target}.method가 예상 값과 다릅니다.",
            errors,
        )
        _expect(
            meta.get("throwingSide") in {"left", "right"},
            f"normalization.{target}.throwingSide가 left/right가 아닙니다.",
            errors,
        )


def _validate_phase_scores(
    value: Any,
    errors: list[str],
    warnings: list[str],
    *,
    strict: bool,
    path: str = "phaseScores",
) -> None:
    if not isinstance(value, list):
        errors.append(f"{path}가 array가 아닙니다.")
        return
    phases = {item.get("phase") for item in value if isinstance(item, dict)}
    missing = EXPECTED_PHASES.difference(phases)
    _expect(not missing, f"{path}에 phase 누락: {sorted(missing)}", errors)
    for item in value:
        if not isinstance(item, dict):
            errors.append(f"{path} 안에 object가 아닌 항목이 있습니다.")
            continue
        status = item.get("status")
        if status is not None and status != "ready":
            message = f"{item.get('phase')} phase status가 ready가 아닙니다: {status}"
            (errors if strict else warnings).append(message)
        score = item.get("score")
        if score is not None:
            _expect(
                _is_finite_number(score) and 0 <= float(score) <= 100,
                f"{item.get('phase')} score가 0~100 숫자가 아닙니다.",
                errors,
            )
        for field_name in ("userStartFrame", "userEndFrame", "proStartFrame", "proEndFrame"):
            _expect(isinstance(item.get(field_name), int), f"{item.get('phase')} {field_name}가 정수가 아닙니다.", errors)
        joint_scores = item.get("jointScores", [])
        _expect(isinstance(joint_scores, list), f"{item.get('phase')} jointScores가 array가 아닙니다.", errors)


def _validate_similarity(value: Any, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append("similarity가 object가 아닙니다.")
        return
    _expect(value.get("algorithmName") == EXPECTED_ALGORITHM, "similarity.algorithmName이 예상 값과 다릅니다.", errors)
    _expect(value.get("scoreScale") == "0~100", "similarity.scoreScale이 0~100이 아닙니다.", errors)
    _validate_overall_score(value.get("overallScore"), errors)
    _validate_phase_scores(value.get("phaseScores"), errors, [], strict=False)


def _validate_speed(value: Any, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append("speed가 object가 아닙니다.")
        return
    for target in ("user", "pro"):
        result = value.get(target)
        if not isinstance(result, dict):
            errors.append(f"speed.{target}가 없습니다.")
            continue
        status = result.get("status")
        _expect(isinstance(status, str) and bool(status), f"speed.{target}.status가 문자열이 아닙니다.", errors)
        if status == "ready":
            for field_name in (
                "speedKmh",
                "speedMps",
                "releaseFrame",
                "arrivalFrame",
                "frameDelta",
                "fps",
                "targetDistanceM",
                "releaseExtensionM",
                "effectiveDistanceM",
                "flightTimeSec",
            ):
                _expect(field_name in result, f"speed.{target}.{field_name}가 없습니다.", errors)
            for field_name in ("speedKmh", "speedMps", "fps", "targetDistanceM", "releaseExtensionM", "effectiveDistanceM", "flightTimeSec"):
                _expect(_is_finite_number(result.get(field_name)), f"speed.{target}.{field_name}가 유한한 숫자가 아닙니다.", errors)
            for field_name in ("releaseFrame", "arrivalFrame", "frameDelta"):
                _expect(isinstance(result.get(field_name), int), f"speed.{target}.{field_name}가 정수가 아닙니다.", errors)


def _validate_video_meta(value: Any, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append("videoMeta가 object가 아닙니다.")
        return
    for target in ("user", "pro"):
        meta = value.get(target)
        if not isinstance(meta, dict):
            errors.append(f"videoMeta.{target}가 없습니다.")
            continue
        _expect(isinstance(meta.get("videoId"), str), f"videoMeta.{target}.videoId가 문자열이 아닙니다.", errors)
        for field_name in ("frameCount", "width", "height"):
            _expect(isinstance(meta.get(field_name), int), f"videoMeta.{target}.{field_name}가 정수가 아닙니다.", errors)
        for field_name in ("fps", "durationSec"):
            _expect(_is_finite_number(meta.get(field_name)), f"videoMeta.{target}.{field_name}가 유한한 숫자가 아닙니다.", errors)


def _validate_keypoints_csv_text(value: Any, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append("keypointsCsvText가 object가 아닙니다.")
        return
    for target in ("user", "pro"):
        _validate_keypoints_csv(value.get(target), f"keypointsCsvText.{target}", errors)


def _validate_keypoints_csv(value: Any, path: str, errors: list[str]) -> None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{path}가 비어 있습니다.")
        return
    reader = csv.DictReader(StringIO(value))
    columns = set(reader.fieldnames or [])
    missing = REQUIRED_KEYPOINT_COLUMNS.difference(columns)
    _expect(not missing, f"{path} 필수 컬럼 누락: {sorted(missing)}", errors)
    first_row = next(reader, None)
    _expect(first_row is not None, f"{path}에 데이터 행이 없습니다.", errors)
    if first_row:
        _validate_first_keypoint_row(first_row, path, errors)


def _validate_first_keypoint_row(row: dict[str, str], target: str, errors: list[str]) -> None:
    for column in ("frame_index", "normalised_frame"):
        try:
            int(row.get(column, ""))
        except ValueError:
            errors.append(f"{target}.{column} 첫 행이 정수가 아닙니다.")
    numeric_columns = [column for column in row if column.endswith(("_x", "_y", "_confidence", "_smooth"))]
    numeric_columns.extend(["time_sec", "pitcher_com_x_smooth", "pitcher_com_y_smooth"])
    for column in numeric_columns:
        value = row.get(column)
        if value in (None, ""):
            errors.append(f"{target}.{column} 첫 행 값이 비어 있습니다.")
            continue
        try:
            parsed = float(value)
        except ValueError:
            errors.append(f"{target}.{column} 첫 행이 숫자가 아닙니다.")
            continue
        if not math.isfinite(parsed):
            errors.append(f"{target}.{column} 첫 행이 유한한 숫자가 아닙니다.")


def _expect(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def _is_finite_number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(float(value))


def main() -> int:
    args = parse_args()
    payload = json.loads(args.response_json.read_text(encoding="utf-8"))
    result = validate_response(payload, strict=args.strict)
    for warning in result["warnings"]:
        print(f"[WARN] {warning}")
    if result["errors"]:
        for error in result["errors"]:
            print(f"[FAIL] {error}")
        return 1
    print("[PASS] pitch analysis response contract looks valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
