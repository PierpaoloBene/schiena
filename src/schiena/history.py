"""Intervention Outcome and Plateau (pure logic).

Discomfort is rated 0–10 per body region after each Session (0 = none, 10 = severe).
"""

from __future__ import annotations

import math
import statistics

from .session import comparability

REGIONS = ("neck", "shoulders", "upper_back", "lower_back", "wrists", "legs")

# Smallest Reference Variability we trust, per Metric (noise floor of the measurement).
RV_FLOOR = {
    "trunk": 1.5,
    "neck": 1.5,
    "head_offset": 0.02,
    "upper_back": 2.0,
    "lower_back": 2.0,
    "back_rounding": 2.5,
    "upper_arm": 2.0,
    "elbow": 3.0,
    "hip": 3.0,
    "knee": 3.0,
    "longest_still_s": 120.0,
    "absences": 1.0,
}

SUCCESSFUL = "successful"
INCONCLUSIVE = "inconclusive"
COMFORT_ONLY = "comfort-only improvement"


def metric_value(summary: dict, metric: str) -> float | None:
    if metric == "longest_still_s":
        return summary.get("longest_still_s")
    if metric == "absences":
        return float(len(summary.get("absences", [])))
    if metric.endswith("_minute_std"):
        return (summary["metrics"].get(metric.removesuffix("_minute_std")) or {}).get("minute_std")
    return (summary["metrics"].get(metric) or {}).get("median")


def median_se(summary: dict, metric: str) -> float | None:
    if metric in ("longest_still_s", "absences") or metric.endswith("_minute_std"):
        return None
    return (summary["metrics"].get(metric) or {}).get("median_se")


def day_to_day(baselines: list[dict], metric: str) -> float | None:
    """Typical difference between two of the user's ordinary Sessions: √2 × SD of the Baselines.

    With two Baselines this is exactly their difference; with three or more every one counts,
    so a single unusual day weighs less.
    """
    vals = [v for v in (metric_value(b, metric) for b in baselines) if v is not None]
    if len(vals) < 2:
        return None
    return math.sqrt(2) * statistics.stdev(vals)


def measurement_noise(baselines: list[dict], reassessment: dict | None, metric: str) -> float | None:
    """How far the Baseline mean and the Reassessment could differ by chance within the Sessions:
    2 × the standard error of that difference, from the minute-by-minute spread."""
    base = [v for v in (median_se(b, metric) for b in baselines) if v is not None]
    after = median_se(reassessment, metric) if reassessment else None
    if not base or after is None:
        return None
    var_base = sum(v * v for v in base) / len(base) ** 2  # variance of the mean of the Baseline medians
    return 2 * math.sqrt(var_base + after * after)


def reference_variability(baselines: list[dict], metric: str, reassessment: dict | None = None,
                          reused: float | None = None) -> dict | None:
    """The change a Metric must exceed to count: the largest of
    - floor: noise floor of the measurement (RV_FLOOR);
    - day_to_day: how much the user's ordinary Sessions differ (or a value reused from before);
    - measurement_noise: chance variation inside the Sessions being compared.
    """
    parts = {
        "floor": RV_FLOOR.get(metric.removesuffix("_minute_std"), 0.0),
        "day_to_day": reused if reused is not None else day_to_day(baselines, metric),
        "measurement_noise": measurement_noise(baselines, reassessment, metric),
    }
    if parts["day_to_day"] is None:
        return None
    known = {k: v for k, v in parts.items() if v is not None}
    deciding = max(known, key=known.get)
    return {"value": known[deciding], "deciding": deciding,
            **{k: (round(v, 4) if v is not None else None) for k, v in parts.items()}}


def discomfort_change(before: list[dict], after: dict) -> dict:
    """Compare the mean baseline discomfort with the Reassessment discomfort."""
    regions = {}
    for r in REGIONS:
        b = [d[r] for d in before if d and d.get(r) is not None]
        if b and after and after.get(r) is not None:
            regions[r] = round(after[r] - statistics.mean(b), 2)
    total = sum(regions.values())
    worse = any(v >= 2 for v in regions.values()) or total >= 2
    better = not worse and total <= -2
    return {"per_region": regions, "total": round(total, 2), "worse": worse, "better": better,
            "rated": bool(regions)}


def evaluate(
    baselines: list[dict],
    reassessment: dict,
    targets: list[dict],
    discomfort_before: list[dict],
    discomfort_after: dict | None,
    reference: dict[str, float] | None = None,
) -> dict:
    """Intervention Outcome from Session summaries.

    targets: [{"metric": "head_offset", "direction": "decrease"|"increase"}]
    reference: day-to-day variability per Metric from earlier Baselines, reused when there is a single
    Baseline. The returned "reference_variability" holds the day-to-day values to reuse next time.
    """
    reference = dict(reference or {})
    moves = []
    for tgt in targets:
        m = tgt["metric"]
        base_vals = [v for v in (metric_value(b, m) for b in baselines) if v is not None]
        after = metric_value(reassessment, m)
        detail = reference_variability(baselines, m, reassessment, reused=reference.get(m))
        rv = detail["value"] if detail else None
        if detail is not None and detail["day_to_day"] is not None:
            reference[m] = detail["day_to_day"]
        if not base_vals or after is None or rv is None:
            moves.append({"metric": m, "direction": tgt["direction"], "measurable": False})
            continue
        before = statistics.mean(base_vals)
        change = after - before
        expected = change < 0 if tgt["direction"] == "decrease" else change > 0
        moves.append({
            "metric": m,
            "direction": tgt["direction"],
            "measurable": True,
            "baseline": round(before, 3),
            "reassessment": round(after, 3),
            "change": round(change, 3),
            "reference_variability": round(rv, 3),
            "threshold": {k: v for k, v in detail.items() if k != "value"},
            "moved_as_expected": bool(expected and abs(change) > rv),
        })
    comfort = discomfort_change(discomfort_before, discomfort_after or {})
    not_comparable = sorted({r for b in baselines for r in comparability(b, reassessment)})
    moved = any(x.get("moved_as_expected") for x in moves)

    if moved and not comfort["worse"]:
        outcome, cause = SUCCESSFUL, None
    elif not moved and comfort["better"]:
        outcome, cause = COMFORT_ONLY, None
    else:
        outcome = INCONCLUSIVE
        if moved:
            cause = "worse comfort"
        elif not_comparable:
            cause = "not comparable"
        else:
            cause = "no measurable effect"
    return {
        "outcome": outcome,
        "probable_cause": cause,
        "metrics": moves,
        "comfort": comfort,
        "limited_comparability": not_comparable,
        "reference_variability": {k: round(v, 3) for k, v in reference.items()},
    }


def plateau(interventions: list[dict]) -> str | None:
    """Rule (c): three consecutive inconclusive Interventions. (a) and (b) are judged by Claude."""
    done = [i for i in interventions if i.get("outcome")]
    if len(done) >= 3 and all(i["outcome"] == INCONCLUSIVE for i in done[-3:]):
        return "three consecutive inconclusive Interventions"
    return None
