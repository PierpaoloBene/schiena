import { useMemo, useRef, useState } from "react";
import { clock, fmt, METRIC_INFO, MetricKey, Sample } from "../lib";

export function Sparkline({ values, color, width = 120, height = 34 }: { values: (number | null | undefined)[]; color: string; width?: number; height?: number }) {
  const pts = values.map((v, i) => [i, v] as const).filter((p): p is readonly [number, number] => p[1] != null);
  if (pts.length < 2) return <svg width={width} height={height} />;
  const ys = pts.map((p) => p[1]);
  const lo = Math.min(...ys), hi = Math.max(...ys);
  const span = hi - lo || 1;
  const n = Math.max(values.length - 1, 1);
  const d = pts.map(([i, v], k) => `${k ? "L" : "M"}${((i / n) * width).toFixed(1)},${(height - 3 - ((v - lo) / span) * (height - 6)).toFixed(1)}`).join("");
  const id = `sg${color.slice(1)}`;
  return (
    <svg width={width} height={height} className="sparkline">
      <defs>
        <linearGradient id={id} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor={color} stopOpacity="0.35" />
          <stop offset="1" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={`${d}L${width},${height}L0,${height}Z`} fill={`url(#${id})`} />
      <path d={d} fill="none" stroke={color} strokeWidth="1.8" strokeLinejoin="round" />
    </svg>
  );
}

/** Time series of one Metric over a Session, with Absences shaded and a cursor. */
export function Timeline({
  samples,
  metric,
  absences,
  interruptions = [],
  cursor,
  onCursor,
  height = 140,
  band,
}: {
  samples: Sample[];
  metric: MetricKey;
  absences: { start_s: number; end_s: number }[];
  interruptions?: { start_s: number; end_s: number }[];
  cursor?: number | null;
  onCursor?: (t: number) => void;
  height?: number;
  band?: [number, number];
}) {
  const ref = useRef<SVGSVGElement>(null);
  const [hover, setHover] = useState<number | null>(null);
  const W = 1000;
  const info = METRIC_INFO[metric];
  const { path, lo, hi, tMax, smooth } = useMemo(() => {
    const pts = samples.filter((s) => s.valid && s.metrics?.[metric] != null).map((s) => [s.t, s.metrics![metric] as number] as const);
    const tMax = Math.max(60, samples.length ? samples[samples.length - 1].t : 60);
    if (!pts.length) return { path: "", lo: 0, hi: 1, tMax, smooth: "" };
    const ys = pts.map((p) => p[1]).sort((a, b) => a - b);
    const lo = ys[Math.floor(ys.length * 0.01)], hi = ys[Math.ceil(ys.length * 0.99) - 1];
    const pad = (hi - lo) * 0.15 || 1;
    const L = lo - pad, H = hi + pad;
    const X = (t: number) => (t / tMax) * W;
    const Y = (v: number) => height - 18 - ((Math.min(H, Math.max(L, v)) - L) / (H - L)) * (height - 30);
    let path = "";
    let prevT = -10;
    for (const [t, v] of pts) {
      path += `${t - prevT > 3 ? "M" : "L"}${X(t).toFixed(1)},${Y(v).toFixed(1)}`;
      prevT = t;
    }
    // 60-s rolling median for the trend line
    let smooth = "";
    for (let i = 0; i < pts.length; i += 5) {
      const win = pts.filter((p) => Math.abs(p[0] - pts[i][0]) <= 30).map((p) => p[1]).sort((a, b) => a - b);
      smooth += `${i ? "L" : "M"}${X(pts[i][0]).toFixed(1)},${Y(win[Math.floor(win.length / 2)]).toFixed(1)}`;
    }
    return { path, lo: L, hi: H, tMax, smooth };
  }, [samples, metric, height]);

  const Y = (v: number) => height - 18 - ((v - lo) / (hi - lo)) * (height - 30);
  const tAt = (clientX: number) => {
    const r = ref.current!.getBoundingClientRect();
    return Math.max(0, Math.min(tMax, ((clientX - r.left) / r.width) * tMax));
  };
  const shown = hover ?? cursor ?? null;
  const shownSample = shown != null ? nearest(samples, shown) : null;

  return (
    <div className="timeline">
      <div className="timeline-head">
        <span className="dot" style={{ background: info.color }} />
        <span className="timeline-label">{info.label}</span>
        <span className="muted small">{info.hint}</span>
        <span className="timeline-value">{shownSample ? `${clock(shownSample.t)} · ${fmt(metric, shownSample.metrics?.[metric])}` : ""}</span>
      </div>
      <svg
        ref={ref}
        viewBox={`0 0 ${W} ${height}`}
        preserveAspectRatio="none"
        className="timeline-svg"
        style={{ height }}
        onMouseMove={(e) => setHover(tAt(e.clientX))}
        onMouseLeave={() => setHover(null)}
        onClick={(e) => onCursor?.(tAt(e.clientX))}
      >
        {absences.map((a, i) => (
          <rect key={i} x={(a.start_s / tMax) * W} width={((a.end_s - a.start_s) / tMax) * W} y={0} height={height - 14} className="absence" />
        ))}
        {interruptions.map((a, i) => (
          <rect key={`i${i}`} x={(a.start_s / tMax) * W} width={((a.end_s - a.start_s) / tMax) * W} y={0} height={height - 14} className="interruption" />
        ))}
        {band && <rect x={0} width={W} y={Y(band[1])} height={Math.max(0, Y(band[0]) - Y(band[1]))} fill={info.color} opacity={0.08} />}
        {lo < 0 && hi > 0 && <line x1={0} x2={W} y1={Y(0)} y2={Y(0)} className="zero" />}
        <defs>
          <pattern id="hatch" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <line x1="0" y1="0" x2="0" y2="8" stroke="rgba(248,113,113,0.35)" strokeWidth="3" />
          </pattern>
        </defs>
        <path d={path} fill="none" stroke={info.color} strokeOpacity={0.35} strokeWidth={1.2} vectorEffect="non-scaling-stroke" />
        <path d={smooth} fill="none" stroke={info.color} strokeWidth={2.4} vectorEffect="non-scaling-stroke" />
        {shown != null && <line x1={(shown / tMax) * W} x2={(shown / tMax) * W} y1={0} y2={height - 14} className="cursor" vectorEffect="non-scaling-stroke" />}
        {[0, 0.25, 0.5, 0.75, 1].map((f) => (
          <text key={f} x={f * W} y={height - 2} className="axis" textAnchor={f === 0 ? "start" : f === 1 ? "end" : "middle"}>
            {clock(f * tMax)}
          </text>
        ))}
      </svg>
    </div>
  );
}

export function nearest(samples: Sample[], t: number): Sample | null {
  let best: Sample | null = null;
  for (const s of samples) {
    if (!best || Math.abs(s.t - t) < Math.abs(best.t - t)) best = s;
  }
  return best;
}

/** Horizontal comparison of a Metric across Sessions: median dot with p10–p90 range. */
export function RangeBars({
  rows,
  metric,
}: {
  rows: { label: string; median?: number; p10?: number; p90?: number; tone?: string }[];
  metric: MetricKey;
}) {
  const vals = rows.flatMap((r) => [r.p10, r.p90, r.median]).filter((v): v is number => v != null);
  if (!vals.length) return <div className="muted small">Not measured</div>;
  const lo = Math.min(...vals), hi = Math.max(...vals);
  const pad = (hi - lo) * 0.1 || 1;
  const X = (v: number) => ((v - lo + pad) / (hi - lo + 2 * pad)) * 100;
  const color = METRIC_INFO[metric].color;
  return (
    <div className="rangebars">
      {rows.map((r, i) => (
        <div key={i} className="rangebar-row">
          <span className="rangebar-label">{r.label}</span>
          <div className="rangebar-track">
            {r.p10 != null && r.p90 != null && (
              <div className="rangebar-range" style={{ left: `${X(r.p10)}%`, width: `${X(r.p90) - X(r.p10)}%`, background: r.tone ?? color }} />
            )}
            {r.median != null && <div className="rangebar-median" style={{ left: `${X(r.median)}%`, borderColor: r.tone ?? color }} />}
          </div>
          <span className="rangebar-value">{fmt(metric, r.median)}</span>
        </div>
      ))}
    </div>
  );
}
