import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./app.css";
import { Camera } from "./pages/Camera";
import { Live } from "./pages/Live";
import { Progress } from "./pages/Progress";
import { SessionDetail, Sessions } from "./pages/Sessions";
import { CalibrationPage } from "./pages/CalibrationPage";
import { Link, usePath } from "./router";

const NAV: [string, string][] = [
  ["/", "Live"],
  ["/sessions", "Sessions"],
  ["/progress", "Progress"],
  ["/calibration", "Calibration"],
];

function App() {
  const path = usePath();
  if (path.startsWith("/camera")) return <Camera />;
  const session = path.match(/^\/sessions\/([\w-]+)/);
  const page = session ? (
    <SessionDetail id={session[1]} />
  ) : path.startsWith("/sessions") ? (
    <Sessions />
  ) : path.startsWith("/progress") ? (
    <Progress />
  ) : (path.startsWith("/calibration") || path.startsWith("/workstation")) ? (
    <CalibrationPage />
  ) : (
    <Live />
  );
  return (
    <div className="shell">
      <nav className="nav">
        <Link to="/" className="brand">
          <img src="/icon.svg" alt="" />
          Schiena
        </Link>
        <div className="nav-links">
          {NAV.map(([to, label]) => (
            <Link key={to} to={to} className={(to === "/" ? path === "/" : path.startsWith(to)) ? "active" : ""}>
              {label}
            </Link>
          ))}
        </div>
      </nav>
      <main>{page}</main>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
