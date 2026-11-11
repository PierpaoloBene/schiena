import math

import numpy as np
import pytest

from schiena.posture import EAR, ELBOW, HIP, KNEE, ANKLE, NOSE, SHOULDER, WRIST, Landmark, back_contour, measure


def body(fwd=1, trunk_deg=10.0, neck_deg=20.0, side="right", vis=0.99):
    """Synthetic seated person facing +x (fwd=1) or −x, hip at (500, 800), trunk 300 px."""
    lms = [Landmark(0, 0, 0.1) for _ in range(33)]
    hip = (500.0, 800.0)
    t = math.radians(trunk_deg)
    sh = (hip[0] + fwd * 300 * math.sin(t), hip[1] - 300 * math.cos(t))
    n = math.radians(neck_deg)
    ear = (sh[0] + fwd * 120 * math.sin(n), sh[1] - 120 * math.cos(n))
    pts = [
        (EAR, ear),
        (SHOULDER, sh),
        (ELBOW, (sh[0] + fwd * 60, sh[1] + 200)),
        (WRIST, (sh[0] + fwd * 260, sh[1] + 200)),
        (HIP, hip),
        (KNEE, (hip[0] + fwd * 300, hip[1])),
        (ANKLE, (hip[0] + fwd * 300, hip[1] + 300)),
    ]
    for idx, p in pts:
        lms[idx[side]] = Landmark(p[0], p[1], vis)
    lms[NOSE] = Landmark(ear[0] + fwd * 80, ear[1] + 10, vis)
    return lms


@pytest.mark.parametrize("fwd", [1, -1])
def test_angles_are_signed_forward_regardless_of_direction(fwd):
    m = measure(body(fwd=fwd))
    assert m.valid and m.forward == fwd
    assert m.metrics["trunk"] == pytest.approx(10.0, abs=1e-6)
    assert m.metrics["neck"] == pytest.approx(20.0, abs=1e-6)
    assert m.metrics["head_offset"] == pytest.approx(120 * math.sin(math.radians(20)) / 300, abs=1e-6)
    assert m.metrics["knee"] == pytest.approx(90.0, abs=1e-6)
    assert m.metrics["elbow"] == pytest.approx(90 + math.degrees(math.atan2(60, 200)), abs=1e-6)
    assert m.metrics["upper_arm"] == pytest.approx(math.degrees(math.atan2(60, 200)), abs=1e-6)


def test_reclined_trunk_is_negative():
    assert measure(body(trunk_deg=-12)).metrics["trunk"] == pytest.approx(-12, abs=1e-6)


def test_left_side_is_detected():
    m = measure(body(side="left"))
    assert m.side == "left" and m.valid


def test_occluded_knee_is_not_estimated():
    lms = body()
    lms[KNEE["right"]] = Landmark(lms[KNEE["right"]].x, lms[KNEE["right"]].y, 0.2)
    m = measure(lms)
    assert m.metrics["knee"] is None and m.metrics["hip"] is None
    assert m.valid


def test_no_person():
    assert not measure(None).person


def test_missing_ear_makes_sample_invalid_but_keeps_trunk():
    lms = body()
    lms[EAR["right"]] = Landmark(0, 0, 0.1)
    m = measure(lms)
    assert not m.valid and m.metrics["trunk"] is not None and m.metrics["neck"] is None


def silhouette(fwd=1, rounding_px=0.0):
    """Mask of a back: vertical back at x=400 (facing +x); a hunch bulges backwards mid-back."""
    mask = np.zeros((1000, 1000), np.float32)
    for y in range(500, 801):
        f = (y - 500) / 300  # 0 at shoulder, 1 at hip
        bulge = rounding_px * (1 - abs(2 * f - 1))
        edge = 400 - bulge
        if fwd > 0:
            mask[y, int(edge) : 700] = 1
        else:
            mask[y, 300 : int(1000 - edge)] = 1
    return mask


def test_back_profile_straight_back():
    lms = body(trunk_deg=0)
    # shoulder (500,500) hip (500,800); back edge 100 px behind
    m = measure(lms, silhouette())
    assert len(m.back_contour) >= 10
    assert m.metrics["upper_back"] == pytest.approx(0, abs=1.0)
    assert m.metrics["lower_back"] == pytest.approx(0, abs=1.0)


def test_back_profile_detects_rounded_upper_back():
    m = measure(body(trunk_deg=0), silhouette(rounding_px=60))
    assert m.metrics["back_rounding"] > 10
    assert m.metrics["upper_back"] > 10


def test_back_contour_mirrored():
    mask = silhouette(fwd=-1)
    pts = back_contour(mask, (500, 500), (500, 800), fwd=-1)
    assert pts and all(abs(x - 599) <= 1 for x, _ in pts)
