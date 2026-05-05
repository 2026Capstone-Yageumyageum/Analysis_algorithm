from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
MPL_CACHE_DIR = REPO_ROOT / ".cache" / "matplotlib"
MPL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(MPL_CACHE_DIR))
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from analysis_algorithm.pipeline import run_pair_experiment  # noqa: E402
from analysis_algorithm.schema import DEFAULT_PRO_VIDEO, DEFAULT_USER_VIDEO  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the current phase-aware pitching comparison experiment.")
    parser.add_argument("--pro-video", type=Path, default=DEFAULT_PRO_VIDEO)
    parser.add_argument("--user-video", type=Path, default=DEFAULT_USER_VIDEO)
    parser.add_argument("--output-root", type=Path, default=REPO_ROOT / "outputs")
    parser.add_argument("--pro-height-cm", type=float, default=None)
    parser.add_argument("--user-height-cm", type=float, default=None)
    parser.add_argument("--pro-handedness", choices=["left", "right"], default=None)
    parser.add_argument("--user-handedness", choices=["left", "right"], default=None)
    parser.add_argument("--skip-overlay", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    missing_paths = [path for path in (args.pro_video, args.user_video) if not path.exists()]
    if missing_paths:
        print("Missing input video(s):")
        for path in missing_paths:
            print(f"- {path}")
        return 1

    summary = run_pair_experiment(
        pro_video=args.pro_video,
        user_video=args.user_video,
        output_root=args.output_root,
        pro_height_cm=args.pro_height_cm,
        user_height_cm=args.user_height_cm,
        pro_handedness=args.pro_handedness,
        user_handedness=args.user_handedness,
        render_overlay=not args.skip_overlay,
    )
    print(f"experiment_dir: {summary['outputs']['experiment_dir']}")
    print(f"alignment: {summary['outputs']['alignment']}")
    print(f"alignment_status: {summary['alignment_status']}")
    print(f"aligned_pair_count: {summary['aligned_pair_count']}")
    if summary["outputs"].get("phase_dtw_overlay"):
        print(f"phase_dtw_overlay: {summary['outputs']['phase_dtw_overlay']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
