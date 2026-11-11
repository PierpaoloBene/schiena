"""On-disk layout under the data directory (default ``./data``, override with SCHIENA_DATA).

data/
├── sessions/<id>/session.json   metadata + summary + discomfort
│                 samples.jsonl  one Sample per line (1 fps)
│                 frames/*.jpg   a few frames per minute, named by second
│                 report.md      written by Claude (/report)
├── workstation.json             reconstructed Workstation (/calibrate)
├── profile.json                 height + relaxed standing reference (Calibrate)
├── photos/                      optional Workstation photos
└── history.json                 Interventions and Outcomes
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path


def data_dir() -> Path:
    return Path(os.environ.get("SCHIENA_DATA", "data")).resolve()


def sessions_dir() -> Path:
    return data_dir() / "sessions"


def session_dir(session_id: str) -> Path:
    d = (sessions_dir() / session_id).resolve()
    if d.parent != sessions_dir().resolve():
        raise ValueError("invalid session id")
    return d


def new_session_id(now: datetime | None = None) -> str:
    return (now or datetime.now()).strftime("%Y-%m-%d_%H-%M-%S")


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return default


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False))
    tmp.replace(path)


def read_samples(session_id: str) -> list[dict]:
    path = session_dir(session_id) / "samples.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def load_session(session_id: str) -> dict | None:
    meta = read_json(session_dir(session_id) / "session.json")
    if meta is None:
        return None
    meta["id"] = session_id
    d = session_dir(session_id)
    meta["frames"] = sorted(p.name for p in (d / "frames").glob("*.jpg")) if (d / "frames").exists() else []
    meta["has_report"] = (d / "report.md").exists()
    return meta


def list_sessions() -> list[dict]:
    if not sessions_dir().exists():
        return []
    out = [load_session(p.name) for p in sorted(sessions_dir().iterdir(), reverse=True) if p.is_dir()]
    return [s for s in out if s]


def history_path() -> Path:
    return data_dir() / "history.json"


def load_history() -> dict:
    return read_json(history_path(), {"interventions": []})


def save_history(h: dict) -> None:
    write_json(history_path(), h)


def profile_path() -> Path:
    return data_dir() / "profile.json"


def load_profile() -> dict:
    return read_json(profile_path(), {})


def save_profile(p: dict) -> None:
    write_json(profile_path(), p)


def workstation_path() -> Path:
    return data_dir() / "workstation.json"


class SessionWriter:
    """Appends Samples and frames for a running Session."""

    def __init__(self, session_id: str, meta: dict):
        self.id = session_id
        self.dir = session_dir(session_id)
        (self.dir / "frames").mkdir(parents=True, exist_ok=True)
        self.meta = meta
        write_json(self.dir / "session.json", meta)
        self._samples = open(self.dir / "samples.jsonl", "a")

    def add_sample(self, sample: dict) -> None:
        self._samples.write(json.dumps(sample, separators=(",", ":")) + "\n")
        self._samples.flush()

    def add_frame(self, t: float, jpeg: bytes) -> str:
        name = f"{int(t):05d}.jpg"
        (self.dir / "frames" / name).write_bytes(jpeg)
        return name

    def finish(self, meta_update: dict) -> dict:
        self._samples.close()
        self.meta.update(meta_update)
        write_json(self.dir / "session.json", self.meta)
        return self.meta
