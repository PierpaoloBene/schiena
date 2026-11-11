import { useEffect, useRef } from "react";
import { KP, METRIC_INFO, Sample } from "../lib";

const SEGMENTS: [keyof typeof KP, keyof typeof KP, string][] = [
  ["ear", "shoulder", METRIC_INFO.neck.color],
  ["shoulder", "elbow", METRIC_INFO.upper_arm.color],
  ["elbow", "wrist", METRIC_INFO.elbow.color],
  ["shoulder", "hip", METRIC_INFO.trunk.color],
  ["hip", "knee", METRIC_INFO.hip.color],
  ["knee", "ankle", METRIC_INFO.knee.color],
];

/** Live JPEG from the phone with the analysed skeleton and back contour drawn on top. */
export function CameraFeed({ imageUrl, sample }: { imageUrl: string | null; sample: Sample | null }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const c = canvas.current;
    if (!c) return;
    const ctx = c.getContext("2d")!;
    const w = c.clientWidth * devicePixelRatio, h = c.clientHeight * devicePixelRatio;
    c.width = w;
    c.height = h;
    ctx.clearRect(0, 0, w, h);
    if (!sample?.kp || !sample.side) return;
    const side = sample.side;
    const P = (x: number, y: number) => [x * w, y * h] as const;
    ctx.lineCap = "round";
    if (sample.back?.length) {
      ctx.strokeStyle = METRIC_INFO.upper_back.color;
      ctx.lineWidth = 4 * devicePixelRatio;
      ctx.setLineDash([2 * devicePixelRatio, 6 * devicePixelRatio]);
      ctx.beginPath();
      sample.back.forEach(([x, y], i) => (i ? ctx.lineTo(...P(x, y)) : ctx.moveTo(...P(x, y))));
      ctx.stroke();
      ctx.setLineDash([]);
    }
    for (const [a, b, color] of SEGMENTS) {
      const ka = sample.kp[(KP[a] as Record<string, number>)[side]];
      const kb = sample.kp[(KP[b] as Record<string, number>)[side]];
      const vis = ka[2] >= 0.5 && kb[2] >= 0.5;
      ctx.strokeStyle = color;
      ctx.globalAlpha = vis ? 0.95 : 0.25;
      ctx.lineWidth = 5 * devicePixelRatio;
      ctx.beginPath();
      ctx.moveTo(...P(ka[0], ka[1]));
      ctx.lineTo(...P(kb[0], kb[1]));
      ctx.stroke();
    }
    ctx.globalAlpha = 1;
    for (const j of ["ear", "shoulder", "elbow", "wrist", "hip", "knee", "ankle"] as const) {
      const k = sample.kp[(KP[j] as Record<string, number>)[side]];
      if (k[2] < 0.5) continue;
      ctx.fillStyle = "#fff";
      ctx.beginPath();
      ctx.arc(...P(k[0], k[1]), 4.5 * devicePixelRatio, 0, Math.PI * 2);
      ctx.fill();
    }
  }, [sample, imageUrl]);

  const aspect = sample ? `${sample.w} / ${sample.h}` : "9 / 16";
  return (
    <div className="camera-feed" style={{ aspectRatio: aspect }}>
      {imageUrl ? <img src={imageUrl} alt="" /> : <div className="camera-empty">No camera</div>}
      <canvas ref={canvas} />
    </div>
  );
}
