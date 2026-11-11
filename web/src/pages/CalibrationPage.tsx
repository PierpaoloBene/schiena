import { useEffect, useState } from "react";
import { PostureScene } from "../components/Scene";
import { api, fmt, METRIC_INFO, MetricKey, Profile, Sample, toSagittal, Workstation } from "../lib";

const DERIVED_LABELS: Record<string, string> = {
  monitor_top_above_eye_cm: "Monitor top vs eye height",
  monitor_distance_cm: "Eye → monitor centre",
  monitor_centre_below_eye_deg: "Monitor centre below eye line",
  laptop_screen_top_above_eye_cm: "Laptop screen top vs eye height",
  laptop_screen_distance_cm: "Eye → laptop screen centre",
  laptop_screen_centre_below_eye_deg: "Laptop screen below eye line",
  keyboard_above_elbow_cm: "Keyboard vs elbow height",
  keyboard_ahead_of_elbow_cm: "Keyboard ahead of elbow",
};

export function CalibrationPage() {
  const [ws, setWs] = useState<Workstation | null | undefined>(undefined);
  const [sample, setSample] = useState<Sample | null>(null);
  const [photos, setPhotos] = useState<string[]>([]);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [height, setHeight] = useState("");
  useEffect(() => {
    api<Workstation | null>("/api/workstation").then(async (w) => {
      setWs(w);
      if (w) {
        const samples = await api<Sample[]>(`/api/sessions/${w.session_id}/samples`);
        setSample(samples.find((s) => Math.round(s.t) === parseInt(w.frame)) ?? null);
      }
    });
    api<string[]>("/api/photos").then((p) => setPhotos(p.filter((n) => !n.startsWith("standing_"))));
    api<Profile>("/api/profile").then((p) => {
      setProfile(p);
      if (p.height_cm) setHeight(String(p.height_cm));
    });
  }, []);
  if (ws === undefined) return <div className="page muted">Loading…</div>;
  return (
    <div className="page">
      <header className="page-head">
        <h1>Calibration</h1>
        <p className="muted">
          Once, and again after you change your desk or move the phone. Your part is on the phone (<b>Calibrate</b>: height, a relaxed
          standing photo, desk photos); then ask Claude <code>/calibrate</code> to rebuild your desk in 3D.
        </p>
      </header>
      <section className="card">
        <h3>You</h3>
        <div className="you-grid">
          <div>
            <label className="slider-row">
              <span>Height (cm)</span>
              <input className="input" inputMode="numeric" value={height} onChange={(e) => setHeight(e.target.value)} />
              <button
                className="btn small"
                disabled={!(Number(height) >= 100 && Number(height) <= 230) || Number(height) === profile?.height_cm}
                onClick={async () =>
                  setProfile(await api<Profile>("/api/profile", { method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify({ height_cm: Number(height) }) }))
                }
              >
                Save
              </button>
            </label>
            <p className="muted small">
              {profile?.trunk_m
                ? `Scale calibrated: shoulder→hip ${Math.round(profile.trunk_m * 100)} cm${profile.standing_side?.ok ? " (from your standing photo)" : " (average proportions)"}. Applies to new Sessions and to /calibrate.`
                : "Without your height, distances assume an average body."}
            </p>
            {profile?.standing_side?.ok ? (
              <dl className="derived">
                {(["neck", "head_offset", "upper_back", "lower_back", "back_rounding", "trunk"] as MetricKey[]).map((k) => (
                  <div key={k}>
                    <dt>{METRIC_INFO[k].label} standing relaxed</dt>
                    <dd>{fmt(k, profile.standing_side!.metrics[k])}</dd>
                  </div>
                ))}
              </dl>
            ) : (
              <p className="muted small">No standing reference yet. On the phone page: “Calibrate: height + standing photos”.</p>
            )}
            {profile?.standing_front?.ok && (
              <dl className="derived">
                <div><dt>Shoulder line (front)</dt><dd>{profile.standing_front.shoulder_line_deg}°</dd></div>
                <div><dt>Hip line (front)</dt><dd>{profile.standing_front.hip_line_deg}°</dd></div>
                <div><dt>Shoulders vs hips sideways</dt><dd>{Math.round(profile.standing_front.lateral_shift * 100)}% of trunk</dd></div>
              </dl>
            )}
            {profile?.standing_front?.ok && <p className="muted small">From one photo, for context only: small asymmetries are normal and this is not a diagnosis.</p>}
          </div>
          <div className="you-photos">
            {profile?.standing_side?.ok && <img src={`/api/photos/${profile.standing_side.photo}`} alt="standing, side" />}
            {profile?.standing_front?.ok && <img src={`/api/photos/${profile.standing_front.photo}`} alt="standing, front" />}
          </div>
        </div>
      </section>
      <h2 className="section-title">Workstation</h2>
      {!ws ? (
        <div className="card empty">
          Not reconstructed yet. After your first Session, ask Claude: <code>/calibrate</code>
          <p className="muted small">Desk photos from the phone's Calibrate screen give Claude a front view too.</p>
        </div>
      ) : (
        <div className="detail-grid">
          <section className="card scene-card tall">
            <PostureScene pose={sample ? toSagittal(sample, ws.anchor) : null} workstation={ws} height="100%" />
          </section>
          <section className="card">
            <h3>Measured from the side</h3>
            <dl className="derived">
              {Object.entries(ws.derived).map(([k, v]) => (
                <div key={k}>
                  <dt>{DERIVED_LABELS[k] ?? k}</dt>
                  <dd>{v > 0 && k.includes("above") ? "+" : ""}{v}{k.endsWith("_deg") ? "°" : " cm"}</dd>
                </div>
              ))}
            </dl>
            {ws.notes && <p className="muted">{ws.notes}</p>}
            <img className="ref-frame" src={`/api/sessions/${ws.session_id}/frames/${ws.frame}`} alt="" />
            <p className="muted small">Reference frame · updated {new Date(ws.updated_at).toLocaleString()}</p>
          </section>
        </div>
      )}
      {photos.length > 0 && (
        <section className="card">
          <h3>Desk photos</h3>
          <div className="frame-strip">
            {photos.map((p) => (
              <img key={p} src={`/api/photos/${p}`} alt="" />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
