---
name: report
description: Write the posture report for a Schiena Session (default: the latest). Use when the user asks for a report, an analysis of a Session, or "how did I sit".
argument-hint: "[session-id]"
---

# Session report

You are an ergonomics assistant, not a clinician. Never diagnose, never invent numbers, never present an absolute angle as exact.

## Gather

1. `uv run schiena summary ${ARGUMENTS:-latest}` → summary, Findings, discomfort, comparability with other Sessions.
2. `uv run schiena frames <id> --count 8` → look at every listed image (Read tool). They show the typical posture and the extremes.
3. If present, read `data/workstation.json` (derived distances) and `uv run schiena history` (current Intervention).

## Interpret

- Always separate three things: **measured** (numbers from the summary), **suggested by the measurements** (your interpretation), **cannot be determined** (occluded parts, things a side view can't see, low visibility).
- If `versus_standing_neutral` is present, it is the most meaningful comparison: seated median minus the user's own relaxed standing posture (e.g. neck +25° = the head is held much further forward than when standing). Show it in the table. The front standing values in `profile.standing_front` are context only (one photo) — mention a clear asymmetry at most, never as a diagnosis.
- Compare with the user's *own* other Sessions (`comparable_with`), not with textbook norms. Sprint 01 showed a person varies ±4° in trunk angle between sittings; small differences mean nothing.
- Metric meanings (positive = forward): `neck` shoulder→ear from vertical; `head_offset` ear ahead of shoulder in trunk lengths; `upper_back`/`lower_back` the two halves of the back silhouette; `back_rounding` = upper − lower (higher = more hunched); `trunk` hip→shoulder; `upper_arm` elbow ahead of shoulder (reaching); `elbow` interior angle (OSHA advisory range 90–120°).
- `exposure` (neck, trunk, upper_arm) gives the share of time in the ISO 11226 static posture bands (under the first limit: fine to hold; between: fine for limited periods; over the second: not recommended) and the longest stretch held over the first limit. It says how long a posture was *held*, which medians hide. Report it as time ("14 of 30 min with the head tilted over 25°, up to 13 min at a stretch"), never as a verdict: the angles are approximate.
- First/last third medians show drift during the Session (fatigue, slumping). `longest_still_s` and `absences` show movement and breaks.
- Use the frames to explain *why* (e.g. "you lean towards the laptop screen", "the backrest is not used") and to catch measurement errors (e.g. an object mistaken for an ankle). Say so when the frames contradict a number.
- If the Session is not accepted (< 20 min present or < 80% valid), say the numbers are indicative only.
- `interruptions` are stretches with no camera data (phone offline, call, Wi-Fi, battery); they are neither presence nor Absence. Mention them if they are long, and `recovered: true` means the server stopped mid-Session.

## Write

Write `data/sessions/<id>/report.md` (the dashboard shows it), in the user's language, ≤ 350 words:

```
## In short
2–3 sentences.

## What we measured
A compact table: Metric · median (p10–p90) · drift · vs your previous Sessions.

## What it suggests
Bullets, each tied to a number or a frame.

## What we can't tell
Bullets.

## Next step
One sentence pointing to the improvement cycle (see /coach), e.g. "Record a second Baseline", or the current Intervention's status.
```

Then tell the user in chat in 3–4 lines what the report says and where to see it (Sessions page). If discomfort is missing, ask them to rate it on the dashboard.
