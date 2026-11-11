# Intervention Library — v0.2

Status: draft (2026-11-11), not yet reviewed by an ergonomics professional.
Claude may only suggest Interventions from this library (`/coach`). Each entry's **Expected effect** names the Metric used for `schiena intervention add --target <metric>:<increase|decrease>`.

Metric names: `trunk`, `neck`, `head_offset`, `upper_back`, `lower_back`, `back_rounding`, `upper_arm`, `elbow`, `hip`, `knee`, `trunk_minute_std`, `neck_minute_std`, `longest_still_s`, `absences`.

## How to read an entry

- **Kind** — *physical* (changes the Workstation: run `/calibrate` again afterwards) or *behavioural* (habits).
- **Justified by** — the Finding that makes the Intervention relevant. Finding names are provisional until Phase 3 defines them.
- **Expected effect** — the Metric that should move, and in which direction. This is what the Intervention Outcome checks against the Reference Variability. *Comfort only* means the side view cannot measure it: the Outcome can only be *comfort-only improvement* or *inconclusive*.
- **Applies when** — preconditions read from the Workstation.
- **Contraindications / caveats** — when not to suggest it, or what to warn about.
- **Cost** — *free* (adjust what is there, household items), or *purchase*. Purchases are never Interventions before a Plateau. They are listed separately and never presented as required (CLAUDE.md §2).

## Measurement caveats that shape this library

- Absolute angles are biased: pose models place the shoulder towards the back of the joint at a desk, so the trunk reads more reclined than it is. Findings must use **changes and variability**, never an absolute angle against a textbook value.
- Between sittings a Metric varies by itself (Sprint 01: trunk ±4°, head offset ±0.08). An Intervention is detectable only if it moves a Metric more than the Reference Variability measured between the two Baselines.
- The side view measures head forward offset, neck, trunk, upper/lower back profile, upper arm and elbow (when visible), hip/knee (best effort), presence and stillness. It cannot see the screen's lateral position, glare, wrist deviation or shoulder elevation. Interventions about those are *comfort only*.

## Sources

- **[OSHA-POS]** OSHA eTool *Computer Workstations — Good Working Positions*: neutral posture; elbows 90–120°; reclined sitting 105–120°; "even good posture is unhealthy if held"; vary position. https://www.osha.gov/etools/computer-workstations/positions
- **[OSHA-MON]** OSHA eTool *Monitors*: top line at or slightly below eye level; centre 15–20° below horizontal eye level; distance 20–40 in (50–100 cm), at least 20 in; directly in front; tilt 10–20°; larger text on small screens. https://www.osha.gov/etools/computer-workstations/components/monitors
- **[OSHA-CHK]** OSHA eTool *Evaluation Checklist*: torso upright or slightly reclined, lumbar support, forearms ~90–100° to the upper arm, thighs level, feet flat or on a footrest, laptops used as primary computers should get a separate keyboard and pointing device, tasks varied with micro-breaks, alternate sitting and standing. https://www.osha.gov/etools/computer-workstations/checklists/evaluation
- **[COCH-SIT]** Shrestha et al., *Workplace interventions for reducing sitting at work*, Cochrane 2018 (CD010912.pub5): **low-quality** evidence that sit-stand desks reduce sitting (~100 min/day at ≤ 3 months). Walking strategies did not significantly reduce sitting. https://cochranelibrary.com/cdsr/doi/10.1002/14651858.CD010912.pub5/information
- **[COCH-BRK]** Luger et al., *Work-break schedules for preventing musculoskeletal disorders in workers*, Cochrane 2019 (CD012886): **low-quality** evidence that extra breaks make little difference to musculoskeletal pain/discomfort. Individual trials with computer users found 30 s breaks every 20–40 min improved perceived discomfort without hurting productivity. https://cochranelibrary.com/cdsr/doi/10.1002/14651858.CD012886

Note: OSHA eTools are advisory and create no requirements. Evidence for behavioural Interventions is weak. That is a reason to test each one empirically, which is what Schiena does, and not to promise an effect.

---

## A. Screen

### I-01 Raise the main screen to eye level
- **Kind:** physical · **Cost:** free (books, box) or purchase (monitor arm/riser)
- **Justified by:** head forward (high head forward offset), especially when it increases during the Session.
- **Expected effect:** `head_offset` ↓, `neck` ↓.
- **Applies when:** the top of the main screen is clearly below eye level (`monitor_top_above_eye_cm` well below 0 in `workstation.json`).
- **Caveats:** for bifocal/progressive lenses, keep the screen lower and tilt it up [OSHA-MON]. Never raise the top above eye level, because the head then tilts back.
- **Source:** [OSHA-MON], [OSHA-CHK].

### I-02 Lower the main screen
- **Kind:** physical · **Cost:** free
- **Justified by:** Workstation shows the top of the screen above eye level; neck discomfort in the Comfort Rating.
- **Expected effect:** comfort only. The side view does not measure head extension yet.
- **Caveats:** don't combine with I-01.
- **Source:** [OSHA-MON].

### I-03 Bring the screen closer (about arm's length)
- **Kind:** physical · **Cost:** free
- **Justified by:** head forward and/or trunk leaning forward toward the screen.
- **Expected effect:** head forward offset ↓; trunk inclination ↓ (less forward lean).
- **Applies when:** the screen is farther than ~100 cm (Workstation).
- **Caveats:** keep it at least 50 cm away [OSHA-MON].
- **Source:** [OSHA-MON], [OSHA-CHK] ("reading without leaning").

### I-04 Increase text size / zoom
- **Kind:** behavioural · **Cost:** free
- **Justified by:** head forward or forward lean during reading or typing.
- **Expected effect:** head forward offset ↓; trunk inclination ↓.
- **Caveats:** a cheaper first step than I-03; try it before moving equipment.
- **Source:** [OSHA-MON] ("increase text size on smaller monitors").

### I-05 Put the main screen directly in front of you
- **Kind:** physical · **Cost:** free
- **Justified by:** Workstation shows the main screen off-centre (more than ~35° to the side); neck discomfort.
- **Expected effect:** comfort only. Twisting is invisible in the side view.
- **Source:** [OSHA-MON], [OSHA-CHK].

### I-06 Tilt the screen perpendicular to the line of sight
- **Kind:** physical · **Cost:** free
- **Justified by:** Workstation shows a strongly tilted screen, or glare.
- **Expected effect:** comfort only.
- **Source:** [OSHA-MON] (tilt 10–20°).

## B. Laptop setup (the current Workstation: MacBook built-in keyboard + raised external monitor)

### I-07 Use the external monitor as the only screen
- **Kind:** behavioural · **Cost:** free
- **Justified by:** head forward with large head movements, suggesting the gaze switches between the laptop and the external screen.
- **Expected effect:** head forward offset ↓; its variability may also drop.
- **Applies when:** both laptop screen and external monitor are in use.
- **Caveats:** only if the external monitor is itself well placed (see A).
- **Source:** [OSHA-MON] (primary monitor centred, others beside it).

### I-08 Separate keyboard and trackpad/mouse from the laptop
- **Kind:** physical · **Cost:** free if the user already owns them, otherwise **purchase** (post-Plateau only)
- **Justified by:** elbow angle outside 90–120°, or forward lean to reach the laptop keyboard.
- **Expected effect:** elbow angle → 90–120°; trunk inclination ↓.
- **Applies when:** the laptop is the main input device.
- **Caveats:** goes with I-09 (raise the laptop) or I-07. Once the keyboard is separate, place it per I-10.
- **Source:** [OSHA-CHK] ("laptops used as primary computers … separate keyboard and pointing device").

### I-09 Raise the laptop screen to eye level (stand or books)
- **Kind:** physical · **Cost:** free (books) or purchase (stand)
- **Justified by:** head forward, when the laptop screen is the one being looked at.
- **Expected effect:** head forward offset ↓.
- **Contraindication:** **only together with I-08.** Raising a laptop without a separate keyboard lifts the hands and the shoulders.
- **Source:** [OSHA-MON], [OSHA-CHK].

## C. Input devices

### I-10 Keyboard and trackpad close, at elbow height
- **Kind:** physical · **Cost:** free
- **Justified by:** elbow angle > 120° (arms reaching forward) or forward lean while typing.
- **Expected effect:** elbow angle ↓ toward 90–120°; trunk inclination ↓.
- **Caveats:** the trackpad (right hand) goes right beside the keyboard, not farther out [OSHA-CHK].
- **Source:** [OSHA-POS] (elbows close to the body, 90–120°), [OSHA-CHK].

### I-11 Keyboard flat or slightly tilted down
- **Kind:** physical · **Cost:** free
- **Justified by:** wrist/forearm discomfort.
- **Expected effect:** comfort only. Wrist extension is not measured.
- **Source:** [OSHA-CHK].

## D. Chair and sitting

### I-12 Adjust seat height (elbows at desk height, thighs level)
- **Kind:** physical · **Cost:** free
- **Justified by:** elbow angle < 90° (desk too high for the seat) or knee/hip angle far from ~90° (best effort).
- **Expected effect:** elbow angle → 90–120°; knee angle → ~90° when visible.
- **Caveats:** if raising the seat leaves the feet unsupported, combine with I-15.
- **Source:** [OSHA-POS], [OSHA-CHK].

### I-13 Sit back against the backrest
- **Kind:** behavioural · **Cost:** free
- **Justified by:** sustained forward trunk lean with the backrest unused (trunk inclination forward for most of the Session).
- **Expected effect:** trunk inclination ↓ (less forward lean).
- **Caveats:** may need I-10 or I-03 first, otherwise sitting back moves the user away from the keyboard and screen.
- **Source:** [OSHA-POS] (back fully supported, upright or slightly reclined).

### I-14 Add lumbar support (cushion or rolled towel)
- **Kind:** physical · **Cost:** free (household) or purchase (cushion)
- **Justified by:** forward trunk lean or slumping; lower-back discomfort in the Comfort Rating.
- **Expected effect:** trunk inclination ↓ and/or lower-back comfort ↑.
- **Applies when:** the chair has no adjustable lumbar support (Workstation).
- **Source:** [OSHA-POS], [OSHA-CHK].

### I-15 Footrest when feet don't rest flat
- **Kind:** physical · **Cost:** free (box, books) or purchase
- **Justified by:** Workstation or the image shows dangling feet; knee angle far from ~90° (best effort); legs/hips discomfort.
- **Expected effect:** knee angle → ~90° when visible; otherwise comfort only.
- **Source:** [OSHA-POS], [OSHA-CHK].

### I-16 Move the chair closer to the desk
- **Kind:** behavioural · **Cost:** free
- **Justified by:** elbow angle > 120° together with forward trunk lean (reaching).
- **Expected effect:** elbow angle ↓; trunk inclination ↓.
- **Caveats:** needs leg clearance under the desk [OSHA-CHK].
- **Source:** [OSHA-CHK].

### I-17 Recline the backrest slightly (≈ 100–110°)
- **Kind:** physical · **Cost:** free
- **Justified by:** low trunk variability held upright or forward; lower-back discomfort.
- **Expected effect:** trunk inclination shifts backwards; lower-back comfort ↑.
- **Caveats:** with the trunk bias, judge only the *change* from the Baselines. Combine with I-03 or I-04 if the screen becomes too far.
- **Source:** [OSHA-POS] (reclined sitting 105–120° between torso and thighs).

## E. Movement and variation

### I-18 Micro-breaks: 30 s every 20–40 min
- **Kind:** behavioural · **Cost:** free
- **Justified by:** long periods of relative stillness (low variability of trunk and head).
- **Expected effect:** duration of the longest still period ↓; postural variability ↑.
- **Caveats:** evidence on pain is low-quality [COCH-BRK]. Present it as an experiment, not a cure. Absences are detected only after 5 s and a 30 s pause may not leave the frame, so the effect shows up as variability.
- **Source:** [COCH-BRK], [OSHA-POS], [OSHA-CHK].

### I-19 Stand up and walk for a few minutes every 30–60 min
- **Kind:** behavioural · **Cost:** free
- **Justified by:** no Absence and low variability for the whole Session.
- **Expected effect:** Absences appear (count ↑); postural variability ↑ after returning.
- **Caveats:** presence time drops. With one 3-minute break per 30 min the Session still stays above the 20-min acceptance threshold.
- **Source:** [OSHA-POS] ("stand up and walk around for a few minutes periodically"), [OSHA-CHK].

### I-20 Vary the sitting posture on purpose
- **Kind:** behavioural · **Cost:** free
- **Justified by:** low trunk variability (one posture held for most of the Session).
- **Expected effect:** postural variability ↑ (trunk inclination p10–p90 range widens).
- **What to do:** alternate upright and slightly reclined sitting, with small adjustments to the chair and backrest.
- **Source:** [OSHA-POS] ("even good posture is unhealthy if held").

### I-21 Do some tasks standing (calls, meetings, reading)
- **Kind:** behavioural · **Cost:** free
- **Justified by:** no Absence for the whole Session; low variability.
- **Expected effect:** Absences (count ↑).
- **Caveats:** standing Sessions are out of scope (seated only), so the effect is measured indirectly.
- **Source:** [OSHA-CHK] (alternate sitting and standing), [OSHA-POS].

## Purchase suggestions (post-Plateau only, never required)

Shown separately once a Plateau is reached and a Finding remains:
- Laptop stand.
- External keyboard and mouse/trackpad. Together with the stand these make I-08 + I-09.
- Monitor arm or riser (I-01).
- Lumbar cushion (I-14).
- Footrest (I-15).
- Chair with adjustable seat height, lumbar support and armrests.
- Sit-stand desk: **low-quality evidence** that it reduces sitting [COCH-SIT]. Say so explicitly.

## Explicitly out of scope

- Eye-strain advice, such as the 20-20-20 rule, and lighting/glare beyond I-06: not posture, and not measurable.
- Exercises, stretching programmes, anything with a clinical flavour: Schiena makes no diagnoses.
- Wrist rests and split keyboards: wrist posture is not measured.
