import pytest

from schiena.workstation import reconstruct


def ref_sample():
    kp = [[0, 0, 0.1] for _ in range(33)]
    kp[8] = [0.55, 0.30, 0.9]   # right ear
    kp[12] = [0.50, 0.40, 0.9]  # right shoulder
    kp[14] = [0.52, 0.55, 0.9]  # right elbow
    return {"valid": True, "side": "right", "fwd": 1, "w": 1000, "h": 1000,
            "hip": [500.0, 700.0], "mpp": 0.002, "kp": kp}


def test_points_become_body_relative_metres():
    ws = reconstruct({"objects": {"monitor": {"top": [0.85, 0.28], "bottom": [0.85, 0.48]}}}, ref_sample())
    assert ws["objects"]["monitor"]["top"] == [0.7, 0.84]
    assert ws["body"]["ear"] == [0.1, 0.8]
    assert ws["derived"]["monitor_top_above_eye_cm"] == pytest.approx(4.0)
    assert ws["derived"]["monitor_distance_cm"] == pytest.approx(62.1, abs=0.1)


def test_facing_left_flips_forward():
    s = ref_sample()
    s["fwd"] = -1
    ws = reconstruct({"objects": {"keyboard": {"centre": [0.3, 0.6]}}}, s)
    assert ws["objects"]["keyboard"]["centre"] == [0.4, 0.2]


def test_reference_needs_scale():
    s = ref_sample()
    s["mpp"] = None
    with pytest.raises(ValueError):
        reconstruct({"objects": {}}, s)
