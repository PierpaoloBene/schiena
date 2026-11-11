import pytest
from schiena.history import COMFORT_ONLY, INCONCLUSIVE, SUCCESSFUL, evaluate, plateau
from schiena.session import FramingGate, check_framing, comparability, find_absences, longest_still_period, summarize


def sample(t, person=True, valid=True, hip_y=900.0, trunk=8.0, neck=20.0, head=0.2):
    if not person:
        return {"t": t, "person": False, "valid": False, "w": 720, "h": 1280}
    kp = [[0.5, 0.5, 0.1] for _ in range(33)]
    kp[11] = [0.55, 0.45, 0.9]
    kp[12] = [0.56, 0.45, 0.9]
    return {
        "t": t, "person": True, "valid": valid, "w": 720, "h": 1280, "side": "right", "fwd": 1,
        "trunk_len": 300.0, "hip": [400.0, hip_y], "kp": kp,
        "metrics": {"trunk": trunk, "neck": neck, "head_offset": head},
    }


def test_short_gaps_are_not_absences():
    s = [sample(t) for t in range(60)]
    for t in range(10, 14):
        s[t] = sample(t, person=False)
    assert find_absences(s) == []


def test_out_of_frame_absence():
    s = [sample(t) for t in range(120)]
    for t in range(30, 50):
        s[t] = sample(t, person=False)
    assert find_absences(s) == [(30, 50)]


def test_standing_is_absence():
    s = [sample(t) for t in range(120)]
    for t in range(60, 80):
        s[t] = sample(t, hip_y=900 - 200)  # hip rises 2/3 of a trunk length
    assert find_absences(s) == [(60, 80)]


def test_absences_close_together_are_merged():
    s = [sample(t) for t in range(120)]
    for t in list(range(20, 30)) + list(range(32, 42)):
        s[t] = sample(t, person=False)
    assert find_absences(s) == [(20, 42)]


def test_acceptance():
    s = [sample(t) for t in range(25 * 60)]
    summ = summarize(s, "2026-11-11T10:00:00")
    assert summ["accepted"] and summ["valid_percent"] == 100.0
    assert summ["metrics"]["trunk"]["median"] == 8.0
    short = summarize(s[: 15 * 60], "2026-11-11T10:00:00")
    assert not short["accepted"]


def test_invalid_samples_count_against_acceptance():
    s = [sample(t, valid=(t % 4 != 0)) for t in range(25 * 60)]
    assert not summarize(s, "2026-11-11T10:00:00")["accepted"]  # 75% valid


def test_absence_is_excluded_not_invalid():
    s = [sample(t) for t in range(30 * 60)]
    for t in range(100, 300):
        s[t] = sample(t, person=False)
    summ = summarize(s, "2026-11-11T10:00:00")
    assert summ["valid_percent"] == 100.0
    assert summ["presence_s"] == 30 * 60 - 200


def test_still_period():
    s = [sample(t, trunk=8 + (0 if t < 600 else 10)) for t in range(900)]
    assert longest_still_period(s) == 599


def test_framing():
    ok = check_framing(sample(0))
    assert ok.ok, ok.problems
    small = sample(0)
    small["trunk_len"] = 100
    assert not check_framing(small).ok
    frontal = sample(0)
    frontal["kp"][11] = [0.35, 0.45, 0.9]
    assert "side" in check_framing(frontal).problems[0]
    gate = FramingGate(5)
    assert gate.update(0, ok) == 0
    assert gate.update(5, ok) == 1
    assert gate.update(6, check_framing(sample(6, person=False))) == 0


def summ(trunk=8.0, head=0.2, scale=0.23, band_hour=10):
    s = [sample(t, trunk=trunk, head=head) for t in range(25 * 60)]
    out = summarize(s, f"2026-11-11T{band_hour:02d}:00:00")
    out["placement"]["body_scale"] = scale
    return out


def test_comparability():
    assert comparability(summ(), summ()) == []
    assert comparability(summ(), summ(scale=0.30)) == []  # the phone moved closer: angles don't change
    assert "time of day" in comparability(summ(), summ(band_hour=15))[0]
    a, b = summ(), summ()
    a["placement"]["yaw"], b["placement"]["yaw"] = 5.0, 12.0
    assert comparability(a, b) == []
    b["placement"]["yaw"] = 28.0
    assert "different angle" in comparability(a, b)[0]


def test_outcome_successful():
    r = evaluate([summ(head=0.20), summ(head=0.23)], summ(head=0.12),
                 [{"metric": "head_offset", "direction": "decrease"}], [{"neck": 4}, {"neck": 4}], {"neck": 3})
    assert r["outcome"] == SUCCESSFUL
    assert r["metrics"][0]["reference_variability"] == 0.03


def test_outcome_within_reference_variability_is_inconclusive():
    r = evaluate([summ(head=0.20), summ(head=0.26)], summ(head=0.17),
                 [{"metric": "head_offset", "direction": "decrease"}], [{}, {}], {})
    assert r["outcome"] == INCONCLUSIVE and r["probable_cause"] == "no measurable effect"


def test_outcome_worse_comfort_wins():
    r = evaluate([summ(head=0.20), summ(head=0.21)], summ(head=0.10),
                 [{"metric": "head_offset", "direction": "decrease"}], [{"neck": 2}, {"neck": 2}], {"neck": 5})
    assert r["outcome"] == INCONCLUSIVE and r["probable_cause"] == "worse comfort"


def test_outcome_comfort_only():
    r = evaluate([summ(), summ()], summ(),
                 [{"metric": "trunk", "direction": "decrease"}], [{"lower_back": 5}, {"lower_back": 5}], {"lower_back": 2})
    assert r["outcome"] == COMFORT_ONLY


def test_single_baseline_reuses_reference_variability():
    r = evaluate([summ(head=0.20)], summ(head=0.15), [{"metric": "head_offset", "direction": "decrease"}],
                 [{}], {}, reference={"head_offset": 0.03})
    assert r["outcome"] == SUCCESSFUL


def test_plateau_after_three_inconclusive():
    assert plateau([{"outcome": INCONCLUSIVE}] * 3)
    assert not plateau([{"outcome": INCONCLUSIVE}, {"outcome": SUCCESSFUL}, {"outcome": INCONCLUSIVE}])


def test_interruption_is_neither_presence_nor_absence():
    s = [sample(t) for t in range(30 * 60) if not 600 <= t < 900]  # phone offline for 5 min
    summ = summarize(s, "2026-11-11T10:00:00", 30 * 60)
    assert summ["interruptions"] == [{"start_s": 600.0, "end_s": 900.0}]
    assert summ["absences"] == []
    assert summ["presence_s"] == 25 * 60
    assert summ["accepted"]


def test_phone_dead_before_the_end():
    s = [sample(t) for t in range(15 * 60)]
    summ = summarize(s, "2026-11-11T10:00:00", 30 * 60)
    assert summ["interrupted_s"] == 15 * 60 and not summ["accepted"]


def test_out_of_order_samples_are_sorted():
    s = [sample(t) for t in range(60)]
    summ = summarize(list(reversed(s)), "2026-11-11T10:00:00", 60)
    assert summ["interruptions"] == [] and summ["presence_s"] == 60


def drifting(head_by_minute, minutes=25):
    """Samples whose head_offset changes from minute to minute (constant within a minute)."""
    s = [sample(t, head=head_by_minute(t // 60)) for t in range(minutes * 60)]
    return summarize(s, "2026-11-11T10:00:00")


def test_median_standard_error():
    steady = summ()
    assert steady["metrics"]["head_offset"]["median_se"] == 0
    wobbly = drifting(lambda m: 0.20 + (0.06 if m % 2 else -0.06))
    assert wobbly["metrics"]["head_offset"]["median_se"] > 0.015


def test_noisy_sessions_raise_the_threshold():
    """A 0.08 drop beats the day-to-day difference (0.03) but not the minute-to-minute noise."""
    wobble = lambda centre: drifting(lambda m: centre + (0.15 if m % 2 else -0.15))
    r = evaluate([wobble(0.20), wobble(0.23)], wobble(0.135),
                 [{"metric": "head_offset", "direction": "decrease"}], [{}, {}], {})
    m = r["metrics"][0]
    assert m["threshold"]["deciding"] == "measurement_noise"
    assert m["reference_variability"] > abs(m["change"])
    assert r["outcome"] == INCONCLUSIVE
    assert r["reference_variability"]["head_offset"] == 0.03  # what is reused is the day-to-day part


def test_three_baselines_all_count():
    """√2 × SD of all Baselines: one odd day weighs less than in a two-Baseline range."""
    r = evaluate([summ(head=0.20), summ(head=0.21), summ(head=0.26)], summ(head=0.15),
                 [{"metric": "head_offset", "direction": "decrease"}], [{}, {}, {}], {})
    m = r["metrics"][0]
    assert m["threshold"]["deciding"] == "day_to_day"
    assert 0.04 < m["reference_variability"] < 0.06  # range would be 0.06
    assert r["outcome"] == SUCCESSFUL


def test_exposure_bands_and_longest_stretch():
    from schiena.session import exposure

    # 10 min at neck 15°, 5 min at 40°, a 4 s gap (interruption), 3 min at 40°, 2 min at 90°
    s = [sample(t, neck=15.0) for t in range(600)]
    s += [sample(t, neck=40.0) for t in range(600, 900)]
    s += [sample(t, neck=40.0) for t in range(904, 1084)]
    s += [sample(t, neck=90.0) for t in range(1084, 1204)]
    e = exposure(s, "neck", (25.0, 85.0))
    assert e["below_percent"] == pytest.approx(100 * 600 / 1200, abs=0.1)
    assert e["between_percent"] == pytest.approx(100 * 480 / 1200, abs=0.1)
    assert e["above_percent"] == pytest.approx(100 * 120 / 1200, abs=0.1)
    assert e["longest_over_first_limit_s"] == 300  # the gap breaks the stretch; 180 s + 120 s after it
    assert exposure([sample(t, neck=10.0) for t in range(60)], "neck", (25.0, 85.0))["longest_over_first_limit_s"] == 0
    # a 3 s dip below the limit doesn't end the stretch, a 10 s one does
    dip = [sample(t, neck=10.0 if 100 <= t < 103 else 40.0) for t in range(200)]
    assert exposure(dip, "neck", (25.0, 85.0))["longest_over_first_limit_s"] == 200
    dip = [sample(t, neck=10.0 if 100 <= t < 110 else 40.0) for t in range(200)]
    assert exposure(dip, "neck", (25.0, 85.0))["longest_over_first_limit_s"] == 100
