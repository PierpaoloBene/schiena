"""Personal calibration (pure logic): height and relaxed standing reference photos.

- **Height** gives the image a real scale. With a side standing photo the tool measures the
  user's own trunk length (shoulder→hip landmarks, in metres); otherwise it assumes the
  average ratio TRUNK_TO_HEIGHT.
- **Side standing photo** is the user's *neutral* posture: seated Metrics are reported as a
  difference from it. The pose model's biases (e.g. shoulder placed towards the back) are
  partly shared by both, so the difference is more meaningful than an absolute angle.
- **Front standing photo** is context only (shoulder/hip line, lateral shift). Never a diagnosis.
"""

from __future__ import annotations

import math

import numpy as np

from .posture import ANKLE, EAR, HIP, SHOULDER, Landmark, measure

TRUNK_TO_HEIGHT = 0.29  # shoulder→hip landmark distance / body height, average adult
NEUTRAL_METRICS = ("neck", "head_offset", "trunk", "upper_back", "lower_back", "back_rounding")


def silhouette_height_px(mask: np.ndarray | None, lms: list[Landmark]) -> float | None:
    """Top of the head (mask) to the floor contact (lowest of mask and foot landmarks)."""
    if mask is None:
        return None
    rows = np.flatnonzero((mask > 0.5).any(axis=1))
    if rows.size == 0:
        return None
    feet = [lms[i].y for i in (27, 28, 29, 30, 31, 32) if lms[i].visible]
    bottom = max([float(rows[-1])] + feet)
    return bottom - float(rows[0])


def analyse_side(lms: list[Landmark] | None, mask: np.ndarray | None, w: int, h: int) -> dict:
    if not lms:
        return {"ok": False, "problems": ["No one in the photo — stand where the camera can see you."]}
    m = measure(lms, mask)
    side = m.side
    problems = []
    if not m.valid:
        problems.append("Ear, shoulder and hip must be visible.")
    if not lms[ANKLE[side]].visible:
        problems.append("Your feet are cut off — step back until the whole body is in the picture.")
    ls, rs = lms[SHOULDER["left"]], lms[SHOULDER["right"]]
    if m.trunk_length and abs(ls.x - rs.x) / m.trunk_length > 0.35:
        problems.append("Turn sideways so the camera sees you exactly in profile.")
    height_px = silhouette_height_px(mask, lms)
    if height_px is None:
        problems.append("Could not find your silhouette — try with more light.")
    if problems:
        return {"ok": False, "problems": problems}
    return {
        "ok": True,
        "problems": [],
        "side": side,
        "trunk_px": round(m.trunk_length, 1),
        "height_px": round(height_px, 1),
        "metrics": {k: (round(v, 3) if v is not None else None) for k, v in m.metrics.items() if k in NEUTRAL_METRICS},
        "kp": [[round(l.x / w, 4), round(l.y / h, 4), round(l.visibility, 2)] for l in lms],
        "back": [[round(x / w, 4), round(y / h, 4)] for x, y in m.back_contour],
        "w": w,
        "h": h,
    }


def _tilt(a: Landmark, b: Landmark) -> float:
    """Angle of the line a–b from horizontal, degrees; positive = the image-right point is higher."""
    left, right = (a, b) if a.x < b.x else (b, a)
    return math.degrees(math.atan2(left.y - right.y, right.x - left.x))


def analyse_front(lms: list[Landmark] | None, w: int, h: int) -> dict:
    if not lms:
        return {"ok": False, "problems": ["No one in the photo — stand facing the camera."]}
    pts = [lms[i[s]] for i in (SHOULDER, HIP) for s in ("left", "right")]
    if not all(p.visible for p in pts):
        return {"ok": False, "problems": ["Shoulders and hips must be visible — step back."]}
    ls, rs, lh, rh = pts
    shoulder_w = abs(ls.x - rs.x)
    trunk = math.dist(((ls.x + rs.x) / 2, (ls.y + rs.y) / 2), ((lh.x + rh.x) / 2, (lh.y + rh.y) / 2))
    if shoulder_w < 0.5 * trunk:
        return {"ok": False, "problems": ["Face the camera straight on."]}
    out = {
        "ok": True,
        "problems": [],
        "shoulder_line_deg": round(_tilt(ls, rs), 1),
        "hip_line_deg": round(_tilt(lh, rh), 1),
        "lateral_shift": round(((ls.x + rs.x) / 2 - (lh.x + rh.x) / 2) / trunk, 3),
        "kp": [[round(l.x / w, 4), round(l.y / h, 4), round(l.visibility, 2)] for l in lms],
        "w": w,
        "h": h,
    }
    le, re = lms[EAR["left"]], lms[EAR["right"]]
    if le.visible and re.visible:
        out["head_tilt_deg"] = round(_tilt(le, re), 1)
    return out


def trunk_metres(profile: dict | None) -> float | None:
    """The user's shoulder→hip landmark distance in metres, if calibrated."""
    if not profile or not profile.get("height_cm"):
        return None
    height_m = profile["height_cm"] / 100
    side = profile.get("standing_side")
    if side and side.get("ok"):
        return height_m * side["trunk_px"] / side["height_px"]
    return height_m * TRUNK_TO_HEIGHT


def neutral(profile: dict | None) -> dict | None:
    side = (profile or {}).get("standing_side")
    return side["metrics"] if side and side.get("ok") else None


def versus_neutral(summary: dict, profile: dict | None) -> dict | None:
    """Seated median − standing neutral, per Metric."""
    ref = neutral(profile)
    if not ref:
        return None
    out = {}
    for k, v in ref.items():
        med = (summary["metrics"].get(k) or {}).get("median")
        if v is not None and med is not None:
            out[k] = round(med - v, 3)
    return out
