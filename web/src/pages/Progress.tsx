import { useEffect, useState } from "react";
import { RangeBars } from "../components/Charts";
import { PostureScene } from "../components/Scene";
import { api, fmt, Intervention, METRIC_INFO, MetricKey, Sample, SessionMeta, sessionTitle, toSagittal, Workstation } from "../lib";
import { Link } from "../router";

const OUTCOME_TONE: Record<string, string> = {
  successful: "ok",
  "comfort-only improvement": "accent",
  inconclusive: "warn",
};

const TREND_METRICS: MetricKey[] = ["neck", "head_offset", "upper_back", "lower_back", "trunk", "elbow"];

export function Progress() {
  const [history, setHistory] = useState<{ interventions: Intervention[]; plateau: string | null } | null>(null);
  const [sessions, setSessions] = useState<SessionMeta[]>([]);
  useEffect(() => {
    api<{ interventions: Intervention[]; plateau: string | null }>("/api/history").then(setHistory);
    api<SessionMeta[]>("/api/sessions").then(setSessions);
  }, []);
  if (!history) return <div className="page muted">Loading…</div>;
  const byId = Object.fromEntries(sessions.map((s) => [s.id, s]));
  const done = sessions.filter((s) => s.summary).slice(0, 12).reverse();
  const active = history.interventions.filter((i) => i.status !== "evaluated");

  return (
    <div className="page">
      <header className="page-head">
        <h1>Progress</h1>
        <p className="muted">One change at a time, tested against your own Baselines. A change counts only if it moves beyond your normal day-to-day variation and doesn't make you feel worse.</p>
      </header>

      <section className="cycle card">
        {["Baseline ×2", "One change", "Reassessment", "Keep or revert"].map((step, i) => (
          <div key={step} className="cycle-step">
            <span className="cycle-n">{i + 1}</span>
            {step}
          </div>
        ))}
        <div className="claude-hint">
          Ask Claude: <code>/coach</code> — it reads your Sessions and history and tells you the next step.
        </div>
      </section>

      {history.plateau && (
        <section className="card banner-card">
          <b>Plateau reached:</b> {history.plateau}. From now on a check-up Session every 2–4 weeks is enough.
        </section>
      )}

      {active.map((i) => (
        <section key={i.id} className="card intervention current">
          <div className="intervention-head">
            <span className="chip accent">{i.status === "proposed" ? "suggested" : "in progress"}</span>
            <h2>{i.title}</h2>
            {i.library_id && <span className="muted small">{i.library_id}</span>}
          </div>
          {i.instructions && <p>{i.instructions}</p>}
          <p className="muted small">
            Expected: {i.targets.map((t) => `${METRIC_INFO[t.metric as MetricKey]?.label ?? t.metric} ${t.direction === "decrease" ? "↓" : "↑"}`).join(", ")}. Baselines:{" "}
            {i.baselines.map((b) => (
              <Link key={b} to={`/sessions/${b}`}>{byId[b] ? sessionTitle(byId[b]) : b} </Link>
            ))}
          </p>
        </section>
      ))}

      <h2 className="section-title">Interventions tried</h2>
      {!history.interventions.some((i) => i.status === "evaluated") && <div className="card muted">Nothing evaluated yet.</div>}
      <div className="intervention-list">
        {history.interventions
          .filter((i) => i.status === "evaluated")
          .reverse()
          .map((i) => (
            <InterventionCard key={i.id} i={i} byId={byId} />
          ))}
      </div>

      {done.length > 1 && (
        <>
          <h2 className="section-title">Across Sessions</h2>
          <div className="trend-grid">
            {TREND_METRICS.map((k) => (
              <section key={k} className="card">
                <h3 style={{ color: METRIC_INFO[k].color }}>{METRIC_INFO[k].label}</h3>
                <RangeBars
                  metric={k}
                  rows={done.map((s) => ({
                    label: s.label ?? sessionTitle(s),
                    median: s.summary!.metrics[k]?.median,
                    p10: s.summary!.metrics[k]?.p10,
                    p90: s.summary!.metrics[k]?.p90,
                  }))}
                />
              </section>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function InterventionCard({ i, byId }: { i: Intervention; byId: Record<string, SessionMeta> }) {
  const [poses, setPoses] = useState<{ before: Sample | null; after: Sample | null }>({ before: null, after: null });
  const [ws, setWs] = useState<Workstation | null>(null);
  useEffect(() => {
    const typical = async (sid?: string) => {
      if (!sid) return null;
      const samples = await api<Sample[]>(`/api/sessions/${sid}/samples`);
      const med = byId[sid]?.summary?.metrics.trunk?.median ?? 0;
      return samples.filter((s) => s.valid).reduce<Sample | null>((b, s) => (!b || Math.abs((s.metrics?.trunk ?? 0) - med) < Math.abs((b.metrics?.trunk ?? 0) - med) ? s : b), null);
    };
    Promise.all([typical(i.baselines[0]), typical(i.reassessment)]).then(([before, after]) => setPoses({ before, after }));
    api<Workstation | null>("/api/workstation").then(setWs).catch(() => {});
  }, [i.id]);
  return (
    <section className="card intervention">
      <div className="intervention-head">
        <span className={`chip ${OUTCOME_TONE[i.outcome ?? ""] ?? ""}`}>{i.outcome}</span>
        <h2>{i.title}</h2>
        {i.decision && <span className="chip">{i.decision}</span>}
      </div>
      {i.probable_cause && <p className="muted">Probable cause: {i.probable_cause}</p>}
      <div className="before-after">
        <div>
          <span className="muted small">Before</span>
          <PostureScene pose={poses.before ? toSagittal(poses.before, ws?.anchor) : null} workstation={ws} height={260} />
        </div>
        <div>
          <span className="muted small">After</span>
          <PostureScene pose={poses.after ? toSagittal(poses.after, ws?.anchor) : null} workstation={ws} height={260} />
        </div>
      </div>
      <table className="moves">
        <thead>
          <tr>
            <th>Metric</th>
            <th>Before</th>
            <th>After</th>
            <th>Change</th>
            <th>Your normal variation</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {(i.metrics ?? []).map((m) => (
            <tr key={m.metric}>
              <td>{METRIC_INFO[m.metric as MetricKey]?.label ?? m.metric} {m.direction === "decrease" ? "↓" : "↑"}</td>
              {m.measurable ? (
                <>
                  <td>{fmt(m.metric, m.baseline)}</td>
                  <td>{fmt(m.metric, m.reassessment)}</td>
                  <td>{m.change! >= 0 ? "+" : ""}{fmt(m.metric, m.change)}</td>
                  <td>±{fmt(m.metric, m.reference_variability)}</td>
                  <td>{m.moved_as_expected ? "✓ beyond variation" : "within variation"}</td>
                </>
              ) : (
                <td colSpan={5} className="muted">not measurable</td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
      {i.comfort?.rated && (
        <p className="muted small">
          Discomfort change: {Object.entries(i.comfort.per_region).map(([k, v]) => `${k.replace("_", " ")} ${v > 0 ? "+" : ""}${v}`).join(", ")}
        </p>
      )}
      {!!i.limited_comparability?.length && <p className="warn-text small">Limited comparability: {i.limited_comparability.join("; ")}</p>}
    </section>
  );
}
