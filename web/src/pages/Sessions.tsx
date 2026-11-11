import { useEffect, useMemo, useState } from "react";
import Markdown from "react-markdown";
import { nearest, Timeline } from "../components/Charts";
import { PostureScene } from "../components/Scene";
import { api, clock, fmt, METRIC_INFO, MetricKey, originFromSamples, originOf, Sample, SessionMeta, sessionTitle, toSagittal, Workstation } from "../lib";
import { Link, navigate } from "../router";

const KEY_METRICS: MetricKey[] = ["neck", "head_offset", "upper_back", "lower_back", "trunk"];

export function Sessions() {
  const [sessions, setSessions] = useState<SessionMeta[] | null>(null);
  useEffect(() => {
    api<SessionMeta[]>("/api/sessions").then(setSessions).catch(() => setSessions([]));
  }, []);
  if (!sessions) return <div className="page muted">Loading…</div>;
  return (
    <div className="page">
      <header className="page-head">
        <h1>Sessions</h1>
        <p className="muted">Every 30-minute recording, newest first. Open one to replay it in 3D and rate how you felt.</p>
      </header>
      {!sessions.length && (
        <div className="empty card">
          No Sessions yet. Connect the phone from <Link to="/">Live</Link> and work for half an hour.
        </div>
      )}
      <div className="session-list">
        {sessions.map((s) => (
          <Link key={s.id} to={`/sessions/${s.id}`} className="card session-card">
            <div className="session-card-head">
              <div>
                <div className="session-title">{sessionTitle(s)}</div>
                <div className="muted small">
                  {s.label ? `${s.label} · ` : ""}
                  {s.summary ? `${Math.round(s.summary.presence_s / 60)} min present · ${s.summary.valid_percent}% valid` : s.status}
                </div>
              </div>
              <div className="chips">
                {s.summary && <span className={`chip ${s.summary.accepted ? "ok" : "warn"}`}>{s.summary.accepted ? "accepted" : "too short"}</span>}
                {!s.discomfort && s.summary && <span className="chip warn">rate comfort</span>}
                {s.has_report && <span className="chip accent">report</span>}
              </div>
            </div>
            {s.summary && (
              <div className="session-metrics">
                {KEY_METRICS.map((k) => (
                  <div key={k}>
                    <span className="muted small">{METRIC_INFO[k].label}</span>
                    <b style={{ color: METRIC_INFO[k].color }}>{fmt(k, s.summary!.metrics[k]?.median)}</b>
                  </div>
                ))}
              </div>
            )}
          </Link>
        ))}
      </div>
    </div>
  );
}

const REGIONS: [string, string][] = [
  ["neck", "Neck"],
  ["shoulders", "Shoulders"],
  ["upper_back", "Upper back"],
  ["lower_back", "Lower back"],
  ["wrists", "Wrists / forearms"],
  ["legs", "Legs / hips"],
];

function DiscomfortForm({ session, onSaved }: { session: SessionMeta; onSaved: (d: Record<string, number>) => void }) {
  const [values, setValues] = useState<Record<string, number>>(session.discomfort ?? Object.fromEntries(REGIONS.map(([k]) => [k, 0])));
  const [saved, setSaved] = useState(!!session.discomfort);
  return (
    <section className="card">
      <h3>How did you feel?</h3>
      <p className="muted small">Discomfort during this Session: 0 = none, 10 = severe. Claude uses it to judge whether a change really helped.</p>
      <div className="discomfort">
        {REGIONS.map(([k, label]) => (
          <label key={k} className="slider-row">
            <span>{label}</span>
            <input
              type="range"
              min={0}
              max={10}
              value={values[k] ?? 0}
              onChange={(e) => {
                setValues({ ...values, [k]: Number(e.target.value) });
                setSaved(false);
              }}
            />
            <b>{values[k] ?? 0}</b>
          </label>
        ))}
      </div>
      <button
        className="btn"
        disabled={saved}
        onClick={async () => {
          const d = await api<Record<string, number>>(`/api/sessions/${session.id}/discomfort`, {
            method: "PUT",
            headers: { "content-type": "application/json" },
            body: JSON.stringify(values),
          });
          setSaved(true);
          onSaved(d);
        }}
      >
        {saved ? "Saved" : "Save"}
      </button>
    </section>
  );
}

export function SessionDetail({ id }: { id: string }) {
  const [meta, setMeta] = useState<SessionMeta | null>(null);
  const [samples, setSamples] = useState<Sample[]>([]);
  const [report, setReport] = useState<string | null>(null);
  const [workstation, setWorkstation] = useState<Workstation | null>(null);
  const [cursor, setCursor] = useState<number | null>(null);
  const [playing, setPlaying] = useState(false);
  const [zoom, setZoom] = useState<string | null>(null);

  useEffect(() => {
    api<SessionMeta>(`/api/sessions/${id}`).then(setMeta).catch(() => setMeta(null));
    api<Sample[]>(`/api/sessions/${id}/samples`).then(setSamples).catch(() => {});
    fetch(`/api/sessions/${id}/report`).then((r) => (r.ok ? r.text() : null)).then(setReport);
    api<Workstation | null>("/api/workstation").then(setWorkstation).catch(() => {});
  }, [id]);

  useEffect(() => {
    if (!playing || !samples.length) return;
    const end = samples[samples.length - 1].t;
    const h = window.setInterval(() => setCursor((c) => ((c ?? 0) + 10 > end ? 0 : (c ?? 0) + 10)), 100);
    return () => clearInterval(h);
  }, [playing, samples]);

  const current = useMemo(() => {
    if (!samples.length) return null;
    const valid = samples.filter((s) => s.valid);
    if (cursor == null) {
      // the most typical posture: closest to the median trunk angle
      const med = meta?.summary?.metrics.trunk?.median ?? 0;
      return valid.reduce<Sample | null>((b, s) => (!b || Math.abs((s.metrics?.trunk ?? 0) - med) < Math.abs((b.metrics?.trunk ?? 0) - med) ? s : b), null);
    }
    return nearest(valid, cursor);
  }, [samples, cursor, meta]);
  const origin = useMemo(() => (current ? originOf(meta?.summary, current) ?? originFromSamples(samples) : null), [current, meta, samples]);
  const pose = current ? toSagittal(current, origin) : null;
  const frame = useMemo(() => {
    if (!meta?.frames?.length) return null;
    const t = current?.t ?? 0;
    return meta.frames.reduce((b, f) => (Math.abs(parseInt(f) - t) < Math.abs(parseInt(b) - t) ? f : b));
  }, [meta, current]);

  if (!meta) return <div className="page muted">Loading…</div>;
  const s = meta.summary;
  return (
    <div className="page">
      <header className="page-head row">
        <div>
          <Link to="/sessions" className="muted small">← Sessions</Link>
          <h1>{sessionTitle(meta)}</h1>
          {meta.label && <span className="chip accent">{meta.label}</span>}
        </div>
        {s && (
          <div className="stat-row">
            <Stat label="Present" value={`${Math.round(s.presence_s / 60)} min`} />
            <Stat label="Valid" value={`${s.valid_percent}%`} />
            <Stat label="Breaks" value={`${s.absences.length}`} />
            {!!s.interrupted_s && <Stat label="Interrupted" value={`${Math.round(s.interrupted_s / 60)} min`} />}
            <Stat label="Longest still" value={`${Math.round(s.longest_still_s / 60)} min`} />
            <span className={`chip big ${s.accepted ? "ok" : "warn"}`}>{s.accepted ? "accepted" : "not accepted"}</span>
          </div>
        )}
      </header>

      <div className="detail-grid">
        <section className="card scene-card tall">
          <div className="scene-overlay">
            <span className="badge">{cursor == null ? "typical posture" : clock(current?.t ?? 0)}</span>
            <button className="btn ghost small" onClick={() => setPlaying(!playing)}>{playing ? "Pause" : "Replay ×10"}</button>
          </div>
          <PostureScene pose={pose} workstation={workstation} height="100%" />
        </section>
        <section className="card frame-card">
          {frame ? <img src={`/api/sessions/${id}/frames/${frame}`} alt="" onClick={() => setZoom(frame)} /> : <div className="muted">No frames</div>}
          <div className="muted small">Saved frame at {frame ? clock(parseInt(frame)) : "—"}</div>
        </section>
      </div>

      {s && (
        <section className="card">
          {(["neck", "head_offset", "upper_back", "lower_back", "trunk", "elbow"] as MetricKey[]).map((k) => (
            <Timeline
              key={k}
              samples={samples}
              metric={k}
              absences={s.absences}
              interruptions={s.interruptions}
              cursor={cursor}
              onCursor={setCursor}
              height={96}
              band={s.metrics[k]?.p10 != null ? [s.metrics[k].p10!, s.metrics[k].p90!] : undefined}
            />
          ))}
          <p className="muted small">Thin line: every second. Thick line: one-minute trend. Shaded: away from the desk. Red hatching: no camera data (phone offline, call, Wi-Fi). Click to move the 3D model to that moment.</p>
          {meta.recovered && <p className="warn-text small">This Session was closed automatically after the server stopped during the recording.</p>}
        </section>
      )}

      <div className="two-col">
        <section className="card">
          <h3>What was measured</h3>
          {meta.findings?.length ? (
            <ul className="findings">
              {meta.findings.map((f) => (
                <li key={f.id}>
                  <span className={`conf conf-${f.confidence}`}>{f.confidence}</span>
                  <div>
                    <b>{f.text}</b>
                    <div className="muted small">{f.evidence}</div>
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">No notable Findings.</p>
          )}
        </section>
        <DiscomfortForm session={meta} onSaved={(d) => setMeta({ ...meta, discomfort: d })} />
      </div>

      <section className="card report">
        <h3>Claude's report</h3>
        {report ? (
          <Markdown>{report}</Markdown>
        ) : (
          <div className="claude-hint">
            No report yet. In Claude Code, run <code>/report {id}</code>
          </div>
        )}
      </section>

      {meta.frames && meta.frames.length > 0 && (
        <section className="card">
          <h3>Saved frames</h3>
          <div className="frame-strip">
            {meta.frames.map((f) => (
              <img key={f} src={`/api/sessions/${id}/frames/${f}`} loading="lazy" alt="" onClick={() => setCursor(parseInt(f))} className={frame === f ? "active" : ""} />
            ))}
          </div>
        </section>
      )}

      <div className="danger-zone">
        <button
          className="btn ghost danger-text"
          onClick={async () => {
            if (!confirm("Delete this Session and its frames?")) return;
            await api(`/api/sessions/${id}`, { method: "DELETE" });
            navigate("/sessions");
          }}
        >
          Delete Session
        </button>
      </div>

      {zoom && (
        <div className="lightbox" onClick={() => setZoom(null)}>
          <img src={`/api/sessions/${id}/frames/${zoom}`} alt="" />
        </div>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="stat">
      <span className="muted small">{label}</span>
      <b>{value}</b>
    </div>
  );
}
