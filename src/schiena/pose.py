"""Pose estimation engine (MediaPipe Pose Landmarker) and Sample construction."""

from __future__ import annotations

import math
import threading
import urllib.request
from pathlib import Path
from typing import Protocol

import numpy as np

from . import camera
from .camera import CameraPose
from .posture import HIP, SHOULDER, Landmark, Measurement, measure

MODEL_URLS = {
    "heavy": "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/latest/pose_landmarker_heavy.task",
    "full": "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/latest/pose_landmarker_full.task",
}


class PoseResult:
    def __init__(self, landmarks: list[Landmark] | None, mask: np.ndarray | None, world: list[tuple] | None):
        self.landmarks = landmarks
        self.mask = mask
        self.world = world


class PoseEstimator(Protocol):
    def estimate(self, rgb: np.ndarray, timestamp_ms: int) -> PoseResult: ...


def ensure_model(models_dir: Path, variant: str = "heavy") -> Path:
    path = models_dir / f"pose_landmarker_{variant}.task"
    if not path.exists():
        models_dir.mkdir(parents=True, exist_ok=True)
        print(f"Downloading the MediaPipe pose model ({variant}) …", flush=True)
        tmp = path.with_suffix(".part")
        urllib.request.urlretrieve(MODEL_URLS[variant], tmp)
        tmp.rename(path)
    return path


class MediaPipeEstimator:
    """MediaPipe Pose Landmarker in VIDEO mode (temporal smoothing between frames)."""

    def __init__(self, model_path: Path):
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions, vision

        self._mp = mp
        opts = vision.PoseLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(model_path)),
            running_mode=vision.RunningMode.VIDEO,
            output_segmentation_masks=True,
            num_poses=1,
        )
        self._landmarker = vision.PoseLandmarker.create_from_options(opts)
        self._lock = threading.Lock()
        self._last_ts = -1

    def estimate(self, rgb: np.ndarray, timestamp_ms: int) -> PoseResult:
        h, w = rgb.shape[:2]
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
        with self._lock:
            ts = max(timestamp_ms, self._last_ts + 1)
            self._last_ts = ts
            r = self._landmarker.detect_for_video(image, ts)
        if not r.pose_landmarks:
            return PoseResult(None, None, None)
        lms = [Landmark(p.x * w, p.y * h, p.visibility) for p in r.pose_landmarks[0]]
        world = [(p.x, p.y, p.z) for p in r.pose_world_landmarks[0]] if r.pose_world_landmarks else None
        mask = r.segmentation_masks[0].numpy_view().copy() if r.segmentation_masks else None
        if mask is not None and mask.ndim == 3:
            mask = mask[..., 0]
        return PoseResult(lms, mask, world)


def metres_per_pixel(m: Measurement, world: list[tuple] | None) -> float | None:
    """Image scale from MediaPipe's metric world landmarks (approximate, assumes average body size)."""
    if not world or not m.trunk_length or not m.side:
        return None
    sh, hp = world[SHOULDER[m.side]], world[HIP[m.side]]
    return math.dist(sh, hp) / m.trunk_length


def level(result: PoseResult, w: int, h: int, cam: CameraPose | None):
    """Landmarks and mask as a level camera would see them, and the map back to the frame."""
    if cam is None or not result.landmarks:
        return result.landmarks, result.mask, None
    import cv2

    H = camera.homography(cam, w, h)
    pts = camera.apply(H, [(l.x, l.y) for l in result.landmarks])
    lms = [Landmark(x, y, l.visibility) for (x, y), l in zip(pts, result.landmarks)]
    mask = None
    if result.mask is not None:
        mask = cv2.warpPerspective(result.mask.astype(np.float32), H, (result.mask.shape[1], result.mask.shape[0]),
                                   flags=cv2.INTER_LINEAR, borderValue=0)
    return lms, mask, np.linalg.inv(H)


def make_sample(t: float, result: PoseResult, w: int, h: int, trunk_m: float | None = None,
                cam: CameraPose | None = None) -> dict:
    """trunk_m: the user's calibrated shoulder→hip length in metres (better than the model's average body).
    cam: the phone's orientation; angles are measured as if the phone were level.

    Stored coordinates (kp, back, hip) are in the original frame, so they can be drawn on it;
    "camera" says how to level them."""
    lms, mask, back_to_frame = level(result, w, h, cam)
    m = measure(lms, mask)
    sample: dict = {"t": round(t, 3), "person": m.person, "valid": m.valid, "w": w, "h": h}
    if not m.person:
        return sample
    contour = camera.apply(back_to_frame, m.back_contour) if back_to_frame is not None else m.back_contour
    hip = (result.landmarks[HIP[m.side]].x, result.landmarks[HIP[m.side]].y) if m.hip else None
    sample.update({
        "side": m.side,
        "fwd": m.forward,
        "trunk_len": round(m.trunk_length, 2) if m.trunk_length else None,
        "hip": [round(hip[0], 1), round(hip[1], 1)] if hip else None,
        "metrics": {k: (round(v, 3) if v is not None and not math.isnan(v) else None) for k, v in m.metrics.items()},
        "kp": [[round(l.x / w, 4), round(l.y / h, 4), round(l.visibility, 2)] for l in result.landmarks],
        "back": [[round(x / w, 4), round(y / h, 4)] for x, y in contour],
        "mpp": (trunk_m / m.trunk_length) if (trunk_m and m.trunk_length) else metres_per_pixel(m, result.world),
        "scale": "calibrated" if (trunk_m and m.trunk_length) else "model",
    })
    if cam is not None:
        sample["camera"] = cam.as_dict()
    yaw = camera.yaw_from_world(result.world)
    if yaw is not None:
        sample["yaw"] = round(yaw, 1)
    if sample["mpp"]:
        sample["mpp"] = round(sample["mpp"], 6)
    return sample
