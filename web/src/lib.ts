// Shared types, API helpers and posture geometry for the dashboard.

export type Metrics = Partial<Record<MetricKey, number | null>>;

export type MetricKey =
  | "trunk"
  | "neck"
  | "head_offset"
  | "upper_back"
  | "lower_back"
  | "back_rounding"
  | "upper_arm"
  | "elbow"
  | "hip"
  | "knee";

export interface Sample {
  t: number;
  person: boolean;
  valid: boolean;
  w: number;
  h: number;
  side?: "left" | "right";
  fwd?: 1 | -1;
  trunk_len?: number | null;
  hip?: [number, number] | null;
  metrics?: Metrics;
  kp?: [number, number, number][];
  back?: [number, number][];
  mpp?: number | null;
  camera?: CameraTilt | null;
  yaw?: number | null;
}

/** The phone's tilt when the frame was taken (degrees). */
export interface CameraTilt { roll: number; pitch: number }

export interface Status {
  state: "idle" | "framing" | "recording" | "finished";
  phone_connected: boolean;
  session_id: string | null;
  elapsed_s: number;
  session_s: number;
  framing_progress: number;
  framing_problems: string[];
  away: boolean;
  catching_up?: number;
  camera_url?: string;
}

export interface MetricStats {
  median?: number;
  p10?: number;
  p90?: number;
  first_third_median?: number;
  last_third_median?: number;
  visible_percent: number;
  minute_std?: number | null;
}

export interface Summary {
  started_at: string;
  time_band: string;
  duration_s: number;
  presence_s: number;
  valid_percent: number;
  accepted: boolean;
  absences: { start_s: number; end_s: number }[];
  interruptions?: { start_s: number; end_s: number }[];
  interrupted_s?: number;
  longest_still_s: number;
  placement: { side: string; body_scale: number; hip_x: number; hip_y: number; mpp?: number; yaw?: number; roll?: number; pitch?: number } | null;
  metrics: Record<MetricKey, MetricStats>;
}

export interface Finding {
  id: string;
  text: string;
  confidence: "low" | "medium" | "high";
  evidence: string;
}

export interface SessionMeta {
  id: string;
  started_at: string;
  status: string;
  duration_s?: number;
  summary?: Summary | null;
  discomfort?: Record<string, number> | null;
  has_report?: boolean;
  label?: string;
  recovered?: boolean;
  frames?: string[];
  findings?: Finding[];
}

export interface Workstation {
  objects: Record<string, Record<string, [number, number]>>;
  body: Record<string, [number, number] | null>;
  derived: Record<string, number>;
  notes?: string;
  session_id: string;
  frame: string;
  updated_at: string;
  anchor?: Anchor;
}

/** Where body coordinates start: a Session's usual seated hip (pixels of its frames) and its scale.
 * The desk is stored relative to it, so each Session — even with the phone moved — places the
 * desk around its own usual hip. */
export interface Origin { hip: [number, number]; mpp: number }

/** The Workstation's origin, from the Session it was reconstructed on. */
export interface Anchor extends Origin { w: number; h: number; fwd: 1 | -1; camera?: CameraTilt | null }

export interface MetricMove {
  metric: string;
  direction: "increase" | "decrease";
  measurable: boolean;
  baseline?: number;
  reassessment?: number;
  change?: number;
  reference_variability?: number;
  moved_as_expected?: boolean;
}

export interface Intervention {
  id: string;
  library_id?: string;
  title: string;
  kind?: string;
  instructions?: string;
  targets: { metric: string; direction: string }[];
  baselines: string[];
  reassessment?: string;
  status: "proposed" | "applied" | "evaluated";
  outcome?: string;
  probable_cause?: string | null;
  decision?: string;
  metrics?: MetricMove[];
  comfort?: { per_region: Record<string, number>; total: number; worse: boolean; better: boolean; rated: boolean };
  limited_comparability?: string[];
  created_at: string;
  applied_at?: string;
  evaluated_at?: string;
}

export interface StandingSide { ok: boolean; metrics: Metrics; photo: string; measured_at: string; trunk_px: number; height_px: number; kp?: [number, number, number][]; back?: [number, number][]; w: number; h: number }
export interface StandingFront { ok: boolean; shoulder_line_deg: number; hip_line_deg: number; lateral_shift: number; head_tilt_deg?: number; photo: string; measured_at: string; kp?: [number, number, number][]; w: number; h: number }
export interface Profile { height_cm?: number; trunk_m?: number | null; standing_side?: StandingSide; standing_front?: StandingFront }

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, init);
  if (!r.ok) throw new Error(`${r.status} ${path}`);
  return r.json();
}

// ---------------------------------------------------------------- metrics

export const METRIC_INFO: Record<MetricKey, { label: string; unit: string; color: string; hint: string; digits: number }> = {
  neck: { label: "Neck", unit: "°", color: "#fbbf24", hint: "shoulder → ear from vertical; + = head forward", digits: 0 },
  head_offset: { label: "Head forward", unit: "", color: "#fb923c", hint: "ear ahead of shoulder, in trunk lengths", digits: 2 },
  upper_back: { label: "Upper back", unit: "°", color: "#a78bfa", hint: "upper half of the back from vertical; + = forward", digits: 0 },
  lower_back: { label: "Lower back", unit: "°", color: "#f472b6", hint: "lower half of the back from vertical; − = slumped back", digits: 0 },
  back_rounding: { label: "Back rounding", unit: "°", color: "#c084fc", hint: "upper − lower back angle; + = hunched", digits: 0 },
  trunk: { label: "Trunk", unit: "°", color: "#5eead4", hint: "hip → shoulder from vertical; + = leaning forward", digits: 0 },
  upper_arm: { label: "Upper arm", unit: "°", color: "#60a5fa", hint: "elbow ahead of shoulder; + = reaching", digits: 0 },
  elbow: { label: "Elbow", unit: "°", color: "#38bdf8", hint: "shoulder-elbow-wrist angle", digits: 0 },
  hip: { label: "Hip", unit: "°", color: "#4ade80", hint: "shoulder-hip-knee angle", digits: 0 },
  knee: { label: "Knee", unit: "°", color: "#a3e635", hint: "hip-knee-ankle angle", digits: 0 },
};

export const LIVE_METRICS: MetricKey[] = ["neck", "head_offset", "upper_back", "lower_back", "trunk", "upper_arm", "elbow", "knee"];

export function fmt(key: MetricKey | string, v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  const info = METRIC_INFO[key as MetricKey];
  return `${v.toFixed(info?.digits ?? 1)}${info?.unit ?? ""}`;
}

export function clock(s: number): string {
  const m = Math.floor(s / 60);
  const ss = Math.floor(s % 60);
  return `${m}:${ss.toString().padStart(2, "0")}`;
}

export function sessionTitle(s: { started_at: string }): string {
  const d = new Date(s.started_at);
  return d.toLocaleString(undefined, { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

// ---------------------------------------------------------------- body geometry

export const KP = { nose: 0, ear: { left: 7, right: 8 }, shoulder: { left: 11, right: 12 }, elbow: { left: 13, right: 14 }, wrist: { left: 15, right: 16 }, hip: { left: 23, right: 24 }, knee: { left: 25, right: 26 }, ankle: { left: 27, right: 28 }, heel: { left: 29, right: 30 }, toe: { left: 31, right: 32 } } as const;

export type Joint = "ear" | "shoulder" | "elbow" | "wrist" | "hip" | "knee" | "ankle" | "heel" | "toe";
export interface SagittalPoint { x: number; y: number; visible: boolean }
export type Sagittal = Record<Joint, SagittalPoint> & { back: [number, number][] };

/** Sample → body-relative sagittal coordinates (metres; origin hip, x forward, y up). */
const FOCAL_FRACTION = 0.72; // as in schiena/camera.py

/** Pixel → pixel map onto a level camera (same maths as schiena/camera.py). */
export function leveller(s: { w: number; h: number; camera?: CameraTilt | null }): (x: number, y: number) => [number, number] {
  if (!s.camera) return (x, y) => [x, y];
  const r = (s.camera.roll * Math.PI) / 180;
  const p = (s.camera.pitch * Math.PI) / 180;
  const a = [Math.sin(r) * Math.cos(p), -Math.cos(r) * Math.cos(p), Math.sin(p)];
  const v = [a[2], 0, -a[0]]; // a × (0, −1, 0)
  const sn = Math.hypot(...v);
  const c = -a[1];
  let R = [[1, 0, 0], [0, 1, 0], [0, 0, 1]];
  if (sn > 1e-9) {
    const vx = [[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]];
    const k = (1 - c) / (sn * sn);
    R = R.map((row, i) => row.map((e, j) => e + vx[i][j] + k * vx[i].reduce((acc, _, m) => acc + vx[i][m] * vx[m][j], 0)));
  }
  const f = FOCAL_FRACTION * Math.max(s.w, s.h);
  const cx = s.w / 2;
  const cy = s.h / 2;
  return (x, y) => {
    const X = [(x - cx) / f, (y - cy) / f, 1];
    const Y = R.map((row) => row[0] * X[0] + row[1] * X[1] + row[2] * X[2]);
    return [cx + (f * Y[0]) / Y[2], cy + (f * Y[1]) / Y[2]];
  };
}

const median = (v: number[]) => {
  const a = [...v].sort((x, y) => x - y);
  return a.length ? (a.length % 2 ? a[(a.length - 1) / 2] : (a[a.length / 2 - 1] + a[a.length / 2]) / 2) : NaN;
};

/** Origin of a finished Session, from its summary. */
export function originOf(summary: Summary | null | undefined, sample: Sample): Origin | null {
  const pl = summary?.placement;
  const mpp = pl?.mpp ?? sample.mpp;
  return pl && mpp ? { hip: [pl.hip_x * sample.w, pl.hip_y * sample.h], mpp } : null;
}

/** Origin from Samples (a Session still recording). */
export function originFromSamples(samples: Sample[]): Origin | null {
  const v = samples.filter((s) => s.valid && s.hip && s.mpp);
  if (v.length < 5) return null;
  return { hip: [median(v.map((s) => s.hip![0])), median(v.map((s) => s.hip![1]))], mpp: median(v.map((s) => s.mpp!)) };
}

/** A Sample in body coordinates (metres, x forward, y up), levelled with the phone's tilt.
 * origin: the Session's usual hip (see Origin); default: this Sample's own hip. */
export function toSagittal(s: Sample, origin?: Origin | null): Sagittal | null {
  if (!s.person || !s.kp || !s.hip || !s.side || !s.trunk_len) return null;
  const lev = leveller(s);
  const mpp = origin?.mpp ?? s.mpp ?? 0.5 / s.trunk_len;
  const fwd = s.fwd ?? 1;
  const [hx, hy] = lev(...(origin?.hip ?? s.hip));
  const conv = (xn: number, yn: number): [number, number] => {
    const [x, y] = lev(xn * s.w, yn * s.h);
    return [fwd * (x - hx) * mpp, -(y - hy) * mpp];
  };
  const out: Partial<Sagittal> = {};
  for (const j of ["ear", "shoulder", "elbow", "wrist", "hip", "knee", "ankle", "heel", "toe"] as Joint[]) {
    const [x, y, v] = s.kp[KP[j][s.side]];
    const [sx, sy] = conv(x, y);
    out[j] = { x: sx, y: sy, visible: v >= 0.5 };
  }
  out.back = (s.back ?? []).map(([x, y]) => conv(x, y));
  return out as Sagittal;
}
