"""Where the phone points, and how to undo it (pure).

Angles are measured from the vertical, so a phone leaning 3° sideways shifts every angle by 3°.
The phone sends its gravity vector with each frame; the frame's landmarks and person mask are
re-projected onto a virtual camera that is level (optical axis horizontal, image "up" = real up)
before anything is measured. Distance and position in the image don't change angles, so they
are not corrected and don't need to be repeated between Sessions.

The angle between the camera and the person's side ("yaw") is estimated from MediaPipe's 3D
world landmarks. It is not corrected (at 15° the error on a 30° angle is under 1°), only
reported and checked.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

# Focal length as a fraction of the image's long side. Phone front cameras are ~23–26 mm
# equivalent (≈ 0.64–0.72); video modes crop a little more. Only the pitch correction depends
# on it, and only weakly for the small tilts a propped-up phone has.
FOCAL_FRACTION = 0.72
MAX_TILT_DEG = 35.0  # beyond this the sensor reading is not a propped-up phone; ignore it
MAX_YAW_DEG = 30.0  # framing check: the camera must see the person from the side


@dataclass
class CameraPose:
    roll: float  # degrees; rotation of the image around the lens (positive = image turned clockwise)
    pitch: float  # degrees; positive = camera looking up
    up: tuple[float, float, float]  # unit "up" direction in camera coordinates (x right, y down, z forward)

    def as_dict(self) -> dict:
        return {"roll": round(self.roll, 2), "pitch": round(self.pitch, 2)}


def parse_gravity(header: str | None) -> tuple[float, float, float] | None:
    if not header:
        return None
    try:
        g = tuple(float(v) for v in header.split(","))
    except ValueError:
        return None
    if len(g) != 3 or not all(math.isfinite(v) for v in g) or math.hypot(*g) < 1:
        return None
    return g  # type: ignore[return-value]


def from_gravity(g: tuple[float, float, float] | None) -> CameraPose | None:
    """Camera orientation from the phone's accelerationIncludingGravity (W3C device axes:
    x = right edge of the screen, y = top edge, z = out of the screen, towards the user; at
    rest the vector points up). The front camera looks along +z and its frames are not
    mirrored, so image x = −device x and image y (down) = −device y.

    The phone is upright in portrait, so "up" must point to the top of the screen; some
    browsers report the opposite sign, which is undone here.
    """
    if g is None:
        return None
    gx, gy, gz = g
    if gy < 0:
        gx, gy, gz = -gx, -gy, -gz
    n = math.sqrt(gx * gx + gy * gy + gz * gz)
    up = (-gx / n, -gy / n, gz / n)  # camera coordinates
    roll = math.degrees(math.atan2(up[0], -up[1]))
    pitch = math.degrees(math.asin(max(-1.0, min(1.0, up[2]))))
    if abs(roll) > MAX_TILT_DEG or abs(pitch) > MAX_TILT_DEG:
        return None
    return CameraPose(roll, pitch, up)


def from_dict(d: dict | None) -> CameraPose | None:
    """Rebuild a CameraPose stored in a Sample (roll and pitch only)."""
    if not d:
        return None
    r, p = math.radians(d["roll"]), math.radians(d["pitch"])
    up = (math.sin(r) * math.cos(p), -math.cos(r) * math.cos(p), math.sin(p))
    return CameraPose(d["roll"], d["pitch"], up)


def homography(cam: CameraPose, w: int, h: int) -> np.ndarray:
    """Pixel → pixel map onto a level virtual camera with the same lens and image size."""
    f = FOCAL_FRACTION * max(w, h)
    K = np.array([[f, 0, w / 2], [0, f, h / 2], [0, 0, 1]], dtype=float)
    a = np.array(cam.up, dtype=float)
    b = np.array([0.0, -1.0, 0.0])
    v = np.cross(a, b)
    s, c = np.linalg.norm(v), float(np.dot(a, b))
    if s < 1e-9:
        R = np.eye(3)
    else:
        vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
        R = np.eye(3) + vx + vx @ vx * ((1 - c) / (s * s))  # rotation taking a onto b
    return K @ R @ np.linalg.inv(K)


def apply(H: np.ndarray, points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if not points:
        return []
    p = np.hstack([np.asarray(points, dtype=float), np.ones((len(points), 1))]) @ H.T
    return [(float(x / z), float(y / z)) for x, y, z in p]


def yaw_from_world(world: list[tuple] | None) -> float | None:
    """Angle between the camera axis and the person's left–right axis, in degrees: 0 = seen
    exactly from the side. Average of the shoulder and hip lines (MediaPipe world landmarks are
    camera-aligned: x right, y down, z away from the camera)."""
    if not world or len(world) < 25:
        return None
    vx = (world[11][0] - world[12][0] + world[23][0] - world[24][0]) / 2
    vz = (world[11][2] - world[12][2] + world[23][2] - world[24][2]) / 2
    if math.hypot(vx, vz) < 0.05:  # shoulders and hips collapsed: not a usable estimate
        return None
    return math.degrees(math.atan2(vx, abs(vz)))
