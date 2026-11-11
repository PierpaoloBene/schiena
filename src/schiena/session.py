"""Session rules (pure logic): framing check, Absence, acceptance, summary, comparability.

A Sample is a dict as stored in ``samples.jsonl``::

    {"t": 12.0, "person": true, "valid": true, "side": "right", "fwd": 1,
     "w": 720, "h": 1280, "trunk_len": 310.0, "hip": [400.0, 900.0],
     "metrics": {"trunk": 8.1, ...}, "kp": [[x, y, vis], ...], "back": [[x, y], ...],
     "mpp": 0.0016}

``kp`` and ``back`` are normalised to the image size; ``hip`` and ``trunk_len`` are pixels.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from datetime import datetime

from .posture import METRICS, SHOULDER, VISIBLE

ABSENCE_MIN_S = 5.0
MAX_HOLE_S = 3.0  # a longer stretch without Samples is an interruption (no camera data)
FRAMING_HOLD_S = 5.0
SESSION_S = 30 * 60
ACCEPT_PRESENCE_S = 20 * 60
ACCEPT_VALID = 0.80
SCALE_RANGE = (0.12, 0.45)  # trunk length / image height
STILL_RANGE_DEG = 5.0


# ---------------------------------------------------------------- framing


@dataclass
class FramingCheck:
    ok: bool
    problems: list[str]


def check_framing(s: dict) -> FramingCheck:
    """Can a Session start with the camera where it is?"""
    if not s.get("person"):
        return FramingCheck(False, ["No one in view — sit down at your desk."])
    problems: list[str] = []
    if not s.get("valid"):
        problems.append("Ear, shoulder and hip must be visible — move the phone back or higher.")
    else:
        h = s["h"]
        scale = s["trunk_len"] / h
        if scale < SCALE_RANGE[0]:
            problems.append("You look too small — bring the phone closer.")
        elif scale > SCALE_RANGE[1]:
            problems.append("You look too big — move the phone farther away.")
        kp = s.get("kp") or []
        if kp:
            ls, rs = kp[SHOULDER["left"]], kp[SHOULDER["right"]]
            spread = abs(ls[0] - rs[0]) * s["w"] / s["trunk_len"]
            if spread > 0.35:
                problems.append("Turn the phone so it sees you exactly from the side.")
            ys = [p[1] for p in kp if p[2] >= VISIBLE]
            if ys and min(ys) < 0.02:
                problems.append("Your head is cut off — tilt or lower the phone.")
    return FramingCheck(not problems, problems)


class FramingGate:
    """Opens once the framing check has held for FRAMING_HOLD_S seconds."""

    def __init__(self, hold_s: float = FRAMING_HOLD_S):
        self.hold_s = hold_s
        self.since: float | None = None

    def update(self, t: float, check: FramingCheck) -> float:
        """Returns the fraction (0–1) of the hold period completed."""
        if not check.ok:
            self.since = None
            return 0.0
        if self.since is None:
            self.since = t
        return min(1.0, (t - self.since) / self.hold_s)


# ---------------------------------------------------------------- absence


def seated_hip_y(samples: list[dict]) -> float | None:
    ys = [s["hip"][1] for s in samples if s.get("valid") and s.get("hip")]
    return statistics.median(ys) if ys else None


def is_absent(s: dict, hip_ref: float | None, trunk_ref: float | None) -> bool:
    """Out of frame, or standing (hip raised more than half a trunk length)."""
    if not s.get("person") or not s.get("hip"):
        return True
    if hip_ref is not None and trunk_ref:
        return s["hip"][1] < hip_ref - 0.5 * trunk_ref
    return False


def find_absences(samples: list[dict]) -> list[tuple[float, float]]:
    """Absence intervals [start, end) of at least ABSENCE_MIN_S seconds.

    Absences separated by less than ABSENCE_MIN_S of presence are merged.
    """
    if not samples:
        return []
    hip_ref = seated_hip_y(samples)
    trunks = [s["trunk_len"] for s in samples if s.get("valid")]
    trunk_ref = statistics.median(trunks) if trunks else None
    step = _step(samples)
    runs: list[list[float]] = []
    start = None
    prev_t = None
    for s in samples:
        if start is not None and prev_t is not None and s["t"] - prev_t > MAX_HOLE_S:
            runs.append([start, end])  # an interruption ends the Absence: we don't know what happened
            start = None
        prev_t = s["t"]
        if is_absent(s, hip_ref, trunk_ref):
            if start is None:
                start = s["t"]
            end = s["t"] + step
        elif start is not None:
            runs.append([start, end])
            start = None
    if start is not None:
        runs.append([start, end])
    merged: list[list[float]] = []
    for r in runs:
        if merged and r[0] - merged[-1][1] < ABSENCE_MIN_S:
            merged[-1][1] = r[1]
        else:
            merged.append(r)
    return [(a, b) for a, b in merged if b - a >= ABSENCE_MIN_S]


def find_interruptions(samples: list[dict], duration: float) -> list[tuple[float, float]]:
    """Stretches with no Samples at all (phone offline, call, Wi-Fi drop, battery)."""
    if not samples:
        return [(0.0, duration)] if duration > MAX_HOLE_S else []
    step = _step(samples)
    out = []
    if samples[0]["t"] > MAX_HOLE_S:
        out.append((0.0, samples[0]["t"]))
    for a, b in zip(samples, samples[1:]):
        if b["t"] - a["t"] > MAX_HOLE_S:
            out.append((a["t"] + step, b["t"]))
    end = samples[-1]["t"] + step
    if duration - end > MAX_HOLE_S:
        out.append((end, duration))
    return out


def _step(samples: list[dict]) -> float:
    if len(samples) < 2:
        return 1.0
    return statistics.median(b["t"] - a["t"] for a, b in zip(samples, samples[1:]))


def present_samples(samples: list[dict], absences: list[tuple[float, float]]) -> list[dict]:
    return [s for s in samples if not any(a <= s["t"] < b for a, b in absences)]


# ---------------------------------------------------------------- summary


def percentile(values: list[float], q: float) -> float:
    v = sorted(values)
    if len(v) == 1:
        return v[0]
    k = (len(v) - 1) * q
    lo = int(k)
    hi = min(lo + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (k - lo)


def longest_still_period(samples: list[dict], keys=("trunk", "neck"), tol=STILL_RANGE_DEG) -> float:
    """Longest stretch (s) in which each of ``keys`` stays within ``tol`` degrees."""
    from collections import deque

    pts = [(s["t"], [s["metrics"].get(k) for k in keys]) for s in samples if s.get("valid")]
    pts = [(t, v) for t, v in pts if all(x is not None for x in v)]
    best = 0.0
    i = 0
    mins = [deque() for _ in keys]  # monotonic deques of indices, per key
    maxs = [deque() for _ in keys]
    for k, (t, vals) in enumerate(pts):
        if k > 0 and t - pts[k - 1][0] > 3:  # gap (Absence or invalid run) breaks stillness
            i = k
            for d in mins + maxs:
                d.clear()
        for j, v in enumerate(vals):
            while mins[j] and pts[mins[j][-1]][1][j] >= v:
                mins[j].pop()
            mins[j].append(k)
            while maxs[j] and pts[maxs[j][-1]][1][j] <= v:
                maxs[j].pop()
            maxs[j].append(k)
        while any(pts[maxs[j][0]][1][j] - pts[mins[j][0]][1][j] > tol for j in range(len(keys))):
            i += 1
            for d in mins + maxs:
                while d and d[0] < i:
                    d.popleft()
        best = max(best, t - pts[i][0])
    return best


def minute_variability(samples: list[dict], key: str) -> float | None:
    """Median over minutes of the per-minute standard deviation of a Metric."""
    by_minute: dict[int, list[float]] = {}
    for s in samples:
        v = s["metrics"].get(key) if s.get("valid") else None
        if v is not None:
            by_minute.setdefault(int(s["t"] // 60), []).append(v)
    stds = [statistics.pstdev(v) for v in by_minute.values() if len(v) >= 20]
    return statistics.median(stds) if stds else None


def median_standard_error(samples: list[dict], key: str, min_minutes: int = 5) -> float | None:
    """How much a Session median could move by chance: spread of the per-minute medians.

    Standard error of a median ≈ 1.25 × SD / √n, with n = minutes. Minutes, not seconds, because
    consecutive seconds are strongly correlated.
    """
    by_minute: dict[int, list[float]] = {}
    for s in samples:
        v = s["metrics"].get(key) if s.get("valid") else None
        if v is not None:
            by_minute.setdefault(int(s["t"] // 60), []).append(v)
    medians = [statistics.median(v) for v in by_minute.values() if len(v) >= 20]
    if len(medians) < min_minutes:
        return None
    return 1.2533 * statistics.stdev(medians) / math.sqrt(len(medians))


def time_band(iso: str) -> str:
    h = datetime.fromisoformat(iso).hour
    return "morning" if h < 12 else "afternoon" if h < 18 else "evening"


def summarize(samples: list[dict], started_at: str, duration_s: float | None = None) -> dict:
    """Deterministic Session summary — the numbers Claude reports on."""
    samples = sorted(samples, key=lambda s: s["t"])
    absences = find_absences(samples)
    duration = duration_s if duration_s is not None else (samples[-1]["t"] + _step(samples) if samples else 0.0)
    interruptions = find_interruptions(samples, duration)
    absent = sum(b - a for a, b in absences)
    interrupted = sum(b - a for a, b in interruptions)
    presence = max(0.0, duration - absent - interrupted)
    present = present_samples(samples, absences)
    valid = [s for s in present if s.get("valid")]
    valid_ratio = len(valid) / len(present) if present else 0.0

    metrics = {}
    for k in METRICS:
        vals = [s["metrics"][k] for s in valid if s["metrics"].get(k) is not None]
        if len(vals) < 10:
            metrics[k] = {"visible_percent": round(100 * len(vals) / max(1, len(valid)), 1)}
            continue
        third = max(1, len(vals) // 3)
        metrics[k] = {
            "median": round(statistics.median(vals), 3),
            "p10": round(percentile(vals, 0.10), 3),
            "p90": round(percentile(vals, 0.90), 3),
            "first_third_median": round(statistics.median(vals[:third]), 3),
            "last_third_median": round(statistics.median(vals[-third:]), 3),
            "visible_percent": round(100 * len(vals) / len(valid), 1),
        }
        se = median_standard_error(valid, k)
        if se is not None:
            metrics[k]["median_se"] = round(se, 4)
    for k in ("trunk", "neck"):
        if "median" in metrics[k]:
            mv = minute_variability(valid, k)
            metrics[k]["minute_std"] = round(mv, 2) if mv is not None else None

    placement = None
    if valid:
        placement = {
            "side": statistics.mode(s["side"] for s in valid),
            "body_scale": round(statistics.median(s["trunk_len"] / s["h"] for s in valid), 4),
            "hip_x": round(statistics.median(s["hip"][0] / s["w"] for s in valid), 4),
            "hip_y": round(statistics.median(s["hip"][1] / s["h"] for s in valid), 4),
        }
    return {
        "started_at": started_at,
        "time_band": time_band(started_at),
        "duration_s": round(duration, 1),
        "presence_s": round(presence, 1),
        "valid_percent": round(100 * valid_ratio, 1),
        "accepted": presence >= ACCEPT_PRESENCE_S and valid_ratio >= ACCEPT_VALID,
        "absences": [{"start_s": round(a, 1), "end_s": round(b, 1)} for a, b in absences],
        "interruptions": [{"start_s": round(a, 1), "end_s": round(b, 1)} for a, b in interruptions],
        "interrupted_s": round(interrupted, 1),
        "longest_still_s": round(longest_still_period(valid), 1),
        "placement": placement,
        "metrics": metrics,
    }


# ---------------------------------------------------------------- comparability


def comparability(a: dict, b: dict) -> list[str]:
    """Reasons why two Session summaries are *not* fully comparable (empty = comparable)."""
    reasons = []
    pa, pb = a.get("placement"), b.get("placement")
    if not pa or not pb:
        return ["placement unknown"]
    if pa["side"] != pb["side"]:
        reasons.append("filmed from different sides")
    if abs(pa["body_scale"] / pb["body_scale"] - 1) > 0.10:
        reasons.append("phone distance changed (body scale differs by more than 10%)")
    if abs(pa["hip_x"] - pb["hip_x"]) > 0.08 or abs(pa["hip_y"] - pb["hip_y"]) > 0.08:
        reasons.append("framing changed (body position in the image moved)")
    if a.get("time_band") != b.get("time_band"):
        reasons.append(f"different time of day ({a.get('time_band')} vs {b.get('time_band')})")
    return reasons
