import { useEffect, useMemo, useRef, useState } from "react";
import { CameraFeed } from "../components/CameraFeed";
import { Sparkline } from "../components/Charts";
import { PostureScene } from "../components/Scene";
import { api, clock, fmt, LIVE_METRICS, METRIC_INFO, MetricKey, originFromSamples, Profile, Sample, SessionMeta, Status, toSagittal, Workstation } from "../lib";
import { navigate } from "../router";

function useLive() {
  const [status, setStatus] = useState<Status | null>(null);
  const [sample, setSample] = useState<Sample | null>(null);
  const [history, setHistory] = useState<Sample[]>([]);
  const [image, setImage] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);
  const [finished, setFinished] = useState<string | null>(null);
  const lastUrl = useRef<string | null>(null);

  useEffect(() => {
    let ws: WebSocket;
    let stop = false;
    let retry: number;
    const open = () => {
      ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/live`);
      ws.binaryType = "blob";
      ws.onopen = () => setConnected(true);
      ws.onclose = () => {
        setConnected(false);
        if (!stop) retry = window.setTimeout(open, 1500);
      };
      ws.onmessage = (ev) => {
        if (ev.data instanceof Blob) {
          const url = URL.createObjectURL(ev.data);
          if (lastUrl.current) URL.revokeObjectURL(lastUrl.current);
          lastUrl.current = url;
          setImage(url);
          return;
        }
        const msg = JSON.parse(ev.data);
        if (msg.status) setStatus(msg.status);
        if (msg.type === "sample") {
          setSample(msg.sample);
          setHistory((h) => [...h.slice(-299), msg.sample]);
        }
        if (msg.type === "finished") setFinished(msg.session_id);
      };
    };
    open();
    const poll = window.setInterval(() => api<Status>("/api/status").then(setStatus).catch(() => {}), 3000);
    return () => {
      stop = true;
      clearTimeout(retry);
      clearInterval(poll);
      ws?.close();
    };
  }, []);
  return { status, sample, history, image, connected, finished, setFinished };
}

function Onboarding({ cameraUrl }: { cameraUrl?: string }) {
  return (
    <div className="onboarding">
      <div className="onboarding-text">
        <h1>
          Sit as you always do.
          <br />
          <span className="gradient">We'll watch your back.</span>
        </h1>
        <ol className="steps">
          <li>
            <b>Scan the code</b> with your phone's camera (same Wi-Fi as this computer).
          </li>
          <li>
            The browser warns that the connection is not private (on iPhone: <b>Show Details → visit this website</b>). It's this computer's own
            certificate; you only do it once.
          </li>
          <li>
            Prop the phone <b>at your side</b>, upright, at chest height, about <b>1.5–2 m</b> away, so it sees you exactly in
            profile.
          </li>
          <li>
            <b>Sit down and work.</b> Recording starts by itself once you're framed, and stops after 30 minutes.
          </li>
        </ol>
        <p className="muted small">Video is never stored. Only body landmarks and two frames per minute stay on this computer.</p>
      </div>
      <div className="qr-card">
        <img src="/api/qr.svg" alt="QR code for the phone" />
        <code>{cameraUrl ?? "…"}</code>
        <span className="pulse-dot">waiting for the phone</span>
      </div>
    </div>
  );
}

function StateBadge({ status }: { status: Status }) {
  const offline = status.state === "recording" && !status.phone_connected;
  const label = offline
    ? "Phone offline — waiting"
    : status.catching_up
      ? `Catching up (${status.catching_up})`
      : { idle: "Phone offline", framing: "Framing", recording: status.away ? "Away" : "Recording", finished: "Saved" }[status.state];
  return <span className={`badge badge-${offline || status.away ? "away" : status.state}`}>{label}</span>;
}

export function Live() {
  const { status, sample, history, image, connected, finished, setFinished } = useLive();
  const [workstation, setWorkstation] = useState<Workstation | null>(null);
  const [usual, setUsual] = useState<SessionMeta | null>(null);
  const [focus, setFocus] = useState<MetricKey | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);

  useEffect(() => {
    api<Workstation | null>("/api/workstation").then(setWorkstation).catch(() => {});
    api<Profile>("/api/profile").then(setProfile).catch(() => {});
    api<SessionMeta[]>("/api/sessions").then((s) => setUsual(s.find((x) => x.summary?.accepted) ?? s.find((x) => x.summary) ?? null)).catch(() => {});
  }, []);

  // The desk is placed around this Session's usual hip (works even if the phone was moved).
  const origin = useMemo(() => originFromSamples(history), [history.length > 0 ? Math.floor(history.length / 30) : -1]); // eslint-disable-line react-hooks/exhaustive-deps
  const pose = useMemo(() => (sample ? toSagittal(sample, origin ?? workstation?.anchor) : null), [sample, workstation, origin]);

  if (!status) return <div className="page center muted">{connected ? "Loading…" : "Connecting to the Schiena server…"}</div>;
  if (!status.phone_connected && status.state !== "recording" && !finished) return <Onboarding cameraUrl={status.camera_url} />;

  const progress = status.state === "recording" ? status.elapsed_s / status.session_s : status.framing_progress;
  return (
    <div className="page live">
      {finished && (
        <div className="banner">
          Session saved. Rate how you feel and ask Claude for the report.
          <button className="btn" onClick={() => navigate(`/sessions/${finished}`)}>Open Session</button>
          <button className="btn ghost" onClick={() => setFinished(null)}>Dismiss</button>
        </div>
      )}
      <div className="live-grid">
        <section className="card scene-card">
          <div className="scene-overlay">
            <StateBadge status={status} />
            {status.state === "recording" && (
              <span className="timer">
                {clock(status.elapsed_s)} <span className="muted">/ {clock(status.session_s)}</span>
              </span>
            )}
            <div className="progress">
              <div style={{ width: `${Math.min(100, progress * 100)}%` }} />
            </div>
          </div>
          <PostureScene pose={pose} workstation={workstation} highlight={focus} height="100%" />
          <div className="scene-actions">
            {status.state === "framing" && (
              <button className="btn ghost" onClick={() => api("/api/session/start", { method: "POST" })}>Start anyway</button>
            )}
            {status.state === "recording" && (
              <button className="btn danger" onClick={() => api("/api/session/stop", { method: "POST" })}>Stop Session</button>
            )}
          </div>
        </section>

        <aside className="live-side">
          <section className="card">
            <CameraFeed imageUrl={status.phone_connected ? image : null} sample={sample} />
            {status.state === "framing" && (
              <div className="framing">
                {status.framing_problems.length ? (
                  status.framing_problems.map((p) => <div key={p} className="framing-item bad">{p}</div>)
                ) : (
                  <div className="framing-item good">Framing looks good — hold still, starting…</div>
                )}
              </div>
            )}
          </section>
        </aside>
      </div>

      <section className="metric-grid">
        {LIVE_METRICS.map((k) => {
          const v = sample?.valid ? sample.metrics?.[k] : null;
          const standing = profile?.standing_side?.ok ? profile.standing_side.metrics[k] : null;
          const ref = standing ?? usual?.summary?.metrics[k]?.median;
          const refLabel = standing != null ? "vs standing relaxed" : "vs your usual";
          const delta = v != null && ref != null ? v - ref : null;
          return (
            <button
              key={k}
              className={`metric-card ${focus === k ? "active" : ""}`}
              onMouseEnter={() => setFocus(k)}
              onMouseLeave={() => setFocus(null)}
              style={{ ["--accent" as string]: METRIC_INFO[k].color }}
            >
              <div className="metric-head">
                <span className="dot" />
                {METRIC_INFO[k].label}
              </div>
              <div className="metric-value">{fmt(k, v)}</div>
              <div className="metric-delta">
                {delta != null ? `${delta >= 0 ? "+" : ""}${fmt(k, delta)} ${refLabel}` : v == null ? "not visible" : " "}
              </div>
              <Sparkline values={history.map((s) => (s.valid ? s.metrics?.[k] : null))} color={METRIC_INFO[k].color} width={160} />
            </button>
          );
        })}
      </section>
    </div>
  );
}
