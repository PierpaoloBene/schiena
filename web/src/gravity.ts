// The phone's gravity vector, sent with each frame so the computer can undo the phone's tilt.
// iOS asks for permission once ("motion and orientation"); it must be requested from a tap.

type Vec = [number, number, number];

let last: Vec | null = null;
let listening = false;

/** Call synchronously from a tap handler (before any await), so iOS can show its prompt. */
export function startGravity(): Promise<void> {
  const DME = (window as unknown as { DeviceMotionEvent?: { requestPermission?: () => Promise<string> } }).DeviceMotionEvent;
  const ask = DME?.requestPermission ? DME.requestPermission().catch(() => "denied") : Promise.resolve("granted");
  return ask.then((answer) => {
    if (answer !== "granted" || listening) return;
    listening = true;
    window.addEventListener("devicemotion", (e) => {
      const g = e.accelerationIncludingGravity;
      if (g?.x == null || g.y == null || g.z == null) return;
      const k = 0.15; // smoothing: the phone is propped up, hand jitter isn't
      last = last ? [last[0] + (g.x - last[0]) * k, last[1] + (g.y - last[1]) * k, last[2] + (g.z - last[2]) * k] : [g.x, g.y, g.z];
    });
  });
}

export function gravity(): string | null {
  return last ? last.map((v) => v.toFixed(3)).join(",") : null;
}
