import numpy as np
import pytest

from schiena.calibration import TRUNK_TO_HEIGHT, analyse_front, analyse_side, trunk_metres, versus_neutral
from schiena.posture import Landmark

from .test_posture import body


def standing_mask(top=100, bottom=1900):
    m = np.zeros((2000, 1000), np.float32)
    m[top:bottom, 300:700] = 1
    return m


def profile_view(lms):
    """The far side is hidden but estimated right next to the near side, as MediaPipe does."""
    for left, right in ((7, 8), (11, 12), (13, 14), (15, 16), (23, 24), (25, 26), (27, 28)):
        lms[left] = Landmark(lms[right].x + 5, lms[right].y, 0.3)
    return lms


def test_side_photo_measures_neutral_and_body_proportions():
    lms = profile_view(body(trunk_deg=0, neck_deg=10))
    r = analyse_side(lms, standing_mask(), 1000, 2000)
    assert r["ok"], r["problems"]
    assert r["trunk_px"] == 300 and r["height_px"] == 1799
    assert r["metrics"]["neck"] == pytest.approx(10, abs=1e-3)


def test_side_photo_needs_feet():
    lms = profile_view(body())
    lms[28] = Landmark(0, 0, 0.1)
    assert "feet" in analyse_side(lms, standing_mask(), 1000, 2000)["problems"][0]


def test_trunk_metres_from_photo_or_average():
    assert trunk_metres({"height_cm": 180}) == pytest.approx(1.8 * TRUNK_TO_HEIGHT)
    p = {"height_cm": 180, "standing_side": {"ok": True, "trunk_px": 300, "height_px": 1800}}
    assert trunk_metres(p) == pytest.approx(0.3)
    assert trunk_metres({}) is None


def test_seated_versus_neutral():
    p = {"standing_side": {"ok": True, "metrics": {"neck": 12.0, "trunk": 2.0}}}
    s = {"metrics": {"neck": {"median": 40.0}, "trunk": {"median": 5.0}}}
    assert versus_neutral(s, p) == {"neck": 28.0, "trunk": 3.0}


def test_front_photo_lines():
    lms = [Landmark(0, 0, 0.1) for _ in range(33)]
    for i, (x, y) in {11: (600, 500), 12: (400, 510), 23: (560, 800), 24: (440, 800), 7: (540, 380), 8: (460, 380)}.items():
        lms[i] = Landmark(x, y, 0.9)
    r = analyse_front(lms, 1000, 1000)
    assert r["ok"]
    assert r["shoulder_line_deg"] == pytest.approx(2.9, abs=0.05)  # image-right shoulder higher
    assert r["hip_line_deg"] == 0 and r["head_tilt_deg"] == 0
