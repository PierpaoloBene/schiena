import math

import numpy as np
import pytest

from schiena import camera
from schiena.pose import PoseResult, level, make_sample
from schiena.posture import HIP, Landmark, measure

from .test_posture import body

W, H = 720, 1280
G = 9.81


def rotate(lms, deg, centre=(W / 2, H / 2)):
    """What a phone rolled by `deg` sees: the image turned around its centre."""
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    out = []
    for l in lms:
        x, y = l.x - centre[0], l.y - centre[1]
        out.append(Landmark(centre[0] + c * x - s * y, centre[1] + s * x + c * y, l.visibility))
    return out


def gravity_for(roll=0.0, pitch=0.0):
    """accelerationIncludingGravity (W3C axes) of a phone with that roll and pitch."""
    r, p = math.radians(roll), math.radians(pitch)
    up_cam = (math.sin(r) * math.cos(p), -math.cos(r) * math.cos(p), math.sin(p))
    return (-up_cam[0] * G, -up_cam[1] * G, up_cam[2] * G)


def test_upright_phone_is_level_whatever_the_sign_convention():
    for g in [(0.0, G, 0.0), (0.0, -G, 0.0)]:
        cam = camera.from_gravity(g)
        assert cam.roll == pytest.approx(0) and cam.pitch == pytest.approx(0)


@pytest.mark.parametrize("roll,pitch", [(6.0, 0.0), (-9.0, 4.0), (3.0, -12.0)])
def test_gravity_round_trip(roll, pitch):
    cam = camera.from_gravity(gravity_for(roll, pitch))
    assert cam.roll == pytest.approx(roll, abs=1e-6) and cam.pitch == pytest.approx(pitch, abs=1e-6)
    again = camera.from_dict(cam.as_dict())
    assert again.up == pytest.approx(cam.up, abs=1e-3)


def test_phone_lying_flat_is_ignored():
    assert camera.from_gravity((0.0, 1.0, G)) is None
    assert camera.parse_gravity("nan,1,2") is None and camera.parse_gravity("0.1,9.7,0.4") == (0.1, 9.7, 0.4)


@pytest.mark.parametrize("roll", [-8.0, 5.0])
def test_roll_is_undone(roll):
    """A phone leaning sideways would shift every angle by the roll; levelled, nothing changes."""
    straight = measure(body(trunk_deg=10, neck_deg=20))
    tilted_lms = rotate(body(trunk_deg=10, neck_deg=20), roll)
    assert abs(measure(tilted_lms).metrics["trunk"] - 10) > 4  # uncorrected: off by the roll
    cam = camera.from_dict({"roll": roll, "pitch": 0.0})
    lms, _, _ = level(PoseResult(tilted_lms, None, None), W, H, cam)
    fixed = measure(lms)
    for k in ("trunk", "neck", "head_offset", "upper_arm", "elbow", "knee"):
        assert fixed.metrics[k] == pytest.approx(straight.metrics[k], abs=1e-6), k


def test_pitch_makes_verticals_vertical_again():
    """A camera looking up 10°: a vertical pole off-centre leans in the image; levelled, it doesn't."""
    f = camera.FOCAL_FRACTION * max(W, H)
    K = np.array([[f, 0, W / 2], [0, f, H / 2], [0, 0, 1]])
    p = math.radians(10)
    # world (x right, y down, z forward) → camera tilted up by p (rotation about x)
    R = np.array([[1, 0, 0], [0, math.cos(p), math.sin(p)], [0, -math.sin(p), math.cos(p)]])
    pole = [np.array([0.6, y, 2.0]) for y in (-0.8, 0.8)]
    img = [(K @ (R @ P)) for P in pole]
    pts = [(v[0] / v[2], v[1] / v[2]) for v in img]
    assert abs(pts[0][0] - pts[1][0]) > 10  # leaning in the tilted image
    cam = camera.from_dict({"roll": 0.0, "pitch": 10.0})
    fixed = camera.apply(camera.homography(cam, W, H), pts)
    assert fixed[0][0] == pytest.approx(fixed[1][0], abs=1e-6)


def test_samples_keep_frame_coordinates_and_record_the_camera():
    tilted = rotate(body(), 6.0)
    s = make_sample(0, PoseResult(tilted, None, None), W, H, cam=camera.from_dict({"roll": 6.0, "pitch": 0.0}))
    assert s["camera"] == {"roll": 6.0, "pitch": 0.0}
    assert s["metrics"]["trunk"] == pytest.approx(10.0, abs=1e-6)
    hip = tilted[HIP["right"]]
    assert s["hip"] == [round(hip.x, 1), round(hip.y, 1)]  # drawn on the original frame


def world(yaw_deg):
    """World landmarks of someone seen from the side, turned by yaw_deg."""
    w = [(0.0, 0.0, 0.0)] * 33
    y = math.radians(yaw_deg)
    left = (0.18 * math.sin(y), 0.0, -0.18 * math.cos(y))  # left side towards the camera
    for li, ri, h in ((11, 12, -0.5), (23, 24, 0.0)):
        w[li] = (left[0], h, left[2])
        w[ri] = (-left[0], h, -left[2])
    return w


@pytest.mark.parametrize("yaw", [0.0, 12.0, -25.0])
def test_yaw_from_world_landmarks(yaw):
    assert camera.yaw_from_world(world(yaw)) == pytest.approx(yaw, abs=1e-6)
