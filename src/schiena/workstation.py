"""Workstation reconstruction: image points (from Claude) → body-relative metres (pure logic).

The phone does not move during a Session, so monitor, keyboard, desk and chair are
visible in its frames. Claude marks their points on one frame (normalised image
coordinates); this module converts them into the *sagittal frame* of the body:
origin at the hip, ``x`` forward (towards the screen), ``y`` up, in metres.
"""

from __future__ import annotations

import math

from .posture import EAR, ELBOW, SHOULDER


def to_body(point: list[float], sample: dict) -> list[float]:
    x = point[0] * sample["w"]
    y = point[1] * sample["h"]
    hx, hy = sample["hip"]
    mpp = sample["mpp"]
    return [round(sample["fwd"] * (x - hx) * mpp, 3), round(-(y - hy) * mpp, 3)]


def keypoint(sample: dict, index: int) -> list[float] | None:
    kp = sample["kp"][index]
    return to_body(kp[:2], sample) if kp[2] >= 0.5 else None


def reconstruct(annotation: dict, sample: dict) -> dict:
    """annotation: {"objects": {name: {point_name: [x, y], ...}}, "notes": "..."}."""
    if not sample.get("valid") or not sample.get("mpp"):
        raise ValueError("the reference frame needs a valid Sample with a known scale")
    objects = {
        name: {pn: to_body(p, sample) for pn, p in pts.items()}
        for name, pts in annotation.get("objects", {}).items()
    }
    side = sample["side"]
    body = {
        "ear": keypoint(sample, EAR[side]),
        "shoulder": keypoint(sample, SHOULDER[side]),
        "elbow": keypoint(sample, ELBOW[side]),
        "hip": [0.0, 0.0],
    }
    return {
        "objects": objects,
        "body": body,
        "derived": derived_measures(objects, body),
        "notes": annotation.get("notes", ""),
    }


def _cm(v: float) -> float:
    return round(v * 100, 1)


def derived_measures(objects: dict, body: dict) -> dict:
    """Approximate distances that matter for ergonomics, in centimetres (± a few cm)."""
    out: dict = {}
    ear, elbow = body.get("ear"), body.get("elbow")
    for screen in ("monitor", "laptop_screen"):
        s = objects.get(screen)
        if not s or not ear or "top" not in s:
            continue
        top = s["top"]
        out[f"{screen}_top_above_eye_cm"] = _cm(top[1] - ear[1])
        if "bottom" in s:
            centre = [(top[0] + s["bottom"][0]) / 2, (top[1] + s["bottom"][1]) / 2]
            out[f"{screen}_distance_cm"] = _cm(math.dist(ear, centre))
            out[f"{screen}_centre_below_eye_deg"] = round(
                math.degrees(math.atan2(ear[1] - centre[1], max(1e-6, centre[0] - ear[0]))), 1
            )
    kb = objects.get("keyboard")
    if kb and elbow:
        pts = list(kb.values())
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        out["keyboard_above_elbow_cm"] = _cm(cy - elbow[1])
        out["keyboard_ahead_of_elbow_cm"] = _cm(cx - elbow[0])
    return out
