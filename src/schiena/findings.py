"""Deterministic Findings from a Session summary: what was measured, with its justification.

These are observations, not diagnoses. Thresholds are either about measurement
quality or relative (drift within the Session); the external references are
OSHA's elbow range (90–120°) and the static posture bands of ISO 11226, both used as
reference points for how time is spent, not as verdicts.
"""

from __future__ import annotations

LABELS = {
    "trunk": "trunk inclination",
    "neck": "neck angle",
    "head_offset": "head forward offset",
    "upper_back": "upper back",
    "lower_back": "lower back",
    "back_rounding": "back rounding",
    "upper_arm": "upper arm",
    "elbow": "elbow angle",
    "hip": "hip angle",
    "knee": "knee angle",
}


def findings(summary: dict) -> list[dict]:
    out: list[dict] = []
    m = summary["metrics"]

    def add(fid, text, confidence, evidence):
        out.append({"id": fid, "text": text, "confidence": confidence, "evidence": evidence})

    for k, label in LABELS.items():
        vis = m.get(k, {}).get("visible_percent", 0)
        if vis < 50:
            add(f"{k}_not_visible", f"{label} not visible enough to measure", "high", f"visible in {vis}% of valid Samples")

    head = m.get("head_offset", {})
    if "median" in head:
        drift = head["last_third_median"] - head["first_third_median"]
        if drift > 0.05:
            add("head_forward_drift", "the head moves forward as the Session goes on", "medium",
                f"head offset {head['first_third_median']:.2f} → {head['last_third_median']:.2f} trunk lengths (first vs last third)")
    for k, thr in (("trunk", 4.0), ("back_rounding", 6.0)):
        x = m.get(k, {})
        if "median" in x:
            drift = x["last_third_median"] - x["first_third_median"]
            if abs(drift) > thr:
                direction = "increases" if drift > 0 else "decreases"
                add(f"{k}_drift", f"{LABELS[k]} {direction} during the Session", "medium",
                    f"{x['first_third_median']:.1f}° → {x['last_third_median']:.1f}° (first vs last third)")

    still = summary.get("longest_still_s", 0)
    if still >= 15 * 60:
        add("long_stillness", "one posture held for a long time", "high",
            f"trunk and neck stayed within 5° for {still / 60:.0f} min in a row")
    if summary["presence_s"] >= 25 * 60 and not summary["absences"]:
        add("no_breaks", "no break away from the desk", "high", f"{summary['presence_s'] / 60:.0f} min seated without an Absence")

    for k, what in (("neck", "head tilted forward"), ("trunk", "trunk leaning forward"), ("upper_arm", "arms raised forward")):
        e = m.get(k, {}).get("exposure")
        if not e:
            continue
        over = e["between_percent"] + e["above_percent"]
        lo = e["limits"][0]
        if over >= 50 or e["longest_over_first_limit_s"] >= 10 * 60:
            add(f"{k}_sustained", f"{what} beyond {lo:.0f}° for much of the Session", "medium",
                f"{over:.0f}% of measured time over {lo:.0f}° (ISO 11226 band), longest unbroken stretch "
                f"{e['longest_over_first_limit_s'] / 60:.0f} min; angles are approximate")

    trunk = m.get("trunk", {})
    if trunk.get("minute_std") is not None and trunk["minute_std"] < 1.0:
        add("low_trunk_variability", "very little trunk movement", "medium",
            f"median per-minute standard deviation {trunk['minute_std']}°")

    elbow = m.get("elbow", {})
    if "median" in elbow and elbow.get("visible_percent", 0) >= 50:
        if elbow["median"] > 120:
            add("elbow_open", "arms reaching forward (elbow open)", "medium",
                f"median elbow angle {elbow['median']:.0f}° (OSHA suggests 90–120°)")
        elif elbow["median"] < 90:
            add("elbow_closed", "elbow sharply bent (input device high or close)", "medium",
                f"median elbow angle {elbow['median']:.0f}° (OSHA suggests 90–120°)")
    if summary.get("interrupted_s", 0) >= 60:
        add("interrupted", "recording interrupted (no camera data)", "high",
            f"{summary['interrupted_s'] / 60:.0f} min without frames in {len(summary.get('interruptions', []))} gap(s); excluded from presence")
    if summary["valid_percent"] < 80:
        add("low_quality", "measurement quality below the acceptance threshold", "high",
            f"{summary['valid_percent']}% valid Samples")
    return out
