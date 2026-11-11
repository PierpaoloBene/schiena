// 3D posture model inside the reconstructed Workstation.
import { Canvas } from "@react-three/fiber";
import { ContactShadows, Html, Line, OrbitControls } from "@react-three/drei";
import { useMemo } from "react";
import * as THREE from "three";
import { METRIC_INFO, Sagittal, Workstation } from "../lib";

const SIDE_Z: Record<string, number> = { ear: 0.075, shoulder: 0.19, elbow: 0.24, wrist: 0.2, hip: 0.11, knee: 0.11, ankle: 0.11, heel: 0.11, toe: 0.11 };

type V3 = [number, number, number];

function Bone({ a, b, radius, color, ghost }: { a: V3; b: V3; radius: number; color: string; ghost?: boolean }) {
  const { position, quaternion, length } = useMemo(() => {
    const va = new THREE.Vector3(...a);
    const vb = new THREE.Vector3(...b);
    const dir = vb.clone().sub(va);
    const len = dir.length();
    const q = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir.clone().normalize());
    return { position: va.add(vb).multiplyScalar(0.5), quaternion: q, length: len };
  }, [a[0], a[1], a[2], b[0], b[1], b[2]]);
  if (length < 1e-4) return null;
  return (
    <mesh position={position} quaternion={quaternion} castShadow>
      <capsuleGeometry args={[radius, Math.max(0.001, length - radius), 6, 14]} />
      <meshStandardMaterial
        color={color}
        roughness={0.35}
        metalness={0.1}
        transparent={ghost}
        opacity={ghost ? 0.18 : 1}
        emissive={color}
        emissiveIntensity={ghost ? 0 : 0.18}
      />
    </mesh>
  );
}

function Body({ pose, highlight }: { pose: Sagittal; highlight?: string | null }) {
  const p = (j: keyof typeof SIDE_Z, side: 1 | -1): V3 => [pose[j as "ear"].x, pose[j as "ear"].y, side * SIDE_Z[j]];
  const vis = (...js: (keyof typeof SIDE_Z)[]) => js.every((j) => pose[j as "ear"].visible);
  const c = (k: keyof typeof METRIC_INFO) => (highlight && highlight !== k ? "#3b4458" : METRIC_INFO[k].color);
  const head: V3 = [pose.ear.x + 0.035, pose.ear.y + 0.03, 0];
  const neckBase: V3 = [pose.shoulder.x, pose.shoulder.y + 0.02, 0];
  const backCurve = useMemo(() => {
    if (pose.back.length < 4) return null;
    return pose.back.map(([x, y]) => new THREE.Vector3(x, y, 0));
  }, [pose]);
  const mid = Math.floor((backCurve?.length ?? 0) / 2);

  const bones: { a: V3; b: V3; r: number; color: string; ghost: boolean }[] = [];
  for (const s of [1, -1] as const) {
    bones.push({ a: p("shoulder", s), b: p("elbow", s), r: 0.042, color: c("upper_arm"), ghost: !vis("elbow") });
    bones.push({ a: p("elbow", s), b: p("wrist", s), r: 0.035, color: c("elbow"), ghost: !vis("elbow", "wrist") });
    bones.push({ a: p("hip", s), b: p("knee", s), r: 0.065, color: c("hip"), ghost: !vis("knee") });
    bones.push({ a: p("knee", s), b: p("ankle", s), r: 0.05, color: c("knee"), ghost: !vis("knee", "ankle") });
    bones.push({ a: p("ankle", s), b: p("toe", s), r: 0.035, color: c("knee"), ghost: !vis("ankle") });
    bones.push({ a: p("shoulder", s), b: p("hip", s), r: 0.035, color: c("trunk"), ghost: false });
    if (backCurve) bones.pop(); // the Torso replaces the shoulder→hip capsules
  }
  bones.push({ a: p("shoulder", 1), b: p("shoulder", -1), r: 0.05, color: c("trunk"), ghost: false });
  bones.push({ a: p("hip", 1), b: p("hip", -1), r: 0.07, color: c("trunk"), ghost: false });
  bones.push({ a: neckBase, b: [head[0] - 0.02, head[1] - 0.06, 0], r: 0.045, color: c("neck"), ghost: !pose.ear.visible });

  return (
    <group>
      {bones.map((b, i) => (
        <Bone key={i} a={b.a} b={b.b} radius={b.r} color={b.color} ghost={b.ghost} />
      ))}
      <mesh position={head} castShadow>
        <sphereGeometry args={[0.1, 32, 24]} />
        <meshStandardMaterial color={c("head_offset")} roughness={0.3} emissive={c("head_offset")} emissiveIntensity={0.15} transparent={!pose.ear.visible} opacity={pose.ear.visible ? 1 : 0.2} />
      </mesh>
      {/* nose: shows where the face points */}
      <mesh position={[head[0] + 0.1, head[1] - 0.01, 0]}>
        <sphereGeometry args={[0.018, 12, 8]} />
        <meshStandardMaterial color="#e2e8f0" />
      </mesh>
      {backCurve && (
        <Torso
          shoulder={[pose.shoulder.x, pose.shoulder.y]}
          hip={[pose.hip.x, pose.hip.y]}
          back={pose.back}
          upper={c("upper_back")}
          lower={c("lower_back")}
        />
      )}
    </group>
  );
}

/**
 * Solid torso whose back surface is the measured back silhouette: rings stacked from
 * shoulder to hip, each spanning from the back contour to a chest estimated by mirroring
 * the back across the shoulder–hip line. Coloured from upper-back to lower-back.
 */
function Torso({ shoulder, hip, back, upper, lower }: { shoulder: [number, number]; hip: [number, number]; back: [number, number][]; upper: string; lower: string }) {
  const geom = useMemo(() => {
    const LEVELS = 16, SEG = 28;
    const pts = [...back].sort((a, b) => b[1] - a[1]); // top (higher y) first
    const lineX = (y: number) => {
      const f = (shoulder[1] - y) / (shoulder[1] - hip[1] || 1e-6);
      return shoulder[0] + (hip[0] - shoulder[0]) * f;
    };
    // back offset (how far behind the shoulder–hip line) at height y, clamped to the contour's ends
    const offsetAt = (y: number) => {
      if (y >= pts[0][1]) return lineX(pts[0][1]) - pts[0][0];
      const last = pts[pts.length - 1];
      if (y <= last[1]) return lineX(last[1]) - last[0];
      for (let i = 0; i < pts.length - 1; i++) {
        const [a, b] = [pts[i], pts[i + 1]];
        if (y <= a[1] && y >= b[1]) {
          const t = (a[1] - y) / (a[1] - b[1] || 1e-6);
          return lineX(a[1]) - a[0] + t * (lineX(b[1]) - b[0] - (lineX(a[1]) - a[0]));
        }
      }
      return 0.1;
    };
    const cu = new THREE.Color(upper), cl = new THREE.Color(lower);
    const pos: number[] = [], col: number[] = [], idx: number[] = [];
    const top = shoulder[1] + 0.03, bottom = hip[1] - 0.04;
    for (let l = 0; l <= LEVELS; l++) {
      const f = l / LEVELS;
      const y = top + (bottom - top) * f;
      const lx = lineX(y);
      const off = Math.max(0.05, offsetAt(y));
      const bx = lx - off, fx = lx + off * 0.55;
      const cx = (bx + fx) / 2, a = (fx - bx) / 2;
      // width: shoulders → waist → pelvis; rounded off at the very top
      const w = (0.2 - 0.045 * Math.sin(Math.PI * Math.min(1, f * 1.3))) * (f < 0.08 ? 0.75 + 3 * f : 1);
      const color = cu.clone().lerp(cl, Math.min(1, Math.max(0, (f - 0.35) / 0.3)));
      for (let k = 0; k < SEG; k++) {
        const t = (k / SEG) * Math.PI * 2;
        pos.push(cx + a * Math.cos(t), y, w * Math.sin(t));
        col.push(color.r, color.g, color.b);
      }
    }
    for (let l = 0; l < LEVELS; l++)
      for (let k = 0; k < SEG; k++) {
        const a = l * SEG + k, b = l * SEG + ((k + 1) % SEG), c2 = a + SEG, d = b + SEG;
        idx.push(a, c2, b, b, c2, d);
      }
    // caps
    for (const [l, flip] of [[0, false], [LEVELS, true]] as const) {
      const ring = l * SEG;
      let cx = 0, cy = 0;
      for (let k = 0; k < SEG; k++) { cx += pos[(ring + k) * 3]; cy += pos[(ring + k) * 3 + 1]; }
      const centre = pos.length / 3;
      pos.push(cx / SEG, cy / SEG, 0);
      col.push(...col.slice(ring * 3, ring * 3 + 3));
      for (let k = 0; k < SEG; k++) {
        const a = ring + k, b = ring + ((k + 1) % SEG);
        flip ? idx.push(centre, b, a) : idx.push(centre, a, b);
      }
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
    g.setAttribute("color", new THREE.Float32BufferAttribute(col, 3));
    g.setIndex(idx);
    g.computeVertexNormals();
    return g;
  }, [shoulder[0], shoulder[1], hip[0], hip[1], back, upper, lower]);
  return (
    <mesh geometry={geom} castShadow>
      <meshStandardMaterial vertexColors roughness={0.4} emissive="#1a1030" side={THREE.DoubleSide} />
    </mesh>
  );
}

function Box({ from, to, z = 0.6, y0, color = "#64748b", opacity = 1 }: { from: [number, number]; to: [number, number]; z?: number; y0?: number; color?: string; opacity?: number }) {
  const x = (from[0] + to[0]) / 2;
  const y = (from[1] + to[1]) / 2;
  const w = Math.max(0.015, Math.abs(to[0] - from[0]));
  const h = Math.max(0.015, Math.abs(to[1] - from[1]));
  return (
    <mesh position={[x, y0 ?? y, 0]} castShadow receiveShadow>
      <boxGeometry args={[w, h, z]} />
      <meshStandardMaterial color={color} roughness={0.6} transparent={opacity < 1} opacity={opacity} depthWrite={opacity === 1} />
    </mesh>
  );
}

function Screen({ top, bottom, width, label }: { top: [number, number]; bottom: [number, number]; width: number; label: string }) {
  const centre = new THREE.Vector3((top[0] + bottom[0]) / 2, (top[1] + bottom[1]) / 2, 0);
  const h = Math.hypot(top[0] - bottom[0], top[1] - bottom[1]);
  const tilt = Math.atan2(top[0] - bottom[0], top[1] - bottom[1]);
  return (
    <group position={centre} rotation={[0, 0, -tilt]}>
      <mesh castShadow>
        <boxGeometry args={[0.025, h, width]} />
        <meshStandardMaterial color="#1e293b" roughness={0.4} />
      </mesh>
      <mesh position={[-0.014, 0, 0]}>
        <boxGeometry args={[0.002, h * 0.94, width * 0.96]} />
        <meshStandardMaterial color="#38bdf8" emissive="#38bdf8" emissiveIntensity={0.55} />
      </mesh>
      <Html position={[0, h / 2 + 0.05, 0]} center className="scene-label">{label}</Html>
    </group>
  );
}

function WorkstationObjects({ ws, floorY }: { ws: Workstation; floorY: number }) {
  const o = ws.objects;
  const deskY = o.desk?.front_edge?.[1];
  const deskFront = o.desk?.front_edge?.[0];
  const deskBack = o.desk?.back_edge?.[0] ?? (deskFront !== undefined ? deskFront + 0.6 : undefined);
  return (
    <group>
      {deskY !== undefined && deskFront !== undefined && deskBack !== undefined && (
        <group>
          <Box from={[deskFront, deskY - 0.03]} to={[deskBack, deskY]} z={1.3} color="#c8a97e" opacity={0.55} />
          {[deskFront + 0.03, deskBack - 0.03].flatMap((x) => [-0.6, 0.6].map((z) => (
            <mesh key={`${x}${z}`} position={[x, (deskY + floorY) / 2, z]}>
              <boxGeometry args={[0.025, deskY - floorY, 0.025]} />
              <meshStandardMaterial color="#e2e8f0" transparent opacity={0.4} />
            </mesh>
          )))}
        </group>
      )}
      {o.monitor?.top && o.monitor?.bottom && <Screen top={o.monitor.top} bottom={o.monitor.bottom} width={0.6} label="monitor" />}
      {o.monitor?.bottom && deskY !== undefined && o.monitor.bottom[1] > deskY && (
        <mesh position={[o.monitor.bottom[0] + 0.06, (o.monitor.bottom[1] + deskY) / 2, 0]}>
          <boxGeometry args={[0.03, o.monitor.bottom[1] - deskY, 0.06]} />
          <meshStandardMaterial color="#334155" />
        </mesh>
      )}
      {o.laptop_screen?.top && o.laptop_screen?.bottom && <Screen top={o.laptop_screen.top} bottom={o.laptop_screen.bottom} width={0.31} label="laptop" />}
      {o.keyboard && (() => {
        const pts = Object.values(o.keyboard);
        const xs = pts.map((p) => p[0]);
        const y = pts.reduce((a, p) => a + p[1], 0) / pts.length;
        const x0 = Math.min(...xs), x1 = Math.max(...xs, x0 + 0.12);
        return <Box from={[x0, y - 0.012]} to={[x1, y + 0.012]} z={0.32} color="#94a3b8" />;
      })()}
      {o.seat?.front && (() => {
        const back = o.seat.back ?? [o.seat.front[0] - 0.45, o.seat.front[1]];
        const y = (o.seat.front[1] + back[1]) / 2;
        return (
          <group>
            <Box from={[back[0], y - 0.05]} to={[o.seat.front[0], y]} z={0.46} color="#475569" />
            <mesh position={[(back[0] + o.seat.front[0]) / 2, (y + floorY) / 2, 0]}>
              <cylinderGeometry args={[0.025, 0.025, Math.max(0.01, y - floorY), 12]} />
              <meshStandardMaterial color="#334155" />
            </mesh>
          </group>
        );
      })()}
      {o.backrest?.top && o.backrest?.bottom && <Box from={[o.backrest.bottom[0] - 0.03, o.backrest.bottom[1]]} to={[o.backrest.top[0], o.backrest.top[1]]} z={0.44} color="#475569" opacity={0.7} />}
    </group>
  );
}

export function PostureScene({ pose, workstation, highlight, height = 520 }: { pose: Sagittal | null; workstation?: Workstation | null; highlight?: string | null; height?: number | string }) {
  const floorY = useMemo(() => {
    const ys = [pose?.ankle, pose?.heel, pose?.toe].filter((p) => p?.visible).map((p) => p!.y);
    const fromWs = workstation?.objects.floor?.point?.[1];
    return fromWs ?? (ys.length ? Math.min(...ys) - 0.04 : -0.5);
  }, [pose, workstation]);
  return (
    <div className="scene" style={{ height }}>
      <Canvas shadows camera={{ position: [0.6, 0.95, 2.7], fov: 38 }} dpr={[1, 2]}>
        <color attach="background" args={["#0b0f19"]} />
        <fog attach="fog" args={["#0b0f19", 4, 9]} />
        <ambientLight intensity={0.5} />
        <directionalLight position={[2, 4, 3]} intensity={1.6} castShadow shadow-mapSize={[1024, 1024]} />
        <pointLight position={[-2, 1.5, -2]} intensity={6} color="#7c3aed" />
        <group position={[-0.3, 0.1, 0]}>
          {pose && <Body pose={pose} highlight={highlight} />}
          {workstation && <WorkstationObjects ws={workstation} floorY={floorY} />}
          <gridHelper args={[6, 30, "#1f2a44", "#141b2d"]} position={[0, floorY, 0]} />
          <ContactShadows position={[0, floorY + 0.001, 0]} opacity={0.5} scale={4} blur={2.2} far={2} />
        </group>
        <OrbitControls enablePan={false} minDistance={1.2} maxDistance={5} target={[0.15, 0.15, 0]} maxPolarAngle={Math.PI * 0.55} />
      </Canvas>
      {!pose && <div className="scene-empty">Waiting for a pose…</div>}
    </div>
  );
}
