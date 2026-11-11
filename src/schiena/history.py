"""Intervention Outcome and Plateau (pure logic).

Discomfort is rated 0–10 per body region after each Session (0 = none, 10 = severe).
"""

from __future__ import annotations

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


def reference_variability(baselines: list[dict], metric: str) -> float | None:
    vals = [metric_value(b, metric) for b in baselines]
    vals = [v for v in vals if v is not None]
    if len(vals) < 2:
        return None
    floor = RV_FLOOR.get(metric.removesuffix("_minute_std"), 0.0)
    return max(floor, max(vals) - min(vals))


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
    reference: Reference Variability per Metric, reused when there is a single baseline.
    """
    reference = dict(reference or {})
    moves = []
    for tgt in targets:
        m = tgt["metric"]
        base_vals = [v for v in (metric_value(b, m) for b in baselines) if v is not None]
        after = metric_value(reassessment, m)
        rv = reference.get(m) or reference_variability(baselines, m)
        if rv is not None:
            reference[m] = rv
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
