"""Per-frame posture measurement from pose landmarks (pure logic, no I/O).

Coordinates are image pixels with y pointing down. The person is filmed from the
side; the *facing side* is the body side closer to the camera. Every angle is
signed so that positive means "forward" (towards where the person is looking).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

VISIBLE = 0.5

NOSE = 0
EAR = {"left": 7, "right": 8}
SHOULDER = {"left": 11, "right": 12}
ELBOW = {"left": 13, "right": 14}
WRIST = {"left": 15, "right": 16}
HIP = {"left": 23, "right": 24}
KNEE = {"left": 25, "right": 26}
ANKLE = {"left": 27, "right": 28}

METRICS = (
    "trunk",       # hip→shoulder from vertical, degrees
    "neck",        # shoulder→ear from vertical, degrees
    "head_offset", # ear ahead of shoulder, in trunk lengths
    "upper_back",  # upper half of the back contour from vertical, degrees
    "lower_back",  # lower half of the back contour from vertical, degrees
    "back_rounding",  # upper_back − lower_back, degrees (positive = hunched)
    "upper_arm",   # shoulder→elbow from vertical, degrees (positive = elbow forward)
    "elbow",       # interior angle shoulder-elbow-wrist
    "hip",         # interior angle shoulder-hip-knee
    "knee",        # interior angle hip-knee-ankle
)


@dataclass(frozen=True)
class Landmark:
    x: float
    y: float
    visibility: float

    @property
    def visible(self) -> bool:
        return self.visibility >= VISIBLE


@dataclass
class Measurement:
    """One analysed frame."""

    person: bool
    valid: bool = False
    side: str | None = None
    forward: int = 1  # +1 if the person looks towards +x in the image, else −1
    trunk_length: float | None = None  # pixels
    hip: tuple[float, float] | None = None  # pixels
    metrics: dict[str, float | None] = field(default_factory=dict)
    back_contour: list[tuple[float, float]] = field(default_factory=list)  # pixels


def facing_side(lms: Sequence[Landmark]) -> str:
    def score(side: str) -> float:
        return sum(lms[i[side]].visibility for i in (EAR, SHOULDER, HIP, KNEE))

    return "left" if score("left") > score("right") else "right"


def forward_sign(lms: Sequence[Landmark], side: str) -> int:
    nose, ear = lms[NOSE], lms[EAR[side]]
    if nose.visible and ear.visible and abs(nose.x - ear.x) > 1e-6:
        return 1 if nose.x > ear.x else -1
    hip, knee = lms[HIP[side]], lms[KNEE[side]]
    return 1 if knee.x >= hip.x else -1


def angle_from_vertical(lower: tuple[float, float], upper: tuple[float, float], fwd: int) -> float:
    """Angle of the segment lower→upper from the upward vertical; positive = forward."""
    dx = (upper[0] - lower[0]) * fwd
    dy = lower[1] - upper[1]
    return math.degrees(math.atan2(dx, dy))


def angle_from_down(top: tuple[float, float], bottom: tuple[float, float], fwd: int) -> float:
    """Angle of the segment top→bottom from the downward vertical; positive = forward."""
    dx = (bottom[0] - top[0]) * fwd
    dy = bottom[1] - top[1]
    return math.degrees(math.atan2(dx, dy))


def interior_angle(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
    v1 = (a[0] - b[0], a[1] - b[1])
    v2 = (c[0] - b[0], c[1] - b[1])
    n = math.hypot(*v1) * math.hypot(*v2)
    if n == 0:
        return float("nan")
    cos = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / n))
    return math.degrees(math.acos(cos))


def back_contour(
    mask: np.ndarray,
    shoulder: tuple[float, float],
    hip: tuple[float, float],
    fwd: int,
    rows: int = 13,
) -> list[tuple[float, float]]:
    """Back edge of the person's silhouette between shoulder and hip.

    For each row the edge is the farthest person pixel *behind* the shoulder–hip
    line, searched within one trunk length of it. Rows with no edge are skipped.
    """
    h, w = mask.shape[:2]
    trunk = math.dist(shoulder, hip)
    points: list[tuple[float, float]] = []
    for k in range(rows):
        f = 0.05 + 0.9 * k / (rows - 1)
        y = shoulder[1] + (hip[1] - shoulder[1]) * f
        line_x = shoulder[0] + (hip[0] - shoulder[0]) * f
        yi = int(round(y))
        if not 0 <= yi < h:
            continue
        lo = int(max(0, min(w - 1, line_x - fwd * trunk)))
        hi = int(max(0, min(w - 1, line_x)))
        a, b = sorted((lo, hi))
        row = mask[yi, a : b + 1] > 0.5
        idx = np.flatnonzero(row)
        if idx.size == 0:
            continue
        # behind = opposite to forward: the smallest x when facing +x.
        x = a + (idx[0] if fwd > 0 else idx[-1])
        # The edge must be connected to the body: require person pixels up to the line.
        if not row[(idx[0] if fwd > 0 else 0) : (len(row) if fwd > 0 else idx[-1] + 1)].mean() > 0.6:
            continue
        points.append((float(x), float(y)))
    return points


def back_angles(contour: list[tuple[float, float]], fwd: int) -> tuple[float, float] | None:
    """(upper_back, lower_back) angles from vertical, from the contour's thirds."""
    if len(contour) < 7:
        return None
    pts = np.array(contour)
    n = len(pts)
    top = pts[: max(2, n // 4)].mean(axis=0)
    mid = pts[n // 2 - 1 : n // 2 + 2].mean(axis=0)
    bottom = pts[-max(2, n // 4) :].mean(axis=0)
    upper = angle_from_vertical(tuple(mid), tuple(top), fwd)
    lower = angle_from_vertical(tuple(bottom), tuple(mid), fwd)
    return upper, lower


def measure(lms: Sequence[Landmark] | None, mask: np.ndarray | None = None) -> Measurement:
    if not lms:
        return Measurement(person=False)
    side = facing_side(lms)
    fwd = forward_sign(lms, side)
    ear, sh, el, wr = (lms[i[side]] for i in (EAR, SHOULDER, ELBOW, WRIST))
    hp, kn, an = (lms[i[side]] for i in (HIP, KNEE, ANKLE))
    p = lambda lm: (lm.x, lm.y)  # noqa: E731

    m: dict[str, float | None] = {k: None for k in METRICS}
    out = Measurement(person=True, side=side, forward=fwd, metrics=m)
    if not (sh.visible and hp.visible):
        return out
    trunk_len = math.dist(p(sh), p(hp))
    if trunk_len < 1:
        return out
    out.trunk_length = trunk_len
    out.hip = p(hp)
    out.valid = ear.visible
    m["trunk"] = angle_from_vertical(p(hp), p(sh), fwd)
    if ear.visible:
        m["neck"] = angle_from_vertical(p(sh), p(ear), fwd)
        m["head_offset"] = (ear.x - sh.x) * fwd / trunk_len
    if el.visible:
        m["upper_arm"] = angle_from_down(p(sh), p(el), fwd)
        if wr.visible:
            m["elbow"] = interior_angle(p(sh), p(el), p(wr))
    if kn.visible:
        m["hip"] = interior_angle(p(sh), p(hp), p(kn))
        if an.visible:
            m["knee"] = interior_angle(p(hp), p(kn), p(an))
    if mask is not None:
        contour = back_contour(mask, p(sh), p(hp), fwd)
        out.back_contour = contour
        angles = back_angles(contour, fwd)
        if angles:
            m["upper_back"], m["lower_back"] = angles
            m["back_rounding"] = angles[0] - angles[1]
    return out
