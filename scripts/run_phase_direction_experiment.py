from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
MPL_CACHE_DIR = REPO_ROOT / ".cache" / "matplotlib"
MPL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(MPL_CACHE_DIR))
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from analysis_algorithm.pipeline import run_pair_experiment  # noqa: E402
from analysis_algorithm.schema import DEFAULT_PRO_VIDEO, DEFAULT_USER_VIDEO  # noqa: E402
from analysis_algorithm.similarity.phase_direction import (  # noqa: E402
    PhaseDirectionConfig,
    compute_phase_direction_similarity,
    write_phase_direction_outputs,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run phase start-end direction-vector similarity experiment.")
    parser.add_argument("--experiment-dir", type=Path, default=None, help="Existing outputs/expN directory to reuse.")
    parser.add_argument("--output-root", type=Path, default=REPO_ROOT / "outputs")
    parser.add_argument("--pro-video", type=Path, default=DEFAULT_PRO_VIDEO)
    parser.add_argument("--user-video", type=Path, default=DEFAULT_USER_VIDEO)
    parser.add_argument("--pro-height-cm", type=float, default=None)
    parser.add_argument("--user-height-cm", type=float, default=None)
    parser.add_argument("--pro-handedness", choices=["left", "right"], default=None)
    parser.add_argument("--user-handedness", choices=["left", "right"], default=None)
    parser.add_argument("--min-motion", type=float, default=0.03)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    experiment_dir = args.experiment_dir
    if experiment_dir is None:
        summary = run_pair_experiment(
            pro_video=args.pro_video,
            user_video=args.user_video,
            output_root=args.output_root,
            pro_height_cm=args.pro_height_cm,
            user_height_cm=args.user_height_cm,
            pro_handedness=args.pro_handedness,
            user_handedness=args.user_handedness,
            render_overlay=False,
        )
        experiment_dir = Path(str(summary["outputs"]["experiment_dir"]))

    required_files = {
        "pro_motion_table": experiment_dir / "pro" / "motion_table.csv",
        "user_motion_table": experiment_dir / "user" / "motion_table.csv",
        "alignment": experiment_dir / "phase_dtw_alignment.json",
    }
    missing_files = [path for path in required_files.values() if not path.exists()]
    if missing_files:
        print("Missing required experiment file(s):")
        for path in missing_files:
            print(f"- {path}")
        return 1

    pro_motion_table = pd.read_csv(required_files["pro_motion_table"])
    user_motion_table = pd.read_csv(required_files["user_motion_table"])
    alignment = json.loads(required_files["alignment"].read_text(encoding="utf-8"))
    result = compute_phase_direction_similarity(
        pro_motion_table=pro_motion_table,
        user_motion_table=user_motion_table,
        alignment=alignment,
        config=PhaseDirectionConfig(min_motion_body_units=args.min_motion),
    )
    outputs = write_phase_direction_outputs(result, experiment_dir)

    print(f"experiment_dir: {experiment_dir}")
    print(f"overall_score: {result.get('overall_score')}")
    print(f"json: {outputs['json']}")
    print(f"csv: {outputs['csv']}")
    print(f"report: {outputs['report']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
