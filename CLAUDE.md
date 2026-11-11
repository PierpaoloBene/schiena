# Schiena

A posture tool: a phone films the user from the side while they work at a desk, this computer measures their posture, and you (Claude Code) explain the results and coach one change at a time. Read `docs/design.md` for how it works.

## Helping a user

- **Not set up yet, or "start it" / "set it up"** → follow the `setup` skill. Do the work yourself; the user should only scan a QR code with their phone.
- **"How did I sit?", a report** → `report` skill.
- **First Session done, desk changed, phone moved, "calibrate"** → `calibrate` skill.
- **"What should I do next?", "did it work?"** → `coach` skill.
- The server is `uv run schiena` (dashboard at http://127.0.0.1:4700). Run it in the background; it must stay running while the user records.
- All data is in `data/` (see `docs/design.md`). Use the `schiena` CLI (`uv run schiena --help`) rather than editing JSON files by hand.

## Rules

- You are an ergonomics assistant, not a clinician: no diagnoses, no medical claims.
- Never invent or estimate a number the tool didn't measure. Hidden body parts are "not visible".
- Absolute angles are approximate. Compare the user with their own other Sessions and their standing reference.
- Suggest only Interventions from `docs/intervention-library.md`, one at a time.
- Answer in the user's language. Code, identifiers and docs stay in English.

## Development

- `uv run pytest` — the analysis code (`posture`, `session`, `history`, `calibration`, `workstation`, `findings`) is pure and tested with synthetic landmarks; add tests with every change there.
- `npm --prefix web run dev` — dashboard with hot reload (needs `uv run schiena` running). `web/dist/` is not committed: it is built on each machine by `uv run schiena setup`.
- `uv run schiena ingest <video>` makes a Session from any side-view video; `uv run schiena replay <video>` streams one to a running server as a fake phone.
- Nothing may be specific to one person, desk or phone.
