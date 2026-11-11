"""`schiena` command line. Claude Code's skills drive the tool through these commands."""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import statistics
import subprocess
import sys
import time
import webbrowser
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web"


def models_dir() -> Path:
    return ROOT / "models"


def _estimator(variant: str = "heavy"):
    from .pose import MediaPipeEstimator, ensure_model

    return MediaPipeEstimator(ensure_model(models_dir(), variant))


def _resolve(sid: str) -> str:
    from . import storage

    if sid == "latest":
        sessions = [s for s in storage.list_sessions() if s.get("summary")]
        if not sessions:
            sys.exit("No finished Sessions yet.")
        return sessions[0]["id"]
    if not storage.session_dir(sid).exists():
        sys.exit(f"No Session {sid!r}.")
    return sid


def _out(value) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------- serve


def build_web(force: bool = False) -> None:
    dist = WEB / "dist" / "index.html"
    if dist.exists() and not force:
        return
    npm = shutil.which("npm")
    if not npm:
        print("! Node.js/npm not found: the dashboard cannot be built. Install Node 20+ and run again.")
        return
    print("Building the dashboard …", flush=True)
    if not (WEB / "node_modules").exists():
        subprocess.run([npm, "ci" if (WEB / "package-lock.json").exists() else "install"], cwd=WEB, check=True)
    subprocess.run([npm, "run", "build"], cwd=WEB, check=True)


def _port_free(host: str, port: int) -> bool:
    import socket

    with socket.socket() as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # like uvicorn: ignore TIME_WAIT after a restart
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


def cmd_serve(a) -> None:
    import uvicorn

    from .certs import ensure_certificate, lan_ip
    from .server import Live, create_app

    for host, port in (("127.0.0.1", a.port), ("0.0.0.0", a.lan_port)):
        if not _port_free(host, port):
            sys.exit(f"Port {port} is already in use. Is Schiena already running? Otherwise pick another with --port / --lan-port.")
    build_web()
    ip = lan_ip()
    cert, key = ensure_certificate(ROOT / "certs", ip)
    lan_url = f"https://{ip}:{a.lan_port}"
    live = Live(_estimator(a.model), frames_per_minute=a.frames_per_minute, session_s=a.minutes * 60)
    app = create_app(live, WEB / "dist", lan_url, a.lan_port)

    dashboard = f"http://127.0.0.1:{a.port}"
    print(f"\n  Schiena is running\n  Dashboard (this computer): {dashboard}\n  Phone (same Wi-Fi):   {lan_url}/camera\n", flush=True)

    servers = [
        uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=a.port, log_level="warning")),
        uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=a.lan_port, log_level="warning",
                                      ssl_certfile=str(cert), ssl_keyfile=str(key))),
    ]

    async def main():
        if not a.no_browser:
            asyncio.get_running_loop().call_later(1.5, webbrowser.open, dashboard)
        await asyncio.gather(*(s.serve() for s in servers))

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass


# ---------------------------------------------------------------- video input


def _video_frames(path: Path, fps: float):
    import cv2

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        sys.exit(f"Cannot open {path}")
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, round(src_fps / fps))
    i = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if i % step == 0:
            yield i / src_fps, frame
        i += 1


def cmd_ingest(a) -> None:
    """Create a Session from a video file (e.g. recorded with the phone's Camera app)."""
    import cv2

    from . import storage
    from .pose import make_sample
    from .session import summarize

    from .calibration import trunk_metres

    est = _estimator(a.model)
    trunk_m = trunk_metres(storage.load_profile())
    started = datetime.fromisoformat(a.started_at) if a.started_at else datetime.fromtimestamp(Path(a.video).stat().st_mtime)
    sid = storage.new_session_id(started)
    w = storage.SessionWriter(sid, {"started_at": started.isoformat(timespec="seconds"), "status": "recording",
                                    "source": Path(a.video).name, "frames_per_minute": a.frames_per_minute})
    samples, last_saved, duration = [], -1e9, 0.0
    for t, bgr in _video_frames(Path(a.video), 1.0):
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        s = make_sample(t, est.estimate(rgb, int(t * 1000)), bgr.shape[1], bgr.shape[0], trunk_m)
        w.add_sample(s)
        samples.append(s)
        if t - last_saved >= 60 / a.frames_per_minute:
            ok, jpeg = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 80])
            w.add_frame(t, jpeg.tobytes())
            last_saved = t
        duration = t + 1
    summary = summarize(samples, w.meta["started_at"], duration)
    w.finish({"status": "finished", "duration_s": duration, "summary": summary})
    print(sid)


def cmd_replay(a) -> None:
    """Stream a video to a running server as if it were the phone (for development)."""
    import cv2
    import httpx

    url = a.url.rstrip("/") + "/api/camera/frame"
    with httpx.Client(verify=False, timeout=10) as client:
        start = time.monotonic()
        for t, bgr in _video_frames(Path(a.video), 2.0):
            wait = t / a.speed - (time.monotonic() - start)
            if wait > 0:
                time.sleep(wait)
            ok, jpeg = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 70])
            status = client.post(url, content=jpeg.tobytes(), headers={"content-type": "image/jpeg"}).json()
            print(f"\r{t:6.0f}s  {status['state']:<10} {status.get('elapsed_s', 0):6.0f}s", end="", flush=True)
    print()


# ---------------------------------------------------------------- data for Claude


def cmd_sessions(a) -> None:
    from . import storage

    for s in storage.list_sessions():
        summ = s.get("summary") or {}
        m = summ.get("metrics", {})
        label = f" [{s['label']}]" if s.get("label") else ""
        print(f"{s['id']}{label}  {summ.get('presence_s', 0) / 60:5.1f} min present  "
              f"valid {summ.get('valid_percent', 0):5.1f}%  {'accepted' if summ.get('accepted') else 'NOT accepted'}  "
              f"trunk {m.get('trunk', {}).get('median', '–')}  head {m.get('head_offset', {}).get('median', '–')}  "
              f"discomfort {'yes' if s.get('discomfort') else 'missing'}  report {'yes' if s.get('has_report') else 'no'}")


def cmd_summary(a) -> None:
    from . import storage
    from .findings import findings
    from .session import comparability

    sid = _resolve(a.session)
    meta = storage.load_session(sid)
    summ = meta.get("summary")
    if not summ:
        sys.exit("This Session has no summary (still recording?).")
    from .calibration import versus_neutral

    others = [s for s in storage.list_sessions() if s["id"] != sid and s.get("summary")]
    profile = storage.load_profile()
    standing = {k: profile[k] for k in ("standing_side", "standing_front") if k in profile}
    for v in standing.values():
        v.pop("kp", None), v.pop("back", None)
    _out({
        "session_id": sid,
        "summary": summ,
        "discomfort": meta.get("discomfort"),
        "findings": findings(summ),
        "versus_standing_neutral": versus_neutral(summ, profile),
        "profile": {"height_cm": profile.get("height_cm"), **standing},
        "frames_dir": str(storage.session_dir(sid) / "frames"),
        "comparable_with": {o["id"]: comparability(summ, o["summary"]) or "comparable" for o in others[:6]},
    })


def pick_frames(sid: str, count: int) -> list[str]:
    """Representative frames: start, end, extremes of the main Metrics, typical posture."""
    from . import storage

    d = storage.session_dir(sid) / "frames"
    names = sorted(p.name for p in d.glob("*.jpg"))
    if len(names) <= count:
        return [str(d / n) for n in names]
    by_t = {int(s["t"]): s for s in storage.read_samples(sid) if s.get("valid")}
    scored = []
    for n in names:
        s = by_t.get(int(n.split(".")[0]))
        if s:
            scored.append((n, s["metrics"]))
    chosen: list[str] = []

    def take(n):
        if n and n not in chosen:
            chosen.append(n)

    if scored:
        take(scored[0][0])
        take(scored[-1][0])
        for key in ("head_offset", "trunk", "back_rounding", "neck"):
            vals = [(m.get(key), n) for n, m in scored if m.get(key) is not None]
            if vals:
                med = statistics.median(v for v, _ in vals)
                take(max(vals)[1])
                take(min(vals)[1])
                take(min(vals, key=lambda x: abs(x[0] - med))[1])
    for n in names[:: max(1, len(names) // count)]:
        take(n)
    return [str(d / n) for n in sorted(chosen[:count])]


def cmd_frames(a) -> None:
    for p in pick_frames(_resolve(a.session), a.count):
        print(p)


def cmd_grid(a) -> None:
    """Overlay a labelled 10% grid on a frame so Claude can read point coordinates."""
    import cv2

    from . import storage

    sid = _resolve(a.session)
    d = storage.session_dir(sid) / "frames"
    name = a.frame or _best_reference_frame(sid)
    img = cv2.imread(str(d / name))
    h, w = img.shape[:2]
    for i in range(1, 20):
        major = i % 2 == 0
        color = (0, 255, 255) if major else (0, 160, 160)
        x, y = int(w * i / 20), int(h * i / 20)
        cv2.line(img, (x, 0), (x, h), color, 1)
        cv2.line(img, (0, y), (w, y), color, 1)
        if major:
            cv2.putText(img, f"{i / 20:.1f}", (x + 2, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)
            cv2.putText(img, f"{i / 20:.1f}", (2, y - 3), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)
    out = storage.session_dir(sid) / f"grid_{name}"
    cv2.imwrite(str(out), img)
    print(json.dumps({"frame": name, "grid_image": str(out), "width": w, "height": h}))


def _best_reference_frame(sid: str) -> str:
    """The saved frame whose Sample is valid and closest to the Session's typical posture."""
    from . import storage

    meta = storage.load_session(sid)
    by_t = {int(s["t"]): s for s in storage.read_samples(sid) if s.get("valid") and s.get("mpp")}
    med = (meta.get("summary") or {}).get("metrics", {}).get("trunk", {}).get("median", 0)
    candidates = [(abs(by_t[int(n.split('.')[0])]["metrics"]["trunk"] - med), n)
                  for n in meta["frames"] if int(n.split(".")[0]) in by_t]
    if not candidates:
        sys.exit("No frame with a valid Sample in this Session.")
    return min(candidates)[1]


def cmd_workstation(a) -> None:
    from . import storage
    from .workstation import reconstruct

    sid = _resolve(a.session)
    annotation = json.loads(Path(a.annotation).read_text()) if a.annotation != "-" else json.load(sys.stdin)
    name = annotation.get("frame") or a.frame or _best_reference_frame(sid)
    t = int(name.split(".")[0])
    samples = {int(s["t"]): s for s in storage.read_samples(sid)}
    sample = samples.get(t)
    if not sample:
        sys.exit(f"No Sample at t={t}")
    from .calibration import trunk_metres

    trunk_m = trunk_metres(storage.load_profile())
    if trunk_m and sample.get("trunk_len"):
        sample["mpp"] = trunk_m / sample["trunk_len"]  # calibrated scale beats the model's average body
    ws = reconstruct(annotation, sample)
    ws.update({"session_id": sid, "frame": name, "updated_at": datetime.now().isoformat(timespec="seconds"),
               "image_points": annotation.get("objects", {}), "side": sample["side"],
               "anchor": {"hip": sample["hip"], "w": sample["w"], "h": sample["h"], "mpp": sample["mpp"], "fwd": sample["fwd"]}})
    storage.write_json(storage.workstation_path(), ws)
    _out(ws)


def cmd_label(a) -> None:
    from . import storage

    sid = _resolve(a.session)
    path = storage.session_dir(sid) / "session.json"
    meta = storage.read_json(path)
    meta["label"] = a.label
    storage.write_json(path, meta)
    print(f"{sid}: {a.label}")


# ---------------------------------------------------------------- interventions


def _intervention(h: dict, iid: str) -> dict:
    for i in h["interventions"]:
        if i["id"] == iid:
            return i
    sys.exit(f"No Intervention {iid!r}.")


def _current_summary(session: dict) -> dict:
    """The Session summary recomputed from its Samples, so older Sessions get newer fields."""
    from . import storage
    from .session import summarize

    samples = storage.read_samples(session["id"])
    if not samples:
        return session["summary"]
    return summarize(samples, session["started_at"], session.get("duration_s"))


def cmd_intervention(a) -> None:
    from . import storage
    from .history import evaluate

    h = storage.load_history()
    now = datetime.now().isoformat(timespec="seconds")
    if a.action == "add":
        targets = []
        for t in a.target or []:
            metric, direction = t.split(":")
            targets.append({"metric": metric, "direction": direction})
        item = {
            "id": f"int-{len(h['interventions']) + 1:03d}",
            "library_id": a.library_id,
            "title": a.title,
            "kind": a.kind,
            "instructions": a.instructions,
            "targets": targets,
            "baselines": [_resolve(s) for s in (a.baselines.split(",") if a.baselines else [])],
            "reference_variability": json.loads(a.reference) if a.reference else None,
            "status": "proposed",
            "created_at": now,
        }
        h["interventions"].append(item)
        storage.save_history(h)
        _out(item)
        return
    item = _intervention(h, a.id)
    if a.action == "apply":
        item.update(status="applied", applied_at=now)
    elif a.action == "not-applied":
        item.update(status="evaluated", outcome="inconclusive", probable_cause="not applied", evaluated_at=now)
    elif a.action == "evaluate":
        reassessment = _resolve(a.reassessment)
        bases = [storage.load_session(b) for b in item["baselines"]]
        re = storage.load_session(reassessment)
        if not re.get("discomfort"):
            print("! The Reassessment has no discomfort rating yet: comfort is treated as unchanged.", file=sys.stderr)
        result = evaluate([_current_summary(b) for b in bases], _current_summary(re), item["targets"],
                          [b.get("discomfort") or {} for b in bases], re.get("discomfort"),
                          item.get("reference_variability"))
        item.update(status="evaluated", reassessment=reassessment, evaluated_at=now, **result)
    elif a.action == "keep":
        item["decision"] = "kept"
    elif a.action == "revert":
        item["decision"] = "reverted"
    storage.save_history(h)
    _out(item)


def cmd_calibrate(a) -> None:
    """Set the height and/or analyse standing photos taken some other way."""
    import cv2

    from . import storage
    from .calibration import analyse_front, analyse_side, trunk_metres

    profile = storage.load_profile()
    if a.height:
        profile["height_cm"] = a.height
    for view, path in (("side", a.side), ("front", a.front)):
        if not path:
            continue
        bgr = cv2.imread(path)
        if bgr is None:
            sys.exit(f"Cannot read {path}")
        h, w = bgr.shape[:2]
        res = _estimator().estimate(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB), 0)
        r = analyse_side(res.landmarks, res.mask, w, h) if view == "side" else analyse_front(res.landmarks, w, h)
        if not r["ok"]:
            sys.exit(f"{view} photo not usable: {'; '.join(r['problems'])}")
        d = storage.data_dir() / "photos"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"standing_{view}.jpg").write_bytes(Path(path).read_bytes())
        r.update(photo=f"standing_{view}.jpg", measured_at=datetime.now().isoformat(timespec="seconds"))
        profile[f"standing_{view}"] = r
    storage.save_profile(profile)
    shown = {k: v for k, v in profile.items()}
    for k in ("standing_side", "standing_front"):
        if k in shown:
            shown[k] = {kk: vv for kk, vv in shown[k].items() if kk not in ("kp", "back")}
    _out({**shown, "trunk_m": trunk_metres(profile)})


def cmd_history(a) -> None:
    from . import storage
    from .history import plateau

    h = storage.load_history()
    h["plateau"] = plateau(h["interventions"])
    _out(h)


# ---------------------------------------------------------------- doctor


def cmd_doctor(a) -> None:
    from .certs import lan_ip

    ok = True

    def check(label, good, hint=""):
        nonlocal ok
        ok &= bool(good)
        print(f"  {'✓' if good else '✗'} {label}" + ("" if good else f"  → {hint}"))

    print("Schiena doctor")
    check(f"Python {sys.version.split()[0]}", sys.version_info[:2] in ((3, 10), (3, 11), (3, 12)), "use Python 3.10–3.12 (uv handles this)")
    try:
        import mediapipe  # noqa: F401
        check("MediaPipe installed", True)
    except Exception as e:  # pragma: no cover
        check("MediaPipe installed", False, str(e))
    check("Pose model downloaded", any(models_dir().glob("*.task")), "run `uv run schiena setup`")
    check("Node.js available", shutil.which("npm"), "install Node 20+ (e.g. `brew install node`)")
    check("Dashboard built", (WEB / "dist" / "index.html").exists(), "run `uv run schiena setup`")
    ip = lan_ip()
    check(f"LAN address {ip}", not ip.startswith("127."), "connect this computer to the same Wi-Fi as the phone")
    print("All good." if ok else "Some checks failed.")
    sys.exit(0 if ok else 1)


def cmd_setup(a) -> None:
    from .certs import ensure_certificate, lan_ip
    from .pose import ensure_model

    ensure_model(models_dir(), a.model)
    build_web(force=True)
    ensure_certificate(ROOT / "certs", lan_ip())
    cmd_doctor(a)


# ---------------------------------------------------------------- main


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="schiena", description="Seated posture coach: phone camera, analysis on this computer, Claude Code as the coach.")
    sub = p.add_subparsers(dest="cmd")

    s = sub.add_parser("serve", help="start the server and open the dashboard (default)")
    s.add_argument("--port", type=int, default=4700)
    s.add_argument("--lan-port", type=int, default=4743)
    s.add_argument("--minutes", type=float, default=30)
    s.add_argument("--frames-per-minute", type=float, default=2)
    s.add_argument("--model", choices=["heavy", "full"], default="heavy")
    s.add_argument("--no-browser", action="store_true")
    s.set_defaults(func=cmd_serve)

    s = sub.add_parser("setup", help="download the model, build the dashboard, create the certificate")
    s.add_argument("--model", choices=["heavy", "full"], default="heavy")
    s.set_defaults(func=cmd_setup)
    sub.add_parser("doctor", help="check the installation").set_defaults(func=cmd_doctor)

    s = sub.add_parser("ingest", help="create a Session from a video file")
    s.add_argument("video")
    s.add_argument("--started-at", help="ISO time the video started (default: file time)")
    s.add_argument("--frames-per-minute", type=float, default=2)
    s.add_argument("--model", choices=["heavy", "full"], default="heavy")
    s.set_defaults(func=cmd_ingest)

    s = sub.add_parser("replay", help="stream a video to the running server as a fake phone")
    s.add_argument("video")
    s.add_argument("--url", default="http://127.0.0.1:4700")
    s.add_argument("--speed", type=float, default=1.0)
    s.set_defaults(func=cmd_replay)

    sub.add_parser("sessions", help="list Sessions").set_defaults(func=cmd_sessions)
    s = sub.add_parser("summary", help="Session summary, Findings and comparability (JSON)")
    s.add_argument("session", nargs="?", default="latest")
    s.set_defaults(func=cmd_summary)
    s = sub.add_parser("frames", help="paths of representative saved frames")
    s.add_argument("session", nargs="?", default="latest")
    s.add_argument("--count", type=int, default=8)
    s.set_defaults(func=cmd_frames)
    s = sub.add_parser("grid", help="frame with a coordinate grid, for locating Workstation objects")
    s.add_argument("session", nargs="?", default="latest")
    s.add_argument("--frame")
    s.set_defaults(func=cmd_grid)
    s = sub.add_parser("workstation", help="save the Workstation from annotated image points (JSON file or -)")
    s.add_argument("session")
    s.add_argument("annotation")
    s.add_argument("--frame")
    s.set_defaults(func=cmd_workstation)
    s = sub.add_parser("label", help="label a Session (e.g. 'baseline 1')")
    s.add_argument("session")
    s.add_argument("label")
    s.set_defaults(func=cmd_label)

    s = sub.add_parser("intervention", help="manage Interventions")
    s.add_argument("action", choices=["add", "apply", "not-applied", "evaluate", "keep", "revert"])
    s.add_argument("id", nargs="?")
    s.add_argument("--library-id")
    s.add_argument("--title")
    s.add_argument("--kind", choices=["physical", "behavioural"])
    s.add_argument("--instructions")
    s.add_argument("--target", action="append", help="metric:increase|decrease (repeatable)")
    s.add_argument("--baselines", help="comma-separated Session ids")
    s.add_argument("--reference", help="JSON Reference Variability to reuse, e.g. '{\"head_offset\": 0.04}'")
    s.add_argument("--reassessment")
    s.set_defaults(func=cmd_intervention)
    sub.add_parser("history", help="Interventions, Outcomes and Plateau (JSON)").set_defaults(func=cmd_history)
    s = sub.add_parser("calibrate", help="height and relaxed standing photos (usually done from the phone)")
    s.add_argument("--height", type=float, help="height in cm")
    s.add_argument("--side", help="photo standing relaxed, in profile")
    s.add_argument("--front", help="photo standing relaxed, facing the camera")
    s.set_defaults(func=cmd_calibrate)

    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or (argv[0].startswith("-") and argv[0] not in ("-h", "--help")):
        argv = ["serve", *argv]  # `schiena` alone (or with server options) starts the server
    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
