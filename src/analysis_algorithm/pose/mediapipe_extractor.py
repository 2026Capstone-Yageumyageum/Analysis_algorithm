from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

from analysis_algorithm.schema import JOINT_INDEX_MAP, JOINT_NAMES, PACKAGE_ROOT


class PoseEstimationUnavailableError(RuntimeError):
    """Raised when MediaPipe cannot be imported or initialized."""


OCCLUSION_PARENT_MAP = {
    "left_elbow": "left_shoulder",
    "right_elbow": "right_shoulder",
    "left_wrist": "left_elbow",
    "right_wrist": "right_elbow",
    "left_knee": "left_hip",
    "right_knee": "right_hip",
    "left_ankle": "left_knee",
    "right_ankle": "right_knee",
    "left_foot_index": "left_ankle",
    "right_foot_index": "right_ankle",
}

OCCLUSION_MAX_GAP_MAP = {
    "left_elbow": 4,
    "right_elbow": 4,
    "left_wrist": 5,
    "right_wrist": 5,
    "left_knee": 4,
    "right_knee": 4,
    "left_ankle": 2,
    "right_ankle": 2,
    "left_foot_index": 2,
    "right_foot_index": 2,
}

OCCLUSION_CONFIDENCE_THRESHOLD_MAP = {
    "left_elbow": 0.45,
    "right_elbow": 0.45,
    "left_wrist": 0.45,
    "right_wrist": 0.45,
    "left_knee": 0.34,
    "right_knee": 0.34,
    "left_ankle": 0.30,
    "right_ankle": 0.30,
    "left_foot_index": 0.30,
    "right_foot_index": 0.30,
}


@dataclass
class PoseResult:
    keypoints_df: pd.DataFrame
    fps: float
    frame_width: int
    frame_height: int
    frame_count: int
    warnings: list[str]


@dataclass(frozen=True)
class OcclusionRepairConfig:
    confidence_multiplier: float = 0.75
    parent_confidence_threshold: float = 0.18
    velocity_mismatch_body_scale: float = 0.90
    bone_length_blend: float = 0.65


class MediaPipePoseEstimator:
    """MediaPipe-only 2D pose extractor used by the current similarity experiments."""

    def __init__(
        self,
        model_complexity: int = 1,
        min_detection_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
        smooth_window: int = 5,
        smoothing_confidence_threshold: float = 0.4,
        model_asset_path: Path | None = None,
    ) -> None:
        try:
            import mediapipe as mp
        except ImportError as exc:
            raise PoseEstimationUnavailableError(
                "MediaPipe import failed. Install requirements.txt before running the experiment."
            ) from exc

        self._mp = mp
        self._backend = ""
        self._pose = None
        self._landmarker = None
        self._image_cls = None
        self._image_format = None

        if hasattr(mp, "solutions") and hasattr(mp.solutions, "pose"):
            try:
                self._pose = mp.solutions.pose.Pose(
                    static_image_mode=False,
                    model_complexity=model_complexity,
                    enable_segmentation=False,
                    smooth_landmarks=True,
                    min_detection_confidence=min_detection_confidence,
                    min_tracking_confidence=min_tracking_confidence,
                )
            except Exception as exc:  # noqa: BLE001
                raise PoseEstimationUnavailableError(f"MediaPipe solutions Pose initialization failed: {exc}") from exc
            self._backend = "solutions"
            self.model_name = f"MediaPipe Solutions Pose (BlazePose GHUM 2D, model_complexity={model_complexity})"
        else:
            task_model_path = model_asset_path or default_pose_task_path()
            if not task_model_path.exists():
                raise PoseEstimationUnavailableError(
                    "MediaPipe Tasks PoseLandmarker model file is missing. "
                    f"Expected: {task_model_path}. Run scripts/download_pose_model.py first."
                )
            try:
                BaseOptions = mp.tasks.BaseOptions
                PoseLandmarker = mp.tasks.vision.PoseLandmarker
                PoseLandmarkerOptions = mp.tasks.vision.PoseLandmarkerOptions
                RunningMode = mp.tasks.vision.RunningMode
                options = PoseLandmarkerOptions(
                    base_options=BaseOptions(
                        model_asset_path=str(task_model_path),
                        delegate=BaseOptions.Delegate.CPU,
                    ),
                    running_mode=RunningMode.VIDEO,
                    num_poses=1,
                    min_pose_detection_confidence=min_detection_confidence,
                    min_pose_presence_confidence=min_detection_confidence,
                    min_tracking_confidence=min_tracking_confidence,
                    output_segmentation_masks=False,
                )
                self._landmarker = PoseLandmarker.create_from_options(options)
                self._image_cls = mp.Image
                self._image_format = mp.ImageFormat.SRGB
            except Exception as exc:  # noqa: BLE001
                raise PoseEstimationUnavailableError(f"MediaPipe Tasks PoseLandmarker initialization failed: {exc}") from exc
            self._backend = "tasks"
            self.model_name = f"MediaPipe Tasks PoseLandmarker 2D ({task_model_path.name})"

        self.joint_names = list(JOINT_NAMES)
        self.smooth_window = smooth_window
        self.smoothing_confidence_threshold = smoothing_confidence_threshold
        self.occlusion_config = OcclusionRepairConfig()

    def process_video(self, video_path: Path) -> PoseResult:
        capture = cv2.VideoCapture(str(video_path))
        if not capture.isOpened():
            raise RuntimeError(f"Could not open video: {video_path}")

        fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
        frame_width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        frame_height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        frame_records: list[dict[str, float]] = []
        frame_index = 0
        warnings: list[str] = []

        try:
            while True:
                success, frame = capture.read()
                if not success:
                    break
                if frame_width <= 0 or frame_height <= 0:
                    frame_height, frame_width = frame.shape[:2]

                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                landmarks = self._detect_landmarks(rgb_frame=rgb_frame, frame_index=frame_index, fps=fps if fps > 0 else 30.0)
                frame_records.append(
                    self._build_frame_record(
                        frame_index=frame_index,
                        fps=fps if fps > 0 else 30.0,
                        frame_width=frame_width,
                        frame_height=frame_height,
                        landmarks=landmarks,
                    )
                )
                frame_index += 1
        finally:
            capture.release()

        if not frame_records:
            warnings.append("No readable frames were extracted from the video.")

        keypoints_df = pd.DataFrame(frame_records)
        if not keypoints_df.empty:
            keypoints_df = self._append_smoothed_keypoints(keypoints_df)

        return PoseResult(
            keypoints_df=keypoints_df,
            fps=fps if fps > 0 else 30.0,
            frame_width=frame_width if frame_width > 0 else 1280,
            frame_height=frame_height if frame_height > 0 else 720,
            frame_count=len(frame_records),
            warnings=warnings,
        )

    def _detect_landmarks(self, rgb_frame: np.ndarray, frame_index: int, fps: float):
        if self._backend == "solutions":
            results = self._pose.process(rgb_frame)
            return results.pose_landmarks.landmark if results.pose_landmarks else None

        mp_image = self._image_cls(image_format=self._image_format, data=rgb_frame)
        timestamp_ms = int(round((frame_index / fps) * 1000.0)) if fps > 0 else int(frame_index * 33)
        result = self._landmarker.detect_for_video(mp_image, timestamp_ms)
        if not result.pose_landmarks:
            return None
        return result.pose_landmarks[0]

    def _build_frame_record(
        self,
        frame_index: int,
        fps: float,
        frame_width: int,
        frame_height: int,
        landmarks,
    ) -> dict[str, float]:
        record: dict[str, float] = {
            "frame_index": int(frame_index),
            "time_sec": float(frame_index / fps) if fps > 0 else float(frame_index / 30.0),
        }

        for joint_name, landmark_index in JOINT_INDEX_MAP.items():
            if landmarks is None:
                record[f"{joint_name}_x"] = np.nan
                record[f"{joint_name}_y"] = np.nan
                record[f"{joint_name}_confidence"] = 0.0
                continue

            landmark = landmarks[landmark_index]
            record[f"{joint_name}_x"] = float(landmark.x * frame_width)
            record[f"{joint_name}_y"] = float(landmark.y * frame_height)
            record[f"{joint_name}_confidence"] = float(getattr(landmark, "visibility", 0.0))

        return record

    def _append_smoothed_keypoints(self, keypoints_df: pd.DataFrame) -> pd.DataFrame:
        df = self._repair_short_self_occlusions(keypoints_df.copy())
        for joint_name in self.joint_names:
            x_col = f"{joint_name}_x"
            y_col = f"{joint_name}_y"
            conf_col = f"{joint_name}_confidence"
            smooth_x_col = f"{joint_name}_x_smooth"
            smooth_y_col = f"{joint_name}_y_smooth"
            imputed_col = f"{joint_name}_imputed_flag"

            imputed_mask = (
                df[imputed_col].fillna(0).astype(bool)
                if imputed_col in df.columns
                else pd.Series(False, index=df.index)
            )
            valid_mask = (df[conf_col] >= self.smoothing_confidence_threshold) | imputed_mask
            if valid_mask.sum() >= 2:
                x_interpolated = df[x_col].where(valid_mask).interpolate(limit_direction="both")
                y_interpolated = df[y_col].where(valid_mask).interpolate(limit_direction="both")
                df[smooth_x_col] = x_interpolated.rolling(window=self.smooth_window, center=True, min_periods=1).mean()
                df[smooth_y_col] = y_interpolated.rolling(window=self.smooth_window, center=True, min_periods=1).mean()
            else:
                df[smooth_x_col] = df[x_col]
                df[smooth_y_col] = df[y_col]

        return df

    def _repair_short_self_occlusions(self, keypoints_df: pd.DataFrame) -> pd.DataFrame:
        repaired_df = keypoints_df.copy()
        for joint_name in self.joint_names:
            if joint_name in OCCLUSION_PARENT_MAP:
                repaired_df = self._repair_joint_short_gaps(repaired_df, joint_name)
        return repaired_df

    def _repair_joint_short_gaps(self, keypoints_df: pd.DataFrame, joint_name: str) -> pd.DataFrame:
        x_col = f"{joint_name}_x"
        y_col = f"{joint_name}_y"
        conf_col = f"{joint_name}_confidence"
        imputed_col = f"{joint_name}_imputed_flag"
        parent_joint = OCCLUSION_PARENT_MAP[joint_name]
        parent_x_col = f"{parent_joint}_x"
        parent_y_col = f"{parent_joint}_y"
        parent_conf_col = f"{parent_joint}_confidence"

        required_columns = [x_col, y_col, conf_col, parent_x_col, parent_y_col, parent_conf_col]
        if any(column not in keypoints_df.columns for column in required_columns):
            return keypoints_df

        repaired_df = keypoints_df.copy()
        if imputed_col not in repaired_df.columns:
            repaired_df[imputed_col] = 0

        x_values = repaired_df[x_col].to_numpy(dtype=float)
        y_values = repaired_df[y_col].to_numpy(dtype=float)
        confidences = repaired_df[conf_col].fillna(0.0).to_numpy(dtype=float)
        parent_x = repaired_df[parent_x_col].to_numpy(dtype=float)
        parent_y = repaired_df[parent_y_col].to_numpy(dtype=float)
        parent_conf = repaired_df[parent_conf_col].fillna(0.0).to_numpy(dtype=float)

        threshold = OCCLUSION_CONFIDENCE_THRESHOLD_MAP.get(
            joint_name,
            self.smoothing_confidence_threshold * self.occlusion_config.confidence_multiplier,
        )
        valid_mask = (confidences >= threshold) & np.isfinite(x_values) & np.isfinite(y_values)
        target_length = self._estimate_projected_bone_length(repaired_df, parent_joint, joint_name)
        if not np.isfinite(target_length) or target_length <= 1.0:
            return repaired_df

        body_scale = self._estimate_body_scale(repaired_df)
        gap_ranges = self._find_short_gaps(~valid_mask, OCCLUSION_MAX_GAP_MAP.get(joint_name, 2))

        for start_index, end_index in gap_ranges:
            prev_index = start_index - 1
            next_index = end_index + 1
            if prev_index < 0 or next_index >= len(repaired_df):
                continue
            if not valid_mask[prev_index] or not valid_mask[next_index]:
                continue
            if float(np.min(parent_conf[start_index : end_index + 1])) < self.occlusion_config.parent_confidence_threshold:
                continue

            start_point = np.array([x_values[prev_index], y_values[prev_index]], dtype=float)
            end_point = np.array([x_values[next_index], y_values[next_index]], dtype=float)
            start_velocity = self._estimate_boundary_velocity(x_values, y_values, valid_mask, prev_index, forward=False)
            end_velocity = self._estimate_boundary_velocity(x_values, y_values, valid_mask, next_index, forward=True)
            if np.linalg.norm(end_velocity - start_velocity) > body_scale * self.occlusion_config.velocity_mismatch_body_scale:
                continue

            for frame_index in range(start_index, end_index + 1):
                alpha = (frame_index - prev_index) / float(next_index - prev_index)
                predicted_point = self._cubic_hermite_point(start_point, end_point, start_velocity, end_velocity, alpha)
                parent_point = np.array([parent_x[frame_index], parent_y[frame_index]], dtype=float)
                if np.all(np.isfinite(parent_point)):
                    direction = predicted_point - parent_point
                    direction_norm = float(np.linalg.norm(direction))
                    if direction_norm > 1e-6:
                        constrained_point = parent_point + (direction / direction_norm) * target_length
                        predicted_point = (
                            predicted_point * (1.0 - self.occlusion_config.bone_length_blend)
                            + constrained_point * self.occlusion_config.bone_length_blend
                        )

                repaired_df.at[frame_index, x_col] = float(predicted_point[0])
                repaired_df.at[frame_index, y_col] = float(predicted_point[1])
                repaired_df.at[frame_index, imputed_col] = 1

        return repaired_df

    @staticmethod
    def _find_short_gaps(invalid_mask: np.ndarray, max_gap: int) -> list[tuple[int, int]]:
        gap_ranges: list[tuple[int, int]] = []
        gap_start: int | None = None
        for index, invalid in enumerate(invalid_mask):
            if invalid and gap_start is None:
                gap_start = index
                continue
            if invalid or gap_start is None:
                continue
            gap_end = index - 1
            if (gap_end - gap_start + 1) <= max_gap:
                gap_ranges.append((gap_start, gap_end))
            gap_start = None
        if gap_start is not None:
            gap_end = len(invalid_mask) - 1
            if (gap_end - gap_start + 1) <= max_gap:
                gap_ranges.append((gap_start, gap_end))
        return gap_ranges

    @staticmethod
    def _estimate_boundary_velocity(
        x_values: np.ndarray,
        y_values: np.ndarray,
        valid_mask: np.ndarray,
        anchor_index: int,
        forward: bool,
    ) -> np.ndarray:
        anchor_point = np.array([x_values[anchor_index], y_values[anchor_index]], dtype=float)
        neighbor_index = anchor_index + 1 if forward else anchor_index - 1
        if 0 <= neighbor_index < len(valid_mask) and valid_mask[neighbor_index]:
            neighbor_point = np.array([x_values[neighbor_index], y_values[neighbor_index]], dtype=float)
            return neighbor_point - anchor_point if forward else anchor_point - neighbor_point
        return np.zeros(2, dtype=float)

    @staticmethod
    def _cubic_hermite_point(p0: np.ndarray, p1: np.ndarray, m0: np.ndarray, m1: np.ndarray, t: float) -> np.ndarray:
        h00 = (2.0 * (t**3)) - (3.0 * (t**2)) + 1.0
        h10 = (t**3) - (2.0 * (t**2)) + t
        h01 = (-2.0 * (t**3)) + (3.0 * (t**2))
        h11 = (t**3) - (t**2)
        return (h00 * p0) + (h10 * m0) + (h01 * p1) + (h11 * m1)

    def _estimate_projected_bone_length(self, keypoints_df: pd.DataFrame, parent_joint: str, child_joint: str) -> float:
        parent_conf = keypoints_df[f"{parent_joint}_confidence"].fillna(0.0).to_numpy(dtype=float)
        child_conf = keypoints_df[f"{child_joint}_confidence"].fillna(0.0).to_numpy(dtype=float)
        valid_mask = (parent_conf >= self.smoothing_confidence_threshold) & (child_conf >= self.smoothing_confidence_threshold)
        if not valid_mask.any():
            return float("nan")
        dx = keypoints_df[f"{child_joint}_x"].to_numpy(dtype=float) - keypoints_df[f"{parent_joint}_x"].to_numpy(dtype=float)
        dy = keypoints_df[f"{child_joint}_y"].to_numpy(dtype=float) - keypoints_df[f"{parent_joint}_y"].to_numpy(dtype=float)
        lengths = np.sqrt((dx**2) + (dy**2))[valid_mask]
        lengths = lengths[np.isfinite(lengths)]
        return float(np.median(lengths)) if len(lengths) else float("nan")

    @staticmethod
    def _estimate_body_scale(keypoints_df: pd.DataFrame) -> float:
        candidate_lengths: list[np.ndarray] = []
        shoulder_cols = {"left_shoulder_x", "left_shoulder_y", "right_shoulder_x", "right_shoulder_y"}
        hip_cols = {"left_hip_x", "left_hip_y", "right_hip_x", "right_hip_y"}
        if shoulder_cols.issubset(keypoints_df.columns):
            candidate_lengths.append(
                np.hypot(
                    keypoints_df["right_shoulder_x"].to_numpy(dtype=float) - keypoints_df["left_shoulder_x"].to_numpy(dtype=float),
                    keypoints_df["right_shoulder_y"].to_numpy(dtype=float) - keypoints_df["left_shoulder_y"].to_numpy(dtype=float),
                )
            )
        if hip_cols.issubset(keypoints_df.columns):
            candidate_lengths.append(
                np.hypot(
                    keypoints_df["right_hip_x"].to_numpy(dtype=float) - keypoints_df["left_hip_x"].to_numpy(dtype=float),
                    keypoints_df["right_hip_y"].to_numpy(dtype=float) - keypoints_df["left_hip_y"].to_numpy(dtype=float),
                )
            )
        finite_values = [values[np.isfinite(values)] for values in candidate_lengths]
        finite_values = [values for values in finite_values if len(values)]
        if not finite_values:
            return 100.0
        return float(np.median(np.concatenate(finite_values)))


def default_pose_task_path() -> Path:
    return PACKAGE_ROOT / "models" / "pose_landmarker_lite.task"
