// Phone page: streams the front camera to the computer. No app, just the browser.
//
// Robustness:
// - every frame carries its capture time; when the computer can't be reached (Wi-Fi drop, computer asleep)
//   frames are queued on the phone (1/s, smaller, up to ~15 min) and uploaded when it's back;
// - if the camera is interrupted (phone call, Siri, app switch) it is restarted automatically;
// - if Safari reloads the page mid-Session, the page offers to resume the same Session.
import { useEffect, useRef, useState } from "react";
import { clock, Status } from "../lib";
import { Calibrate } from "./Calibrate";

const CAPTURE_INTERVAL_MS = 500;
const LIVE_MAX_SIDE = 1280;
const BACKLOG_MAX_SIDE = 800; // frames kept while offline are smaller
const BACKLOG_MAX = 900; // ≈ 15 min at 1 frame/s, ~30 MB

type Phase = "start" | "live" | "error" | "calibrate";
interface Frame { blob: Blob; at: number }

export function Camera() {
  const video = useRef<HTMLVideoElement>(null);
  const stream = useRef<MediaStream | null>(null);
  const queue = useRef<Frame[]>([]);
  const [phase, setPhase] = useState<Phase>("start");
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<Status | null>(null);
  const [offline, setOffline] = useState(false);
  const [queued, setQueued] = useState(0);
  const [cameraLost, setCameraLost] = useState(false);
  const [confirmStop, setConfirmStop] = useState(false);
  const statusRef = useRef<Status | null>(null);
  statusRef.current = status;

  // Is a Session already running (page reloaded mid-Session)?
  useEffect(() => {
    fetch("/api/camera/status").then((r) => r.json()).then(setStatus).catch(() => {});
  }, []);

  async function openCamera() {
    const s = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 720 } },
      audio: false,
    });
    stream.current?.getTracks().forEach((t) => t.stop());
    stream.current = s;
    const track = s.getVideoTracks()[0];
    track.onended = () => setCameraLost(true);
    track.onmute = () => setCameraLost(true);
    track.onunmute = () => setCameraLost(false);
    video.current!.srcObject = s;
    await video.current!.play();
    setCameraLost(false);
  }

  async function start() {
    try {
      await openCamera();
      setPhase("live");
    } catch (e) {
      setError(
        window.isSecureContext
          ? `Camera unavailable: ${(e as Error).message}. Allow camera access for this site in Safari settings.`
          : "This page must be opened over https:// to use the camera.",
      );
      setPhase("error");
    }
  }

  // Keep the screen awake, and recover the camera when the page comes back (after a call, Siri…).
  useEffect(() => {
    if (phase !== "live") return;
    let lock: WakeLockSentinel | null = null;
    const acquire = async () => {
      try {
        lock = await navigator.wakeLock?.request("screen");
      } catch {
        /* not supported: the user must disable auto-lock */
      }
    };
    const recover = async () => {
      const track = stream.current?.getVideoTracks()[0];
      try {
        if (!track || track.readyState === "ended") await openCamera();
        else await video.current?.play();
        setCameraLost(false);
      } catch {
        setCameraLost(true);
      }
    };
    acquire();
    const onVis = () => {
      if (document.visibilityState === "visible") {
        acquire();
        recover();
      }
    };
    document.addEventListener("visibilitychange", onVis);
    const health = window.setInterval(() => {
      const track = stream.current?.getVideoTracks()[0];
      if (document.visibilityState === "visible" && (!track || track.readyState === "ended" || track.muted)) recover();
    }, 3000);
    return () => {
      document.removeEventListener("visibilitychange", onVis);
      clearInterval(health);
      lock?.release();
    };
  }, [phase]);

  // Capture loop: a frame every 500 ms into the queue (only 1/s and smaller while a backlog builds up).
  useEffect(() => {
    if (phase !== "live") return;
    const canvas = document.createElement("canvas");
    let lastQueued = 0;
    const h = window.setInterval(async () => {
      const v = video.current;
      if (!v || !v.videoWidth || v.paused || statusRef.current?.state === "finished") return;
      const now = Date.now();
      const backlog = queue.current.length > 2;
      if (backlog && now - lastQueued < 950) return;
      const side = backlog ? BACKLOG_MAX_SIDE : LIVE_MAX_SIDE;
      const scale = Math.min(1, side / Math.max(v.videoWidth, v.videoHeight));
      canvas.width = Math.round(v.videoWidth * scale);
      canvas.height = Math.round(v.videoHeight * scale);
      canvas.getContext("2d")!.drawImage(v, 0, 0, canvas.width, canvas.height);
      const blob = await new Promise<Blob | null>((r) => canvas.toBlob(r, "image/jpeg", backlog ? 0.6 : 0.72));
      if (!blob) return;
      queue.current.push({ blob, at: now });
      lastQueued = now;
      if (queue.current.length > BACKLOG_MAX) queue.current.shift();
      setQueued(queue.current.length);
    }, CAPTURE_INTERVAL_MS);
    return () => clearInterval(h);
  }, [phase]);

  // Send loop: oldest frame first; on failure keep it and retry.
  useEffect(() => {
    if (phase !== "live") return;
    let stop = false;
    const loop = async () => {
      while (!stop) {
        const f = queue.current[0];
        if (!f) {
          await sleep(100);
          continue;
        }
        try {
          const r = await fetch("/api/camera/frame", {
            method: "POST",
            body: f.blob,
            headers: { "content-type": "image/jpeg", "x-captured-at": String(f.at), "x-backlog": String(queue.current.length - 1) },
          });
          if (!r.ok) throw new Error(String(r.status));
          setStatus(await r.json());
          queue.current.shift();
          // while live, drop stale frames so we never lag behind; the backlog keeps 1 frame/s anyway
          setQueued(queue.current.length);
          setOffline(false);
        } catch {
          setOffline(true);
          await sleep(2000);
        }
      }
    };
    loop();
    return () => {
      stop = true;
    };
  }, [phase]);

  async function post(path: string) {
    const r = await fetch(path, { method: "POST" });
    setStatus(await r.json());
  }

  const recording = status?.state === "recording";
  const finished = status?.state === "finished";
  const behind = queued > 2;

  if (phase === "calibrate") return <Calibrate onDone={() => setPhase("start")} />;

  return (
    <div className={`phone ${recording ? "phone-dark" : ""}`}>
      <video ref={video} playsInline muted autoPlay className={phase === "live" && (recording || finished) ? "phone-video hidden" : "phone-video"} />

      {phase === "start" && (
        <div className="phone-panel">
          <div className="phone-logo">{recording ? "Session in progress" : "Schiena"}</div>
          {recording ? (
            <p>The camera stopped (page reloaded?). Put the phone back in place and resume — the same Session continues.</p>
          ) : (
            <p>This phone becomes the camera. Place it at your side, upright, at chest height, 1.5–2 m away. Plug it into a charger if you can.</p>
          )}
          <button className="btn big" onClick={start}>{recording ? "Resume recording" : "Start camera"}</button>
          {!recording && (
            <>
              <button className="btn ghost" onClick={() => setPhase("calibrate")}>
                Calibrate: you + your desk
              </button>
              <p className="muted small">Optional, once: your height, a relaxed standing photo and a couple of desk photos.</p>
            </>
          )}
        </div>
      )}

      {phase === "error" && (
        <div className="phone-panel">
          <p className="error">{error}</p>
          <button className="btn" onClick={() => location.reload()}>Retry</button>
        </div>
      )}

      {phase === "live" && !recording && !finished && (
        <div className="phone-hud">
          <div className="phone-hud-top">{offline ? "Can't reach the computer…" : "Framing"}</div>
          <div className="phone-hud-bottom">
            {status?.framing_problems?.length ? (
              status.framing_problems.map((p) => <div key={p} className="framing-item bad">{p}</div>)
            ) : status ? (
              <div className="framing-item good">Looks good — sit naturally, starting…</div>
            ) : null}
            <div className="progress">
              <div style={{ width: `${(status?.framing_progress ?? 0) * 100}%` }} />
            </div>
          </div>
        </div>
      )}

      {phase === "live" && recording && status && (
        <div className="phone-recording" onClick={() => setConfirmStop(false)}>
          <div className={`rec-dot ${status.away || offline || cameraLost ? "away" : ""}`} />
          <div className="rec-time">{clock(status.elapsed_s)}</div>
          <div className="muted">
            {cameraLost
              ? "Camera interrupted — it will resume by itself"
              : offline
                ? `Computer unreachable — keeping frames on the phone (${queued})`
                : behind
                  ? `Catching up… ${queued} frames to send`
                  : status.away
                    ? "Away — the timer keeps running"
                    : `of ${clock(status.session_s)}`}
          </div>
          {cameraLost && (
            <button className="btn" onClick={(e) => { e.stopPropagation(); start(); }}>
              Resume camera
            </button>
          )}
          <p className="muted small rec-tip">Keep this screen open. You can lower the brightness.</p>
          <button
            className={`btn ${confirmStop ? "danger" : "ghost"}`}
            onClick={(e) => {
              e.stopPropagation();
              if (confirmStop) post("/api/camera/stop");
              setConfirmStop(!confirmStop);
            }}
          >
            {confirmStop ? "Tap again to stop" : "Stop"}
          </button>
        </div>
      )}

      {phase === "live" && finished && (
        <div className="phone-panel">
          <div className="phone-logo">Saved ✓</div>
          <p>Rate how you feel on the dashboard, then ask Claude for the report.</p>
          <button className="btn" onClick={() => post("/api/camera/again")}>New Session</button>
        </div>
      )}
    </div>
  );
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
