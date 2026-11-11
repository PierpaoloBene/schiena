// Phone: personal calibration — height + relaxed standing photos (side and front) on a timer.
import { useEffect, useRef, useState } from "react";
import { gravity, startGravity } from "../gravity";

type View = "side" | "front";
interface Result { ok: boolean; problems: string[] }

const TIMER_S = 10;

export function Calibrate({ onDone }: { onDone: () => void }) {
  const video = useRef<HTMLVideoElement>(null);
  const stream = useRef<MediaStream | null>(null);
  const [height, setHeight] = useState("");
  const [heightSaved, setHeightSaved] = useState(false);
  const [shooting, setShooting] = useState<View | null>(null);
  const [count, setCount] = useState(0);
  const [results, setResults] = useState<Partial<Record<View, Result | "busy">>>({});
  const [deskMsg, setDeskMsg] = useState<string | null>(null);

  async function uploadDesk(files: FileList | null) {
    if (!files?.length) return;
    setDeskMsg("Sending…");
    let n = 0;
    for (const f of Array.from(files)) {
      const bmp = await createImageBitmap(f);
      const scale = Math.min(1, 1600 / Math.max(bmp.width, bmp.height));
      const c = document.createElement("canvas");
      c.width = Math.round(bmp.width * scale);
      c.height = Math.round(bmp.height * scale);
      c.getContext("2d")!.drawImage(bmp, 0, 0, c.width, c.height);
      const blob = await new Promise<Blob | null>((r) => c.toBlob(r, "image/jpeg", 0.85));
      if (blob && (await fetch("/api/photos", { method: "POST", body: blob, headers: { "content-type": "image/jpeg" } })).ok) n++;
    }
    setDeskMsg(`${n} photo${n === 1 ? "" : "s"} sent ✓`);
  }

  useEffect(() => {
    fetch("/api/camera/status").then((r) => r.json()).then((s) => s.height_cm && (setHeight(String(s.height_cm)), setHeightSaved(true))).catch(() => {});
    return () => stream.current?.getTracks().forEach((t) => t.stop());
  }, []);

  async function saveHeight() {
    const r = await fetch("/api/camera/height", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ height_cm: Number(height) }),
    });
    setHeightSaved(r.ok);
  }

  async function upload(view: View, blob: Blob, g: string | null = null) {
    setResults((r) => ({ ...r, [view]: "busy" }));
    try {
      const r = await fetch(`/api/camera/calibration/${view}`, { method: "POST", body: blob, headers: { "content-type": "image/jpeg", ...(g ? { "x-gravity": g } : {}) } });
      const res: Result = r.ok ? await r.json() : { ok: false, problems: [`Server error ${r.status}`] };
      setResults((x) => ({ ...x, [view]: res }));
    } catch {
      setResults((x) => ({ ...x, [view]: { ok: false, problems: ["Can't reach the computer."] } }));
    }
  }

  async function shoot(view: View) {
    const motion = startGravity(); // inside the tap, before any await
    if (!stream.current) {
      stream.current = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "user", width: { ideal: 1920 }, height: { ideal: 1080 } },
        audio: false,
      });
    }
    setShooting(view);
    await new Promise((r) => requestAnimationFrame(r));
    video.current!.srcObject = stream.current;
    await video.current!.play();
    for (let i = TIMER_S; i > 0; i--) {
      setCount(i);
      await new Promise((r) => setTimeout(r, 1000));
    }
    setCount(0);
    await motion;
    const g = gravity();
    const v = video.current!;
    const c = document.createElement("canvas");
    c.width = v.videoWidth;
    c.height = v.videoHeight;
    c.getContext("2d")!.drawImage(v, 0, 0);
    const blob = await new Promise<Blob | null>((r) => c.toBlob(r, "image/jpeg", 0.9));
    setShooting(null);
    if (blob) await upload(view, blob, g);
  }

  async function fromFile(view: View, files: FileList | null) {
    const f = files?.[0];
    if (!f) return;
    const bmp = await createImageBitmap(f);
    const scale = Math.min(1, 1920 / Math.max(bmp.width, bmp.height));
    const c = document.createElement("canvas");
    c.width = Math.round(bmp.width * scale);
    c.height = Math.round(bmp.height * scale);
    c.getContext("2d")!.drawImage(bmp, 0, 0, c.width, c.height);
    const blob = await new Promise<Blob | null>((r) => c.toBlob(r, "image/jpeg", 0.9));
    if (blob) await upload(view, blob);
  }

  if (shooting) {
    return (
      <div className="phone">
        <video ref={video} playsInline muted autoPlay className="phone-video" />
        <div className="phone-hud">
          <div className="phone-hud-top">{shooting === "side" ? "Stand sideways, relaxed" : "Face the camera, relaxed"}</div>
          <div className="countdown">{count || "📸"}</div>
          <div className="phone-hud-bottom">
            <div className="framing-item good">Step back until your whole body, head to feet, is in the picture. Arms hanging, look straight ahead.</div>
          </div>
        </div>
      </div>
    );
  }

  const row = (view: View, title: string, hint: string) => {
    const r = results[view];
    return (
      <div className="calib-row">
        <div>
          <b>{title}</b>
          <div className="muted small">{hint}</div>
          {r === "busy" && <div className="muted small">Analysing…</div>}
          {r && r !== "busy" && (r.ok ? <div className="ok-text small">Saved ✓</div> : r.problems.map((p) => <div key={p} className="error small">{p}</div>))}
        </div>
        <div className="calib-actions">
          <button className="btn" onClick={() => shoot(view)}>{TIMER_S} s timer</button>
          <label className="btn ghost small">
            Upload
            <input type="file" accept="image/*" hidden onChange={(e) => fromFile(view, e.target.files)} />
          </label>
        </div>
      </div>
    );
  };

  return (
    <div className="phone phone-scroll">
      <video ref={video} playsInline muted className="phone-video hidden" />
      <div className="calib">
        <div className="calib-head">
          <div className="phone-logo">Calibration</div>
          <button className="btn ghost small" onClick={onDone}>Close</button>
        </div>
        <p className="muted">Optional, once. It makes distances real, lets Schiena compare how you sit with how you stand when relaxed, and helps Claude rebuild your desk.</p>
        <h3 className="calib-title">You</h3>
        <div className="calib-row">
          <div>
            <b>Your height</b>
            <div className="muted small">In centimetres</div>
          </div>
          <div className="calib-actions">
            <input
              className="input"
              inputMode="numeric"
              placeholder="178"
              value={height}
              onChange={(e) => {
                setHeight(e.target.value);
                setHeightSaved(false);
              }}
            />
            <button className="btn" disabled={heightSaved || !(Number(height) >= 100 && Number(height) <= 230)} onClick={saveHeight}>
              {heightSaved ? "Saved" : "Save"}
            </button>
          </div>
        </div>
        {row("side", "Standing, side view", "Your relaxed posture: the reference for your neck and back.")}
        {row("front", "Standing, front view", "Context only: shoulder and hip lines.")}
        <p className="muted small">For the timer: lean the phone upright somewhere at chest height, start it and step back 2–3 m.</p>
        <h3 className="calib-title">Your desk</h3>
        <div className="calib-row">
          <div>
            <b>Desk photos</b>
            <div className="muted small">One from the front (screens, keyboard, chair) and one from where the phone stands while recording.</div>
            {deskMsg && <div className="ok-text small">{deskMsg}</div>}
          </div>
          <div className="calib-actions">
            <label className="btn">
              Add
              <input type="file" accept="image/*" multiple hidden onChange={(e) => uploadDesk(e.target.files)} />
            </label>
          </div>
        </div>
        <p className="muted small">After your first Session, ask Claude <code>/calibrate</code>: it rebuilds the desk in 3D from what the phone saw.</p>
        <button className="btn big" onClick={onDone}>Done: back to the camera</button>
      </div>
    </div>
  );
}
