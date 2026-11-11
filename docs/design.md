# Design

How Schiena works and why. For contributors and for Claude.

## Principles

1. **Little effort for the user.** Claude does the setup. The user opens a page on the phone once, puts the phone at their side and works.
2. **The tool measures, Claude interprets.** Every number comes from deterministic code (`src/schiena/`). Claude reads the numbers and frames, explains them, suggests one change at a time and judges whether it worked. It never invents numbers or makes diagnoses.
3. **Local first.** Video is never stored. Landmarks (1 per second) and 2 frames per minute are kept in `data/`. Claude sees a selection of frames and the numbers when the user runs a skill.
4. **Compare people with themselves.** Angles from one camera are approximate. Sessions are compared with the same person's other Sessions and with their relaxed standing posture, never with textbook values.

## Architecture

```
Phone (browser, no app)          Computer: `uv run schiena` (Python)              Computer: browser
┌─────────────────────┐  HTTPS   ┌───────────────────────────────────────┐  WS  ┌──────────────────────┐
│ front camera        │ ──JPEG─► │ MediaPipe Pose Landmarker (heavy)     │ ───► │ dashboard (React +   │
│ ~2 frames/s         │          │ 33 landmarks, world coords, mask      │      │ three.js)            │
│ black screen, timer │ ◄─status─│ framing, Absence, interruptions       │      │                      │
└─────────────────────┘          │ data/: Samples 1/s, 2 frames/min      │      └──────────────────────┘
                                 └───────────────────────────────────────┘
                                                   │
                                                   ▼
                                Claude Code skills: /setup  /calibrate  /report  /coach
```

- **Server**: Python 3.10–3.12 via `uv`, FastAPI + uvicorn, MediaPipe Tasks, OpenCV.
- **Dashboard**: Vite + React + TypeScript + three.js (react-three-fiber), built to `web/dist/` and served by the Python server. `/camera` is the phone page.
- **Two listeners**: `http://127.0.0.1:4700` for the dashboard (full API, this computer only) and `https://<lan-ip>:4743` for the phone. The phone listener only serves the camera page, frame upload, photo upload and calibration; Session data can't be read from the network.
- **HTTPS**: mobile browsers only allow the camera on a secure origin. The server creates a self-signed certificate for its LAN address in `certs/`; the user accepts the browser warning once. The phone sends frames with `fetch` POST rather than WebSocket, because Safari is stricter with WebSockets on self-signed certificates.
- **Rates**: the phone sends ~2 frames/s for the live view; analysis and stored Samples run at 1/s; 2 frames per minute are saved as JPEG.
- **Pose engine** behind the `PoseEstimator` protocol (`pose.py`). MediaPipe heavy takes ~75 ms per frame on an Apple Silicon Mac; at 1 fps the trunk angle jitters by ~0.5° between consecutive Samples.

## Code map

| File | What it does |
|---|---|
| `posture.py` | Metrics of one frame from landmarks and the person mask (pure) |
| `session.py` | Framing check, Absence, interruptions, acceptance, Session summary, comparability (pure) |
| `history.py` | Intervention Outcome and Plateau (pure) |
| `findings.py` | Deterministic Findings from a summary (pure) |
| `calibration.py` | Height, standing reference photos, scale (pure) |
| `workstation.py` | Image points → body-relative metres (pure) |
| `pose.py` | MediaPipe wrapper, Sample construction |
| `server.py` | Live pipeline and HTTP API |
| `storage.py` | Layout of `data/` |
| `certs.py` | Self-signed certificate |
| `cli.py` | The `schiena` command used by the user and by the skills |

## Data

```
data/
├── sessions/<id>/session.json   metadata, summary, discomfort rating, label
│                 samples.jsonl  one Sample per second
│                 frames/*.jpg   2 per minute, named by second
│                 report.md      written by Claude (/report)
├── profile.json                 height and relaxed standing reference (Calibrate)
├── workstation.json             reconstructed desk (/calibrate)
├── photos/                      standing and desk photos
└── history.json                 Interventions and Outcomes (/coach)
```

`SCHIENA_DATA` moves it elsewhere. Everything in `data/`, `models/` and `certs/` is git-ignored.

## Metrics

Side view at 90°, phone at chest height, 1.5–2 m away. Either side works; the side facing the camera is detected. All angles are positive forward.

| Metric | Definition |
|---|---|
| `neck` | shoulder → ear, from vertical |
| `head_offset` | ear ahead of shoulder, in trunk lengths |
| `upper_back`, `lower_back` | the two halves of the back silhouette (segmentation mask) between shoulder and hip, from vertical |
| `back_rounding` | `upper_back − lower_back`; higher = more hunched |
| `trunk` | hip → shoulder, from vertical |
| `upper_arm` | shoulder → elbow from vertical; positive = reaching forward |
| `elbow`, `hip`, `knee` | interior angles, when visible |

Hidden joints (visibility < 0.5) give no value; nothing is estimated. MediaPipe has no spine landmarks, hence the silhouette. The model places the shoulder towards the back of the joint, so `trunk` reads more reclined than it is; this is why values are compared, not judged on their own.

## Sessions

- A Session starts by itself once the framing check holds for 5 s (person found; ear, shoulder, hip visible; pure side view; body size in range) and lasts 30 minutes of wall clock.
- **Absence**: out of frame, or the hip rises more than half a trunk length above its seated height, for ≥ 5 s. Absences closer than 5 s are merged. Absence is excluded from presence, not counted as invalid.
- **Interruption**: more than 3 s with no Samples at all (phone call, Wi-Fi, battery, computer asleep). Neither presence nor Absence. Frames carry the phone's capture time (`X-Captured-At`); while the computer is unreachable the phone queues frames (1/s, up to 15 min) and uploads them later at their real time. The camera is restarted after a call, and a reloaded page resumes the same Session.
- The server closes a Session at 30 min once the phone's backlog is in (at most 15 min later), finishes Sessions left open by a crash on its next start (`recovered: true`), and keeps macOS awake with `caffeinate` while recording.
- **Accepted** with ≥ 20 min of presence and ≥ 80% valid Samples over presence.

## Calibration

Optional, once, from the phone page **Calibrate**; shown on the dashboard **Calibration** page; completed by the `/calibrate` skill.

- **Height** gives the real scale: metres per pixel = the user's shoulder→hip length / its length in pixels. That length comes from the side standing photo (height × trunk px / silhouette px) or else 0.29 × height. Without a height, MediaPipe's average body is used.
- **Relaxed standing photo, side**: the user's neutral neck, head, back and trunk. Seated medians are reported as a difference from it (`versus_standing_neutral`).
- **Relaxed standing photo, front**: shoulder and hip lines, sideways shift. Context only, never tracked, never a diagnosis.
- **Desk photos**: context for Claude.
- **Workstation**: the phone doesn't move during a Session, so the desk is visible in its frames. Claude marks points (monitor, laptop, keyboard, desk, seat, backrest, floor) on a frame with a coordinate grid; `workstation.py` converts them into body-relative metres; the dashboard draws them in 3D around the body. Widths can't be seen from the side and use standard sizes.

## Improvement cycle

Baseline 1 → Baseline 2 → one Intervention → Reassessment → keep or revert.

- **Reference Variability**: the change a Metric must exceed to count. It is the largest of three values (`history.reference_variability`), and the report says which one decided:
  - *floor*: noise floor of the measurement, per Metric (`RV_FLOOR`);
  - *day to day*: √2 × the standard deviation of the Baseline medians, i.e. the typical difference between two ordinary Sessions. With two Baselines it is their difference; with three or more all of them count. With a single Baseline (after a kept change) the previous value is reused;
  - *measurement noise*: 2 × the standard error of the difference between the Baseline mean and the Reassessment median. Each Session's `median_se` comes from the spread of its per-minute medians (1.25 × SD / √minutes), so a Session where you moved a lot is a less precise measurement.
  Summaries are recomputed from the Samples when an Intervention is evaluated, so older Sessions get the newer fields.
- **Discomfort**: rated 0–10 after each Session (neck, shoulders, upper back, lower back, wrists, legs).
- **Outcome**: *successful* if a target Metric moves the expected way by more than the Reference Variability and discomfort doesn't worsen; *comfort-only improvement* if only discomfort improves; otherwise *inconclusive*, with a probable cause (*no measurable effect*, *worse comfort*, *not comparable*, *not applied*).
- **Comparable Sessions**: same side, body scale within 10%, similar position in the image, same time of day band. Otherwise flagged, never hidden.
- **Plateau**: three inconclusive in a row, or nothing left in the library that a Finding justifies.
- Interventions come only from `docs/intervention-library.md`.

## Known limits

- One phone camera, no depth: angles are approximate (a few degrees), widths are not measured.
- MediaPipe can take an object near the feet for an ankle.
- Lower legs are often hidden by the desk.
- The phone page is tested with Safari on iPhone. Android Chrome should work but is untested.
