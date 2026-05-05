from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert keypoints CSV into frontend displayKeypoints JSON reference format."
    )
    parser.add_argument("--csv", type=Path, required=True, help="keypoints.csv file path.")
    parser.add_argument(
        "--phase-json",
        type=Path,
        default=None,
        help="Optional full analysis response or phaseDetection JSON path.",
    )
    parser.add_argument("--target", choices=["user", "pro"], default="user")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--max-frames", type=int, default=None)
    return parser.parse_args()


def convert_csv_to_display_keypoints(
    csv_text: str,
    *,
    target: str = "user",
    phase_payload: dict[str, Any] | None = None,
    max_frames: int | None = None,
) -> list[dict[str, Any]]:
    rows = list(csv.DictReader(csv_text.splitlines()))
    intervals = _extract_intervals(phase_payload or {}, target)
    output: list[dict[str, Any]] = []
    for row in rows[:max_frames]:
        frame_index = _safe_int(row.get("frame_index"))
        output.append(
            {
                "frameIndex": frame_index,
                "timeSec": _safe_float(row.get("time_sec")),
                "phase": _phase_for_frame(frame_index, intervals),
                "points": _points_from_row(row),
            }
        )
    return output


def _points_from_row(row: dict[str, str]) -> dict[str, dict[str, Any]]:
    points: dict[str, dict[str, Any]] = {}
    for joint in JOINTS:
        x_value = _safe_float(row.get(f"{joint}_x_smooth") or row.get(f"{joint}_x"))
        y_value = _safe_float(row.get(f"{joint}_y_smooth") or row.get(f"{joint}_y"))
        points[_camel_case(joint)] = {
            "x": x_value,
            "y": y_value,
            "confidence": _safe_float(row.get(f"{joint}_confidence")),
            "imputed": _safe_bool(row.get(f"{joint}_imputed_flag")),
        }
    return points


def _extract_intervals(payload: dict[str, Any], target: str) -> list[dict[str, Any]]:
    player_phase_scores = _selected_player_phase_scores(payload)
    if player_phase_scores:
        prefix = "user" if target == "user" else "pro"
        return [
            {
                "phase": item.get("phase"),
                "startFrame": _safe_int(item.get(f"{prefix}StartFrame")),
                "endFrame": _safe_int(item.get(f"{prefix}EndFrame")),
            }
            for item in player_phase_scores
            if isinstance(item, dict)
        ]

    phase_detection = payload.get("phaseDetection") if "phaseDetection" in payload else payload
    target_detection = phase_detection.get(target) if isinstance(phase_detection, dict) else {}
    intervals = (target_detection or {}).get("intervals") if isinstance(target_detection, dict) else None
    if isinstance(intervals, dict) and intervals:
        return [
            {
                "phase": item.get("phase") or phase_name,
                "startFrame": _safe_int(item.get("startFrame")),
                "endFrame": _safe_int(item.get("endFrame")),
            }
            for phase_name, item in intervals.items()
            if isinstance(item, dict)
        ]

    phase_scores = payload.get("phaseScores", [])
    if not isinstance(phase_scores, list):
        return []
    prefix = "user" if target == "user" else "pro"
    return [
        {
            "phase": item.get("phase"),
            "startFrame": _safe_int(item.get(f"{prefix}StartFrame")),
            "endFrame": _safe_int(item.get(f"{prefix}EndFrame")),
        }
        for item in phase_scores
        if isinstance(item, dict)
    ]


def _selected_player_phase_scores(payload: dict[str, Any]) -> list[dict[str, Any]]:
    players = payload.get("players")
    if not isinstance(players, list) or not players:
        return []
    selected_player = players[0]
    if not isinstance(selected_player, dict):
        return []
    phase_scores = selected_player.get("phaseScores")
    return phase_scores if isinstance(phase_scores, list) else []


def _phase_for_frame(frame_index: int, intervals: list[dict[str, Any]]) -> str | None:
    for interval in intervals:
        start_frame = _safe_int(interval.get("startFrame"))
        end_frame = _safe_int(interval.get("endFrame"))
        if start_frame <= frame_index <= end_frame:
            return interval.get("phase")
    return None


def _camel_case(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes"}


def main() -> int:
    args = parse_args()
    phase_payload = json.loads(args.phase_json.read_text(encoding="utf-8")) if args.phase_json else None
    display_keypoints = convert_csv_to_display_keypoints(
        args.csv.read_text(encoding="utf-8"),
        target=args.target,
        phase_payload=phase_payload,
        max_frames=args.max_frames,
    )
    payload = {"target": args.target, "displayKeypoints": display_keypoints}
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
