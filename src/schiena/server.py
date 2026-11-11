"""HTTP server: phone camera ingest, live analysis, dashboard API.

Two listeners share one app:
- ``http://127.0.0.1:<port>``  — the dashboard (this computer only; full API).
- ``https://<lan-ip>:<lan_port>`` — the phone (camera page + frame upload + photos only).
"""

from __future__ import annotations

import asyncio
import io
import json
import shutil
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, Response

from . import storage
from .calibration import analyse_front, analyse_side, trunk_metres, versus_neutral
from .findings import findings
from .history import plateau
from .camera import CameraPose, from_gravity, parse_gravity
from .pose import PoseEstimator, level, make_sample
from .session import (
    ABSENCE_MIN_S,
    SESSION_S,
    FramingGate,
    check_framing,
    comparability,
    seated_hip_y,
    is_absent,
    summarize,
)

ANALYSIS_INTERVAL_S = 1.0
PHONE_TIMEOUT_S = 6.0
LATE_GRACE_S = 15 * 60  # after the 30 minutes, wait this long for buffered frames before closing


class Live:
    """State of the live pipeline (one phone, one Session at a time).

    Frames carry the phone's capture time (``X-Captured-At``, epoch ms). Frames buffered on the
    phone during a Wi-Fi drop arrive late and are placed at their real time. Stretches with no
    frames at all become *interruptions* in the summary — neither presence nor Absence.
    """

    def __init__(self, estimator: PoseEstimator, frames_per_minute: float = 2.0, session_s: float = SESSION_S,
                 clock=time.time):
        self.estimator = estimator
        self.frames_per_minute = frames_per_minute
        self.session_s = session_s
        self.clock = clock
        self.clients: set[WebSocket] = set()
        self.state = "idle"  # idle → framing → recording → finished
        self.last_frame_at = 0.0  # server clock, any frame
        self.clock_offset: float | None = None  # server − phone clock (min over frames ≈ network delay)
        self.last_analysed_capture = -1e18
        self.lock = asyncio.Lock()
        self.gate = FramingGate()
        self.framing_progress = 0.0
        self.framing_problems: list[str] = []
        self.writer: storage.SessionWriter | None = None
        self.start_epoch = 0.0
        self.last_frame_saved_t = -1e9
        self.samples: list[dict] = []
        self.away_s = 0.0
        self.backlog = 0
        self.last_session_id: str | None = None
        self.latest_jpeg: bytes | None = None
        self._caffeinate = None
        self.trunk_m = trunk_metres(storage.load_profile())

    # ------------------------------------------------------------ status

    def phone_connected(self) -> bool:
        return self.clock() - self.last_frame_at < PHONE_TIMEOUT_S

    def elapsed(self) -> float:
        return min(self.session_s, self.clock() - self.start_epoch) if self.state == "recording" else 0.0

    def status(self) -> dict:
        return {
            "state": self.state,
            "phone_connected": self.phone_connected(),
            "session_id": self.writer.id if self.writer else self.last_session_id,
            "elapsed_s": round(self.elapsed(), 1),
            "session_s": self.session_s,
            "framing_progress": round(self.framing_progress, 2),
            "framing_problems": self.framing_problems,
            "away": self.away_s >= ABSENCE_MIN_S,
            "catching_up": self.backlog,
        }

    async def broadcast(self, message: dict | bytes) -> None:
        dead = []
        for ws in list(self.clients):
            try:
                if isinstance(message, bytes):
                    await ws.send_bytes(message)
                else:
                    await ws.send_text(json.dumps(message))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)

    # ------------------------------------------------------------ ingest

    def capture_time(self, captured_at_ms: float | None) -> float:
        """Phone capture time on the server clock."""
        now = self.clock()
        if captured_at_ms is None:
            return now
        phone = captured_at_ms / 1000
        delay = now - phone
        if self.clock_offset is None or delay < self.clock_offset:
            self.clock_offset = delay
        return phone + self.clock_offset

    async def on_frame(self, jpeg: bytes, captured_at_ms: float | None = None, backlog: int = 0,
                       cam: CameraPose | None = None) -> dict:
        async with self.lock:  # frames are handled one at a time, in arrival order
            now = self.clock()
            self.last_frame_at = now
            self.backlog = backlog
            cap = self.capture_time(captured_at_ms)
            late = now - cap > 3
            if self.state == "idle":
                self.state = "framing"
            if not late:
                self.latest_jpeg = jpeg
                await self.broadcast(jpeg)
            if self.state in ("framing", "recording") and cap - self.last_analysed_capture >= ANALYSIS_INTERVAL_S * 0.95:
                if not (self.state == "framing" and late):
                    self.last_analysed_capture = cap
                    sample = await asyncio.to_thread(self._estimate, jpeg, cap, cam)
                    if sample is not None:
                        await self._handle_sample(sample, jpeg, cap, live=not late)
            await self.check_end()
            return self.status()

    def _estimate(self, jpeg: bytes, cap: float, cam: CameraPose | None = None) -> dict | None:
        bgr = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
        if bgr is None:
            return None
        h, w = bgr.shape[:2]
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        result = self.estimator.estimate(rgb, int(cap * 1000))
        return make_sample(0.0, result, w, h, self.trunk_m, cam)

    async def calibrate(self, view: str, jpeg: bytes, cam: CameraPose | None = None) -> dict:
        """Analyse a relaxed standing photo (side or front) and store it in the profile."""
        bgr = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
        if bgr is None:
            return {"ok": False, "problems": ["Not an image."]}
        h, w = bgr.shape[:2]
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        async with self.lock:
            result = await asyncio.to_thread(self.estimator.estimate, rgb, int(self.clock() * 1000) + 1)
        lms, mask, _ = level(result, w, h, cam)
        r = analyse_side(lms, mask, w, h) if view == "side" else analyse_front(lms, w, h)
        if cam is not None:
            r["camera"] = cam.as_dict()
        if r["ok"]:
            d = storage.data_dir() / "photos"
            d.mkdir(parents=True, exist_ok=True)
            (d / f"standing_{view}.jpg").write_bytes(jpeg)
            r.update(photo=f"standing_{view}.jpg", measured_at=datetime.now().isoformat(timespec="seconds"))
            profile = storage.load_profile()
            profile[f"standing_{view}"] = r
            storage.save_profile(profile)
            self.trunk_m = trunk_metres(profile)
        return r

    def set_height(self, height_cm: float) -> dict:
        if not 100 <= height_cm <= 230:
            raise ValueError("height must be between 100 and 230 cm")
        profile = storage.load_profile()
        profile["height_cm"] = round(height_cm, 1)
        storage.save_profile(profile)
        self.trunk_m = trunk_metres(profile)
        return profile

    async def _handle_sample(self, sample: dict, jpeg: bytes, cap: float, live: bool) -> None:
        if self.state == "framing":
            check = check_framing(sample)
            self.framing_problems = check.problems
            self.framing_progress = self.gate.update(cap, check)
            if self.framing_progress >= 1.0:
                self.start(cap)
        elif self.state == "recording" and self.writer:
            t = round(cap - self.start_epoch, 1)
            if not 0 <= t < self.session_s:
                return
            sample["t"] = t
            self.writer.add_sample(sample)
            self.samples.append(sample)
            if t - self.last_frame_saved_t >= 60.0 / self.frames_per_minute or t < self.last_frame_saved_t:
                self.writer.add_frame(t, jpeg)
                self.last_frame_saved_t = max(self.last_frame_saved_t, t)
            if live:
                ref = seated_hip_y(self.samples[-600:])
                trunk = sample.get("trunk_len") or next((s["trunk_len"] for s in reversed(self.samples[-60:]) if s.get("trunk_len")), None)
                self.away_s = self.away_s + 1 if is_absent(sample, ref, trunk) else 0.0
        if live:
            await self.broadcast({"type": "sample", "sample": sample, "status": self.status()})

    async def check_end(self) -> None:
        """Close the Session when its time is up — waiting a while for frames buffered on the phone."""
        if self.state != "recording":
            return
        over = self.clock() - self.start_epoch - self.session_s
        caught_up = self.phone_connected() and self.backlog == 0
        if over >= 0 and (caught_up or over > LATE_GRACE_S):
            await self.stop()

    async def watchdog(self) -> None:
        while True:
            await asyncio.sleep(2)
            async with self.lock:
                await self.check_end()
            if self.state == "recording" and not self.phone_connected():
                await self.broadcast({"type": "status", "status": self.status()})

    # ------------------------------------------------------------ session control

    def start(self, at: float | None = None) -> None:
        start = at if at is not None else self.clock()
        sid = storage.new_session_id(datetime.fromtimestamp(start))
        self.writer = storage.SessionWriter(sid, {"started_at": datetime.fromtimestamp(start).isoformat(timespec="seconds"),
                                                  "status": "recording", "frames_per_minute": self.frames_per_minute,
                                                  "session_s": self.session_s})
        self.state = "recording"
        self.start_epoch = start
        self.last_frame_saved_t = -1e9
        self.samples = []
        self.away_s = 0.0
        self.framing_problems = []
        self._keep_awake(True)

    def _keep_awake(self, on: bool) -> None:
        """macOS: keep the Mac from idle-sleeping during a Session."""
        import os
        import subprocess

        if on and self._caffeinate is None and shutil.which("caffeinate"):
            self._caffeinate = subprocess.Popen(["caffeinate", "-i", "-w", str(os.getpid())])
        elif not on and self._caffeinate is not None:
            self._caffeinate.terminate()
            self._caffeinate = None

    async def stop(self) -> dict | None:
        if not self.writer:
            self.state = "idle"
            return None
        duration = min(self.session_s, self.clock() - self.start_epoch)
        summary = summarize(self.samples, self.writer.meta["started_at"], duration) if self.samples else None
        meta = self.writer.finish({"status": "finished", "duration_s": round(duration, 1), "summary": summary})
        self.last_session_id = self.writer.id
        self.writer = None
        self.state = "finished"
        self.gate = FramingGate()
        self.framing_progress = 0.0
        self._keep_awake(False)
        await self.broadcast({"type": "finished", "session_id": self.last_session_id, "status": self.status()})
        return meta

    def reset(self) -> None:
        if self.state == "finished":
            self.state = "framing" if self.phone_connected() else "idle"


def recover_sessions(session_s: float = SESSION_S) -> list[str]:
    """Finish Sessions left 'recording' by a crash, a closed terminal or a sleeping computer."""
    recovered = []
    for meta in storage.list_sessions():
        if meta.get("status") != "recording":
            continue
        samples = storage.read_samples(meta["id"])
        planned = meta.get("session_s", session_s)
        last = max((s["t"] for s in samples), default=0.0)
        started = datetime.fromisoformat(meta["started_at"]).timestamp()
        duration = min(planned, max(last + 1, time.time() - started))
        path = storage.session_dir(meta["id"]) / "session.json"
        raw = storage.read_json(path)
        raw.update({"status": "finished", "recovered": True, "duration_s": round(duration, 1),
                    "summary": summarize(samples, raw["started_at"], duration) if samples else None})
        storage.write_json(path, raw)
        recovered.append(meta["id"])
    return recovered


def refresh_summaries() -> list[str]:
    """Recompute stored summaries written by an older version of summarize()."""
    from .session import SUMMARY_VERSION

    refreshed = []
    for meta in storage.list_sessions():
        summ = meta.get("summary")
        if meta.get("status") != "finished" or not summ or summ.get("version", 1) >= SUMMARY_VERSION:
            continue
        samples = storage.read_samples(meta["id"])
        if not samples:
            continue
        path = storage.session_dir(meta["id"]) / "session.json"
        raw = storage.read_json(path)
        raw["summary"] = summarize(samples, raw["started_at"], raw.get("duration_s"))
        storage.write_json(path, raw)
        refreshed.append(meta["id"])
    return refreshed


# ---------------------------------------------------------------- app


PHONE_PATHS = ("/camera", "/assets/", "/api/camera/", "/api/photos", "/favicon", "/icon")


def create_app(live: Live, web_dist: Path, lan_url: str, lan_port: int) -> FastAPI:
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(app):
        for sid in recover_sessions(live.session_s):
            print(f"Recovered interrupted Session {sid}", flush=True)
        refreshed = await asyncio.to_thread(refresh_summaries)
        if refreshed:
            print(f"Updated the summaries of {len(refreshed)} Session(s)", flush=True)
        task = asyncio.create_task(live.watchdog())
        yield
        task.cancel()
        if live.state == "recording":
            await live.stop()

    app = FastAPI(title="Schiena", docs_url=None, redoc_url=None, lifespan=lifespan)

    @app.middleware("http")
    async def phone_listener_is_limited(request: Request, call_next):
        # The LAN listener only exposes what the phone needs; data stays on this computer.
        port = request.scope.get("server", (None, None))[1]
        path = request.url.path
        if port == lan_port and not (path == "/" or path.startswith(PHONE_PATHS)):
            return PlainTextResponse("Not available on the network listener", status_code=404)
        if port == lan_port and path == "/":
            return Response(status_code=307, headers={"Location": "/camera"})
        return await call_next(request)

    # ---------------- phone

    @app.post("/api/camera/frame")
    async def camera_frame(request: Request):
        body = await request.body()
        if not body or len(body) > 4_000_000:
            raise HTTPException(400, "expected a JPEG body")
        captured = request.headers.get("x-captured-at")
        backlog = int(request.headers.get("x-backlog", "0") or 0)
        cam = from_gravity(parse_gravity(request.headers.get("x-gravity")))
        return await live.on_frame(body, float(captured) if captured else None, backlog, cam)

    @app.get("/api/camera/status")
    async def camera_status():
        return {**live.status(), "height_cm": storage.load_profile().get("height_cm")}

    @app.post("/api/camera/calibration/{view}")
    async def calibration(view: str, request: Request):
        if view not in ("side", "front"):
            raise HTTPException(404)
        body = await request.body()
        r = await live.calibrate(view, body, from_gravity(parse_gravity(request.headers.get("x-gravity"))))
        return {k: v for k, v in r.items() if k not in ("kp", "back")}

    @app.post("/api/camera/height")
    async def camera_height(request: Request):
        try:
            p = live.set_height(float((await request.json())["height_cm"]))
        except (ValueError, KeyError, TypeError) as e:
            raise HTTPException(400, str(e))
        return {"height_cm": p["height_cm"]}

    @app.get("/api/profile")
    async def profile():
        p = storage.load_profile()
        p["trunk_m"] = trunk_metres(p)
        return p

    @app.put("/api/profile")
    async def put_profile(request: Request):
        try:
            live.set_height(float((await request.json())["height_cm"]))
        except (ValueError, KeyError, TypeError) as e:
            raise HTTPException(400, str(e))
        return await profile()

    @app.post("/api/camera/stop")
    async def camera_stop():
        await live.stop()
        return live.status()

    @app.post("/api/camera/again")
    async def camera_again():
        live.reset()
        return live.status()

    @app.post("/api/photos")
    async def upload_photo(request: Request):
        body = await request.body()
        if not body:
            raise HTTPException(400, "empty")
        d = storage.data_dir() / "photos"
        d.mkdir(parents=True, exist_ok=True)
        name = datetime.now().strftime("%Y-%m-%d_%H-%M-%S-%f") + ".jpg"
        (d / name).write_bytes(body)
        return {"saved": name}

    # ---------------- dashboard

    @app.websocket("/ws/live")
    async def ws_live(ws: WebSocket):
        await ws.accept()
        live.clients.add(ws)
        try:
            await ws.send_text(json.dumps({"type": "status", "status": live.status()}))
            if live.latest_jpeg and live.phone_connected():
                await ws.send_bytes(live.latest_jpeg)
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            live.clients.discard(ws)

    @app.get("/api/status")
    async def status():
        return {**live.status(), "camera_url": f"{lan_url}/camera"}

    @app.post("/api/session/start")
    async def session_start():
        if live.state != "recording":
            if not live.phone_connected():
                raise HTTPException(409, "phone not connected")
            live.start()
        return live.status()

    @app.post("/api/session/stop")
    async def session_stop():
        await live.stop()
        return live.status()

    @app.get("/api/qr.svg")
    async def qr():
        import qrcode
        import qrcode.image.svg

        img = qrcode.make(f"{lan_url}/camera", image_factory=qrcode.image.svg.SvgPathImage, border=1)
        buf = io.BytesIO()
        img.save(buf)
        return Response(buf.getvalue(), media_type="image/svg+xml")

    @app.get("/api/sessions")
    async def sessions():
        out = []
        for s in storage.list_sessions():
            out.append({k: s.get(k) for k in ("id", "started_at", "status", "duration_s", "summary", "discomfort", "has_report", "label")})
        return out

    @app.get("/api/sessions/{sid}")
    async def session(sid: str):
        meta = storage.load_session(sid)
        if not meta:
            raise HTTPException(404)
        if meta.get("summary"):
            meta["findings"] = findings(meta["summary"])
            meta["versus_neutral"] = versus_neutral(meta["summary"], storage.load_profile())
        return meta

    @app.get("/api/sessions/{sid}/samples")
    async def samples(sid: str):
        path = storage.session_dir(sid) / "samples.jsonl"
        if not path.exists():
            raise HTTPException(404)
        return Response("[" + ",".join(l for l in path.read_text().splitlines() if l.strip()) + "]", media_type="application/json")

    @app.get("/api/sessions/{sid}/frames/{name}")
    async def frame(sid: str, name: str):
        path = storage.session_dir(sid) / "frames" / name
        if "/" in name or not path.exists():
            raise HTTPException(404)
        return FileResponse(path, media_type="image/jpeg")

    @app.get("/api/sessions/{sid}/report")
    async def report(sid: str):
        path = storage.session_dir(sid) / "report.md"
        if not path.exists():
            raise HTTPException(404)
        return PlainTextResponse(path.read_text())

    @app.put("/api/sessions/{sid}/discomfort")
    async def discomfort(sid: str, request: Request):
        values = await request.json()
        path = storage.session_dir(sid) / "session.json"
        meta = storage.read_json(path)
        if meta is None:
            raise HTTPException(404)
        meta["discomfort"] = {k: int(v) for k, v in values.items() if v is not None and 0 <= int(v) <= 10}
        storage.write_json(path, meta)
        return meta["discomfort"]

    @app.delete("/api/sessions/{sid}")
    async def delete_session(sid: str):
        d = storage.session_dir(sid)
        if not d.exists() or (live.writer and live.writer.id == sid):
            raise HTTPException(409)
        shutil.rmtree(d)
        return {"deleted": sid}

    @app.get("/api/compare")
    async def compare(a: str, b: str):
        sa, sb = storage.load_session(a), storage.load_session(b)
        if not sa or not sb or not sa.get("summary") or not sb.get("summary"):
            raise HTTPException(404)
        return {"limited_comparability": comparability(sa["summary"], sb["summary"])}

    @app.get("/api/workstation")
    async def workstation():
        return storage.read_json(storage.workstation_path(), None)

    @app.get("/api/history")
    async def history():
        h = storage.load_history()
        h["plateau"] = plateau(h["interventions"])
        return h

    @app.get("/api/photos")
    async def photos():
        d = storage.data_dir() / "photos"
        return sorted(p.name for p in d.glob("*.jpg")) if d.exists() else []

    @app.get("/api/photos/{name}")
    async def photo(name: str):
        path = storage.data_dir() / "photos" / name
        if "/" in name or not path.exists():
            raise HTTPException(404)
        return FileResponse(path)

    # ---------------- web app

    index = web_dist / "index.html"

    @app.get("/{path:path}")
    async def spa(path: str):
        target = (web_dist / path).resolve()
        if path and target.is_file() and web_dist.resolve() in target.parents:
            return FileResponse(target)
        if index.exists():
            return HTMLResponse(index.read_text())
        return HTMLResponse("<h1>Schiena</h1><p>The web UI is not built. Run <code>npm --prefix web ci && npm --prefix web run build</code>.</p>")

    return app
