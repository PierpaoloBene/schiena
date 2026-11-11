---
name: coach
description: Run the Schiena improvement cycle — decide the next step (another Baseline, suggest one Intervention, evaluate a Reassessment, keep/revert, Plateau). Use when the user asks what to do next, wants a suggestion to improve their posture, says they applied a change, or asks whether a change worked.
---

# Improvement cycle

**Baseline 1 → Baseline 2 → one Intervention → Reassessment → keep or revert → repeat.** Same day allowed.

## 1. Read the state

- `uv run schiena sessions` and `uv run schiena history`.
- For Sessions involved, `uv run schiena summary <id>` (it includes comparability).
- `data/workstation.json` and `data/profile.json` (height, relaxed standing reference) if present; `docs/intervention-library.md` (the only Interventions you may suggest).

## 2. Decide

Use only accepted Sessions (≥ 20 min present, ≥ 80% valid) with a discomfort rating; if a rating is missing, ask the user to fill it on the dashboard first.

- **Fewer than 2 comparable Baselines** → ask for another Session in similar conditions (similar time of day, ordinary work, phone beside them; it doesn't have to be the same spot). Label Sessions: `uv run schiena label <id> "baseline 1"`.
- **2 or more Baselines, no Intervention in progress** (more is better: every Baseline counts towards the user's normal variability) → suggest **one** Intervention:
  - pick the Finding with the most evidence (numbers + frames + discomfort) and the library entry that addresses it;
  - prefer free and behavioural entries before physical ones, and never suggest purchases before a Plateau;
  - respect contraindications/combinations in the library;
  - never re-suggest an entry that failed for *no measurable effect* or *worse comfort*, unless the Workstation changed significantly; *not applied* / *not comparable* may be retried;
  - register it: `uv run schiena intervention add --library-id I-04 --title "Increase text size" --kind behavioural --instructions "<what to do, concretely>" --target head_offset:decrease --baselines <b1>,<b2>`. If the Baselines are a single previous Reassessment, add `--reference '<reference_variability JSON from the previous Intervention>'` (it holds the day-to-day values).
  - tell the user exactly what to change and to record a Session once it's in place; mark it applied when they confirm: `uv run schiena intervention apply <int-id>`.
- **Intervention applied and a newer accepted Session exists** → `uv run schiena intervention evaluate <int-id> --reassessment <id>` and explain the result:
  - *successful* — a target Metric moved beyond the Reference Variability and comfort didn't worsen → `intervention keep`; the Reassessment becomes the new Baseline.
  - each target Metric has a `threshold` with `floor`, `day_to_day`, `measurement_noise` and which one was `deciding`. Say it in plain words: "your back changed by 3°, but your ordinary days already differ by 4°" or "…but within these Sessions you moved so much that 3° could be chance".
  - *comfort-only improvement* → keep it as well.
  - *inconclusive* → the user's feeling wins; `intervention revert` and go back to the original Baselines for the next suggestion. The probable cause is set automatically (*no measurable effect*, *worse comfort*, *not comparable*); use `intervention not-applied <id>` if the user didn't actually apply it.
  - Physical change → also run `/calibrate` on the Reassessment.
  - If `limited_comparability` is not empty, say so explicitly; never hide it.
- **Plateau** (history says so after 3 inconclusive, or no medium/high-confidence Finding justifies a library entry, or all applicable entries were tried) → say so; suggest a check-up Session every 2–4 weeks; only now list optional purchases from the library's purchase section, never as required.

## 3. Answer

Short and concrete, in the user's language: where they are in the cycle, the one thing to do next, and what you registered. The Progress page on the dashboard shows the history and before/after comparison.
