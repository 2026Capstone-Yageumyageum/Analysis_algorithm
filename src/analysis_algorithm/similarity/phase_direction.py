from __future__ import annotations

from dataclasses import dataclass
import csv
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


PHASE_LABELS = {
    "setup": "준비 자세",
    "leg_lift": "다리 들기",
    "stride": "보폭 이동 / 팔 준비",
    "release": "릴리즈",
    "follow_through": "팔로스루",
}

PHASE_POINT_SPECS: dict[str, list[dict[str, str]]] = {
    "setup": [
        {"key": "pelvis_center", "label": "골반 중심", "kind": "pelvis_center"},
        {"key": "shoulder_center", "label": "어깨 중심", "kind": "shoulder_center"},
    ],
    "leg_lift": [
        {"key": "lead_knee", "label": "리드 무릎", "kind": "stride_joint", "joint": "knee"},
        {"key": "lead_ankle", "label": "리드 발목", "kind": "stride_joint", "joint": "ankle"},
        {"key": "pelvis_center", "label": "골반 중심", "kind": "pelvis_center"},
        {"key": "throwing_wrist", "label": "투구 손목", "kind": "throwing_joint", "joint": "wrist"},
        {"key": "throwing_elbow", "label": "투구 팔꿈치", "kind": "throwing_joint", "joint": "elbow"},
    ],
    "stride": [
        {"key": "stride_foot", "label": "보폭 발", "kind": "stride_joint", "joint": "foot_index"},
        {"key": "stride_knee", "label": "보폭 무릎", "kind": "stride_joint", "joint": "knee"},
        {"key": "pelvis_center", "label": "골반 중심", "kind": "pelvis_center"},
        {"key": "throwing_wrist", "label": "투구 손목", "kind": "throwing_joint", "joint": "wrist"},
        {"key": "throwing_elbow", "label": "투구 팔꿈치", "kind": "throwing_joint", "joint": "elbow"},
        {"key": "throwing_shoulder", "label": "투구 어깨", "kind": "throwing_joint", "joint": "shoulder"},
    ],
    "release": [
        {"key": "throwing_wrist", "label": "투구 손목", "kind": "throwing_joint", "joint": "wrist"},
        {"key": "throwing_elbow", "label": "투구 팔꿈치", "kind": "throwing_joint", "joint": "elbow"},
        {"key": "throwing_shoulder", "label": "투구 어깨", "kind": "throwing_joint", "joint": "shoulder"},
        {"key": "shoulder_center", "label": "어깨 중심", "kind": "shoulder_center"},
        {"key": "pelvis_center", "label": "골반 중심", "kind": "pelvis_center"},
    ],
    "follow_through": [
        {"key": "throwing_wrist", "label": "투구 손목", "kind": "throwing_joint", "joint": "wrist"},
        {"key": "throwing_elbow", "label": "투구 팔꿈치", "kind": "throwing_joint", "joint": "elbow"},
        {"key": "throwing_shoulder", "label": "투구 어깨", "kind": "throwing_joint", "joint": "shoulder"},
        {"key": "shoulder_center", "label": "어깨 중심", "kind": "shoulder_center"},
        {"key": "pelvis_center", "label": "골반 중심", "kind": "pelvis_center"},
    ],
}


@dataclass(frozen=True)
class PhaseDirectionConfig:
    min_motion_body_units: float = 0.03


def compute_phase_direction_similarity(
    pro_motion_table: pd.DataFrame,
    user_motion_table: pd.DataFrame,
    alignment: dict[str, Any],
    config: PhaseDirectionConfig | None = None,
) -> dict[str, Any]:
    active_config = config or PhaseDirectionConfig()
    pro_lookup = build_frame_lookup(pro_motion_table)
    user_lookup = build_frame_lookup(user_motion_table)
    phase_rows: list[dict[str, Any]] = []
    phase_summaries: list[dict[str, Any]] = []

    for phase_info in alignment.get("phase_alignments", []):
        phase_name = str(phase_info.get("phase") or "")
        if phase_name not in PHASE_POINT_SPECS:
            continue

        phase_label = PHASE_LABELS.get(phase_name, phase_name)
        pro_start = row_for_frame(pro_lookup, phase_info.get("left_start_frame"))
        pro_end = row_for_frame(pro_lookup, phase_info.get("left_end_frame"))
        user_start = row_for_frame(user_lookup, phase_info.get("right_start_frame"))
        user_end = row_for_frame(user_lookup, phase_info.get("right_end_frame"))

        if any(row is None for row in (pro_start, pro_end, user_start, user_end)):
            phase_summaries.append(
                {
                    "phase": phase_name,
                    "phase_label": phase_label,
                    "score": None,
                    "valid_joint_count": 0,
                    "excluded_joint_count": len(PHASE_POINT_SPECS[phase_name]),
                    "status": "missing_phase_boundary",
                }
            )
            continue

        joint_scores: list[float] = []
        for point_spec in PHASE_POINT_SPECS[phase_name]:
            row = compute_point_direction_score(
                phase_name=phase_name,
                phase_label=phase_label,
                point_spec=point_spec,
                pro_start=pro_start,
                pro_end=pro_end,
                user_start=user_start,
                user_end=user_end,
                min_motion_body_units=active_config.min_motion_body_units,
            )
            phase_rows.append(row)
            if row["status"] == "used" and row["score"] is not None:
                joint_scores.append(float(row["score"]))

        phase_summaries.append(
            {
                "phase": phase_name,
                "phase_label": phase_label,
                "score": safe_mean(joint_scores),
                "valid_joint_count": len(joint_scores),
                "excluded_joint_count": len(PHASE_POINT_SPECS[phase_name]) - len(joint_scores),
                "status": "ready" if joint_scores else "no_valid_joint",
            }
        )

    valid_phase_scores = [float(item["score"]) for item in phase_summaries if item.get("score") is not None]
    overall_score = safe_mean(valid_phase_scores)
    lowest_phase = min(
        (item for item in phase_summaries if item.get("score") is not None),
        key=lambda item: float(item["score"]),
        default=None,
    )
    lowest_joint = min(
        (row for row in phase_rows if row.get("score") is not None),
        key=lambda row: float(row["score"]),
        default=None,
    )

    return {
        "experiment_type": "phase_start_end_direction_similarity",
        "score_scale": "1-100",
        "method": "phase별 시작-끝 단위 방향 벡터 코사인 유사도",
        "config": {"min_motion_body_units": active_config.min_motion_body_units},
        "overall_score": overall_score,
        "phase_scores": phase_summaries,
        "joint_scores": phase_rows,
        "lowest_phase": lowest_phase,
        "lowest_joint": lowest_joint,
        "notes": [
            "이 점수는 최종 유사도 점수가 아니라 B 실험용 후보 점수입니다.",
            "이동량 크기와 속도 차이를 줄이기 위해 시작-끝 벡터를 단위벡터로 변환했습니다.",
            "골반 중심은 body-frame 좌표에서 항상 0이 되므로, body-scale로 나눈 이미지 좌표 변화량을 사용했습니다.",
            "움직임이 너무 작은 관절은 방향이 노이즈에 민감하므로 제외했습니다.",
        ],
    }


def compute_point_direction_score(
    phase_name: str,
    phase_label: str,
    point_spec: dict[str, str],
    pro_start: pd.Series,
    pro_end: pd.Series,
    user_start: pd.Series,
    user_end: pd.Series,
    min_motion_body_units: float,
) -> dict[str, Any]:
    pro_start_point = resolve_point(pro_start, point_spec)
    pro_end_point = resolve_point(pro_end, point_spec)
    user_start_point = resolve_point(user_start, point_spec)
    user_end_point = resolve_point(user_end, point_spec)

    base_row: dict[str, Any] = {
        "phase": phase_name,
        "phase_label": phase_label,
        "point": point_spec["key"],
        "point_label": point_spec["label"],
        "coordinate_source": coordinate_source(point_spec),
        "score": None,
        "cos_similarity": None,
        "pro_magnitude": None,
        "user_magnitude": None,
        "status": "excluded",
        "reason": "",
    }

    if any(point is None for point in (pro_start_point, pro_end_point, user_start_point, user_end_point)):
        base_row["reason"] = "필요한 좌표가 부족합니다."
        return base_row

    pro_vector = np.asarray(pro_end_point, dtype=float) - np.asarray(pro_start_point, dtype=float)
    user_vector = np.asarray(user_end_point, dtype=float) - np.asarray(user_start_point, dtype=float)
    pro_magnitude = float(np.linalg.norm(pro_vector))
    user_magnitude = float(np.linalg.norm(user_vector))
    base_row["pro_magnitude"] = pro_magnitude
    base_row["user_magnitude"] = user_magnitude

    if not np.isfinite(pro_magnitude) or not np.isfinite(user_magnitude):
        base_row["reason"] = "벡터 크기가 유효하지 않습니다."
        return base_row
    if pro_magnitude < min_motion_body_units or user_magnitude < min_motion_body_units:
        base_row["reason"] = f"움직임이 {min_motion_body_units:.3f} body unit보다 작아 방향 비교에서 제외했습니다."
        return base_row

    pro_unit = pro_vector / pro_magnitude
    user_unit = user_vector / user_magnitude
    cos_similarity = float(np.clip(np.dot(pro_unit, user_unit), -1.0, 1.0))
    score = ((cos_similarity + 1.0) / 2.0) * 100.0
    base_row["score"] = round(float(score), 2)
    base_row["cos_similarity"] = round(cos_similarity, 4)
    base_row["status"] = "used"
    base_row["reason"] = ""
    return base_row


def resolve_point(row: pd.Series, point_spec: dict[str, str]) -> tuple[float, float] | None:
    kind = point_spec["kind"]
    if kind == "pelvis_center":
        return resolve_scale_normalized_image_delta_point(row)
    if kind == "shoulder_center":
        return average_body_points(row, "left_shoulder", "right_shoulder")
    if kind == "throwing_joint":
        side = str(row.get("throwing_side") or "").lower()
        if side not in {"left", "right"}:
            return None
        return joint_body_point(row, f"{side}_{point_spec['joint']}")
    if kind == "stride_joint":
        side = str(row.get("stride_side") or "").lower()
        if side not in {"left", "right"}:
            return None
        return joint_body_point(row, f"{side}_{point_spec['joint']}")
    return None


def resolve_scale_normalized_image_delta_point(row: pd.Series) -> tuple[float, float] | None:
    x_value = row.get("pelvis_center_x_px")
    y_value = row.get("pelvis_center_y_px")
    body_scale = row.get("body_scale_px")
    if not all_finite(x_value, y_value, body_scale) or float(body_scale) <= 1e-6:
        return None
    x = float(x_value) / float(body_scale)
    y = float(y_value) / float(body_scale)
    if str(row.get("throwing_side") or "").lower() == "left":
        x *= -1.0
    return x, -y


def average_body_points(row: pd.Series, left_joint: str, right_joint: str) -> tuple[float, float] | None:
    left = joint_body_point(row, left_joint)
    right = joint_body_point(row, right_joint)
    if left is None or right is None:
        return None
    return (left[0] + right[0]) / 2.0, (left[1] + right[1]) / 2.0


def joint_body_point(row: pd.Series, joint_name: str) -> tuple[float, float] | None:
    x_value = row.get(f"{joint_name}_body_x")
    y_value = row.get(f"{joint_name}_body_y")
    confidence = row.get(f"{joint_name}_confidence", 1.0)
    if not all_finite(x_value, y_value, confidence) or float(confidence) < 0.05:
        return None
    return float(x_value), float(y_value)


def coordinate_source(point_spec: dict[str, str]) -> str:
    if point_spec["kind"] == "pelvis_center":
        return "body_scale_normalized_image_delta"
    return "pelvis_centered_body_frame"


def build_frame_lookup(motion_table: pd.DataFrame) -> dict[int, pd.Series]:
    if motion_table.empty:
        return {}
    table = motion_table.drop_duplicates(subset=["frame_index"], keep="first")
    return {int(row["frame_index"]): row for _index, row in table.iterrows()}


def row_for_frame(frame_lookup: dict[int, pd.Series], frame_value: Any) -> pd.Series | None:
    if frame_value is None:
        return None
    try:
        frame_index = int(frame_value)
    except (TypeError, ValueError):
        return None
    return frame_lookup.get(frame_index)


def safe_mean(values: list[float]) -> float | None:
    if not values:
        return None
    return round(float(np.mean(values)), 2)


def all_finite(*values: Any) -> bool:
    for value in values:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return False
        if not np.isfinite(numeric):
            return False
    return True


def write_phase_direction_outputs(result: dict[str, Any], output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "phase_direction_similarity.json"
    csv_path = output_dir / "phase_direction_similarity.csv"
    report_path = output_dir / "phase_direction_report.md"

    json_path.write_text(json.dumps(make_json_safe(result), ensure_ascii=False, indent=2), encoding="utf-8")
    write_joint_scores_csv(result.get("joint_scores", []), csv_path)
    report_path.write_text(render_report(result), encoding="utf-8")
    return {"json": str(json_path), "csv": str(csv_path), "report": str(report_path)}


def write_joint_scores_csv(rows: list[dict[str, Any]], output_path: Path) -> None:
    fieldnames = [
        "phase",
        "phase_label",
        "point",
        "point_label",
        "coordinate_source",
        "score",
        "cos_similarity",
        "pro_magnitude",
        "user_magnitude",
        "status",
        "reason",
    ]
    with output_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in fieldnames})


def render_report(result: dict[str, Any]) -> str:
    lines = [
        "# Phase 시작-끝 방향 벡터 기반 폼 유사도 실험",
        "",
        "## 목적",
        "",
        "투구 매커니즘별 시작점과 끝점의 이동 방향을 비교해, 속도나 이동량 크기보다 동작 방향성이 얼마나 유사한지 확인한다.",
        "",
        "## 전체 후보 점수",
        "",
        f"- 전체 폼 후보 점수: `{format_score(result.get('overall_score'))}`",
        "",
        "## Phase별 점수",
        "",
        "| 구간 | 점수 | 사용 관절 수 | 제외 관절 수 | 상태 |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    for phase in result.get("phase_scores", []):
        lines.append(
            f"| {phase.get('phase_label')} | {format_score(phase.get('score'))} | "
            f"{phase.get('valid_joint_count')} | {phase.get('excluded_joint_count')} | {phase.get('status')} |"
        )

    lines.extend(["", "## 관절별 점수", "", "| 구간 | 관절/기준점 | 점수 | 상태 | 제외 이유 |", "| --- | --- | ---: | --- | --- |"])
    for row in result.get("joint_scores", []):
        lines.append(
            f"| {row.get('phase_label')} | {row.get('point_label')} | {format_score(row.get('score'))} | "
            f"{row.get('status')} | {row.get('reason') or '-'} |"
        )

    lowest_phase = result.get("lowest_phase") or {}
    lowest_joint = result.get("lowest_joint") or {}
    lines.extend(
        [
            "",
            "## 관찰 포인트",
            "",
            f"- 가장 낮은 phase: `{lowest_phase.get('phase_label', '-')}` (`{format_score(lowest_phase.get('score'))}`)",
            f"- 가장 낮은 관절/기준점: `{lowest_joint.get('phase_label', '-')}` / `{lowest_joint.get('point_label', '-')}` (`{format_score(lowest_joint.get('score'))}`)",
            "",
            "## 해석 주의",
            "",
            "- 이 점수는 최종 유사도 점수가 아니라 B 실험용 후보 점수이다.",
            "- 시작-끝 방향만 보기 때문에 phase 내부의 세부 궤적 변화는 비교하지 않는다.",
            "- 움직임이 작은 관절은 방향이 노이즈에 민감하므로 제외한다.",
        ]
    )
    return "\n".join(lines) + "\n"


def format_score(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "-"


def make_json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): make_json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [make_json_safe(item) for item in value]
    if hasattr(value, "item"):
        return value.item()
    return value
