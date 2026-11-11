"""Live pipeline with a fake pose engine: framing → recording → stop → saved Session."""

import time

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from schiena import server as srv
from schiena.pose import PoseResult
from schiena.posture import Landmark

from .test_posture import body


class FakeEstimator:
    def estimate(self, rgb, timestamp_ms):
        # scale the synthetic body (1000×1000 space) to the 720×1280 test image
        lms = [Landmark(l.x * 0.5, l.y * 0.9 + 100, l.visibility) for l in body()]
        for left, right in ((7, 8), (11, 12), (13, 14), (15, 16), (23, 24), (25, 26), (27, 28)):
            r = lms[right]
            lms[left] = Landmark(r.x + 5, r.y, 0.3)  # far side: hidden but estimated next to the near side
        return PoseResult(lms, None, [(0, 0, 0)] * 33)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SCHIENA_DATA", str(tmp_path))
    monkeypatch.setattr(srv, "ANALYSIS_INTERVAL_S", 0.0)
    live = srv.Live(FakeEstimator(), session_s=600)
    live.gate.hold_s = 0.05
    app = srv.create_app(live, tmp_path / "dist", "https://lan:1", lan_port=1)
    with TestClient(app) as c:
        yield c, live


def jpeg():
    ok, buf = cv2.imencode(".jpg", np.zeros((1280, 720, 3), np.uint8))
    return buf.tobytes()


def send(c, n):
    for _ in range(n):
        c.post("/api/camera/frame", content=jpeg())
        time.sleep(0.06)


def test_session_starts_when_framed_and_is_saved(client):
    c, live = client
    send(c, 4)
    assert c.get("/api/status").json()["state"] == "recording"
    send(c, 5)
    sid = c.get("/api/status").json()["session_id"]
    assert c.post("/api/session/stop").json()["state"] == "finished"
    meta = c.get(f"/api/sessions/{sid}").json()
    assert meta["summary"]["valid_percent"] == 100.0
    assert meta["frames"], "the first frame is always saved"
    samples = c.get(f"/api/sessions/{sid}/samples").json()
    assert samples and samples[0]["metrics"]["trunk"] == pytest.approx(5.6, abs=0.1)  # 10° body, anisotropically scaled
    r = c.put(f"/api/sessions/{sid}/discomfort", json={"neck": 3, "legs": 11})
    assert r.json() == {"neck": 3}



def test_phone_tilt_is_recorded_and_undone(client):
    """The phone sends its gravity: a phone leaning 5° makes the image lean, the server levels it."""
    from .test_camera import gravity_for

    c, live = client
    header = {"x-gravity": ",".join(f"{v:.4f}" for v in gravity_for(roll=5.0))}
    for _ in range(4):
        c.post("/api/camera/frame", content=jpeg(), headers=header)
        time.sleep(0.06)
    sid = c.get("/api/status").json()["session_id"]
    c.post("/api/session/stop")
    s = c.get(f"/api/sessions/{sid}/samples").json()[0]
    assert s["camera"] == {"roll": pytest.approx(5.0, abs=0.01), "pitch": pytest.approx(0.0, abs=0.01)}
    # the fake engine always returns the same image points, so levelling them changes the angle
    assert abs(s["metrics"]["trunk"] - 5.6) > 3

def test_lan_listener_only_exposes_the_camera():
    # The port check happens in middleware: requests on the LAN port can't read data.
    live = srv.Live(FakeEstimator())
    app = srv.create_app(live, __import__("pathlib").Path("/nonexistent"), "https://lan:1", lan_port=80)
    with TestClient(app, base_url="http://testserver:80") as c:
        assert c.get("/api/sessions").status_code == 404
        assert c.get("/", follow_redirects=False).headers["location"] == "/camera"


# ---------------------------------------------------------------- interruptions (fake clock)

import asyncio

from schiena import storage


class Clock:
    def __init__(self):
        self.now = 1_800_000_000.0

    def __call__(self):
        return self.now


def make_live(tmp_path, monkeypatch, session_s=600):
    monkeypatch.setenv("SCHIENA_DATA", str(tmp_path))
    clock = Clock()
    live = srv.Live(FakeEstimator(), session_s=session_s, clock=clock)
    live._keep_awake = lambda on: None
    return live, clock


def run_frames(live, clock, seconds, start_phone_t=None, captured=True, backlog=0):
    """One frame per second; returns the last status."""
    async def go():
        st = None
        for i in range(seconds):
            phone_t = (start_phone_t if start_phone_t is not None else clock.now) + i
            if start_phone_t is None:
                clock.now += 1
                phone_t = clock.now
            st = await live.on_frame(jpeg(), phone_t * 1000 if captured else None, backlog)
        return st
    return asyncio.run(go())


def test_wifi_drop_frames_buffered_on_phone_are_placed_at_their_time(tmp_path, monkeypatch):
    live, clock = make_live(tmp_path, monkeypatch)
    run_frames(live, clock, 10)                       # framing → recording
    assert live.state == "recording"
    run_frames(live, clock, 60)                       # 1 min live
    drop_start = clock.now
    clock.now += 120                                  # 2 min offline: phone buffers frames
    run_frames(live, clock, 120, start_phone_t=drop_start + 1, backlog=5)  # upload backlog late
    run_frames(live, clock, 30)                       # live again
    asyncio.run(live.stop())
    summ = storage.load_session(live.last_session_id)["summary"]
    assert summ["interruptions"] == []                # nothing lost
    assert summ["valid_percent"] == 100.0


def test_phone_offline_becomes_an_interruption_and_session_closes_itself(tmp_path, monkeypatch):
    live, clock = make_live(tmp_path, monkeypatch, session_s=300)
    run_frames(live, clock, 10)
    run_frames(live, clock, 100)                      # then the phone dies
    clock.now += srv.LATE_GRACE_S + 400
    asyncio.run(live.check_end())
    assert live.state == "finished"
    summ = storage.load_session(live.last_session_id)["summary"]
    assert summ["interrupted_s"] > 150 and summ["absences"] == []


def test_recording_continues_when_the_phone_comes_back(tmp_path, monkeypatch):
    live, clock = make_live(tmp_path, monkeypatch)
    run_frames(live, clock, 10)
    sid = live.writer.id
    run_frames(live, clock, 30)
    clock.now += 60                                   # a phone call: no frames, nothing buffered
    run_frames(live, clock, 30)
    assert live.state == "recording" and live.writer.id == sid
    asyncio.run(live.stop())
    summ = storage.load_session(sid)["summary"]
    assert len(summ["interruptions"]) == 1 and 55 <= summ["interrupted_s"] <= 62


def test_unfinished_session_is_recovered_on_startup(tmp_path, monkeypatch):
    live, clock = make_live(tmp_path, monkeypatch)
    run_frames(live, clock, 10)
    run_frames(live, clock, 40)
    sid = live.writer.id                              # server killed here: never stopped
    assert srv.recover_sessions() == [sid]
    meta = storage.load_session(sid)
    assert meta["status"] == "finished" and meta["recovered"] and meta["summary"]["presence_s"] > 30
