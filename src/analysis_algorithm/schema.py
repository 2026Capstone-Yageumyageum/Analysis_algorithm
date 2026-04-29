from __future__ import annotations

from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
CAPSTONE_ROOT = PACKAGE_ROOT.parent

DEFAULT_USER_VIDEO = CAPSTONE_ROOT / "user_data" / "y1.mp4"
DEFAULT_PRO_VIDEO = CAPSTONE_ROOT / "pro_data" / "hyun_jin_ryu_ball_to_junior_caminero_20230923_6s.mp4"

JOINT_INDEX_MAP = {
    "nose": 0,
    "left_shoulder": 11,
    "right_shoulder": 12,
    "left_elbow": 13,
    "right_elbow": 14,
    "left_wrist": 15,
    "right_wrist": 16,
    "left_hip": 23,
    "right_hip": 24,
    "left_knee": 25,
    "right_knee": 26,
    "left_ankle": 27,
    "right_ankle": 28,
    "left_foot_index": 31,
    "right_foot_index": 32,
}

JOINT_NAMES = tuple(JOINT_INDEX_MAP.keys())

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

PHASE_ORDER = ("setup", "leg_lift", "stride", "release", "follow_through")
