from __future__ import annotations

from pathlib import Path
import os
from urllib.request import urlretrieve


REPO_ROOT = Path(__file__).resolve().parents[1]
MPL_CACHE_DIR = REPO_ROOT / ".cache" / "matplotlib"
MPL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(MPL_CACHE_DIR))
MODEL_URL = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task"
MODEL_PATH = REPO_ROOT / "models" / "pose_landmarker_lite.task"


def main() -> int:
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    if MODEL_PATH.exists() and MODEL_PATH.stat().st_size > 0:
        print(f"model already exists: {MODEL_PATH}")
        return 0
    print(f"downloading: {MODEL_URL}")
    urlretrieve(MODEL_URL, MODEL_PATH)
    print(f"saved: {MODEL_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
