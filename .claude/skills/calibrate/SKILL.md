---
name: calibrate
description: Calibrate Schiena for this user and desk — check the personal profile (height, relaxed standing photos) and reconstruct the Workstation (monitor, laptop, keyboard, desk, chair) in 3D from a Session frame. Use after the first Session, after a physical Intervention or a phone move, or when the user asks to calibrate, set up the workstation, or rebuild the 3D desk.
argument-hint: "[session-id]"
---

# Calibrate: you + your Workstation

Two parts. The user does theirs on the phone (page → **Calibrate**); you do the reconstruction.

## 1. Check the user's part

Read `data/profile.json` (may not exist) and list `data/photos/`.

- `height_cm` missing → scale assumes an average body. Ask for the height (or set it: `uv run schiena calibrate --height <cm>`).
- `standing_side` missing → no neutral reference: seated angles can only be compared between Sessions. Suggest the side photo (10 s timer on the phone).
- `standing_front` missing → optional, context only.
- Workstation photos (`data/photos/*.jpg` other than `standing_*`) → optional context: number of screens, what's in front of the user. Look at them if present.

Don't block on missing items: say what is missing and what it would add, then continue.

## 2. Reconstruct the Workstation

The phone stands still during a Session, so the furniture is visible in its frames. You mark points on one frame; the tool converts them into body-relative centimetres (with the calibrated scale if the profile has a height).

1. `uv run schiena grid ${ARGUMENTS:-latest}` → JSON with `grid_image` (a frame with a labelled 0.1 grid, chosen where the posture is typical). Read the image.
2. Locate these points in **normalised image coordinates** `[x, y]` (0–1, origin top-left; use the grid labels, interpolate to ~0.01). Include only what you can actually see; skip the rest.

   | object | points | meaning |
   |---|---|---|
   | `monitor` | `top`, `bottom` | top and bottom edge of the external screen's panel (seen edge-on) |
   | `laptop_screen` | `top`, `bottom` | top and bottom edge of the laptop lid |
   | `keyboard` | `near`, `far` | edge closest to the user and farthest edge of the keyboard (or laptop keyboard deck) |
   | `desk` | `front_edge`, `back_edge` | desk top surface at the user's edge and at the far edge |
   | `seat` | `front`, `back` | top surface of the seat cushion, front and back |
   | `backrest` | `top`, `bottom` | backrest front surface |
   | `floor` | `point` | floor level below the user's feet |

3. Write the annotation to a temp file and save it:
   ```json
   {"frame": "<frame from step 1>", "objects": {"monitor": {"top": [0.86, 0.29], "bottom": [0.86, 0.45]}, "...": {}}, "notes": "MacBook on desk + external monitor raised behind it; chair without armrests"}
   ```
   `uv run schiena workstation <session-id> <file.json>`
4. Sanity-check the printed `derived` distances (e.g. monitor 50–100 cm from the eye, keyboard within ±15 cm of elbow height). If something is implausible, re-check your points on the grid image and redo step 3.

## 3. Tell the user

In 4–6 lines: what the profile adds or still lacks, and what you found at the desk (e.g. "the monitor top is 12 cm below your eyes; the keyboard is 8 cm above your elbow"). Distances are approximate (± a few cm). The dashboard's **Calibration** page shows both, the desk in 3D.
