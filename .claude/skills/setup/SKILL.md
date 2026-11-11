---
name: setup
description: Install and start Schiena on this computer from a fresh clone. Use when the user asks to set up, install, start or run Schiena, or when `uv run schiena doctor` fails.
---

# Set up Schiena

Do every step yourself. The user should only have to scan a QR code with their phone at the end. Talk to them in their language, briefly.

1. **Check prerequisites**: `uv --version` and `node --version` (Node 20 or newer).
   - No `uv`: ask, then install it — macOS/Linux `curl -LsSf https://astral.sh/uv/install.sh | sh`, Windows `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`. Use the full path printed by the installer (e.g. `~/.local/bin/uv`) until the shell is restarted.
   - No Node: on macOS with Homebrew `brew install node`; on Linux the distribution's package or nodejs.org; otherwise ask the user to install Node 20+ from https://nodejs.org and tell you when done.
2. **Install**: from the repo root run `uv run schiena setup`. It installs the Python packages (uv fetches a suitable Python by itself), downloads the pose model (~30 MB) into `models/`, builds the dashboard into `web/dist/`, creates the HTTPS certificate in `certs/` and prints a checklist.
3. **Fix what the checklist reports.** If the LAN address starts with 127., the computer isn't on a network the phone can reach: ask the user to connect it to the same Wi-Fi as the phone.
4. **Start**: run `uv run schiena` in the background — it must keep running. It opens the dashboard at http://127.0.0.1:4700 and prints the phone address. If a port is busy: `uv run schiena --port 4800 --lan-port 4843`.
5. **Tell the user** what to do next, in a few lines:
   - scan the QR code on the dashboard with the phone (same Wi-Fi);
   - the browser warns that the connection isn't private: it's the computer's own certificate. On iPhone: *Show Details → visit this website*. Only once;
   - tap *Start camera*, allow the camera, put the phone beside them, upright, chest height, 1.5–2 m away;
   - sit down and work: recording starts by itself and lasts 30 minutes;
   - optional, once: *Calibrate* on the phone page (height, standing photos, desk photos);
   - afterwards: rate discomfort on the session page, then ask you for `/report`.

## Troubleshooting

- The phone can't open the page: different network (guest Wi-Fi), or the firewall blocks incoming connections to Python (macOS: System Settings → Network → Firewall).
- No camera prompt on iPhone: Settings → Apps → Safari → Camera → Ask.
- The phone screen locks: iOS older than 16.4 has no Wake Lock; set Auto-Lock to Never while recording.
- No phone: film a side view with any camera and run `uv run schiena ingest <video>`.
- `uv run schiena doctor` re-checks the installation.
