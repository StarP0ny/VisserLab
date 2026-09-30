"""Папка прогона — единица эксперимента.

runs/<YYYY-MM-DD_HHMMSS>_<name>/
  meta.yaml      копия stand.yaml на момент старта + время, заметка, версия кода
  events.jsonl   события: operator (метки) и system (связь, старт/стоп)
  <source>.csv   по файлу на источник; у каждого свой темп, общая шкала — t_unix

В файлы пишется то, что отдал прибор, без поправок. Калибровки и привязка
«канал -> точка стенда» живут в meta.yaml и применяются при анализе.
"""
import json
import subprocess
import threading
import time
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]


def code_version():
    """Коммит + признак грязного дерева: какой код писал этот прогон."""
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO,
                             capture_output=True, text=True, timeout=5).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--", "visserlab"], cwd=REPO,
                               capture_output=True, text=True, timeout=5).stdout.strip()
        return sha + ("-dirty" if dirty else "")
    except (OSError, subprocess.SubprocessError):
        return "unknown"


class Run:
    def __init__(self, runs_dir, name, stand, note=""):
        self.started = time.time()
        stamp = time.strftime("%Y-%m-%d_%H%M%S", time.localtime(self.started))
        self.dir = Path(runs_dir) / (f"{stamp}_{name}" if name else stamp)
        self.dir.mkdir(parents=True, exist_ok=False)

        self.meta = {
            "run": self.dir.name,
            "started_unix": round(self.started, 3),
            "started_local": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.started)),
            "note": note,
            "code": code_version(),
            "stand": stand,
        }
        self._write_meta()
        self._ev_lock = threading.Lock()
        self._ev = open(self.dir / "events.jsonl", "a", encoding="utf-8")
        self.n_marks = 0

    def _write_meta(self):
        with open(self.dir / "meta.yaml", "w", encoding="utf-8") as f:
            yaml.safe_dump(self.meta, f, allow_unicode=True, sort_keys=False)

    def event(self, text, src="operator"):
        rec = {"t_unix": round(time.time(), 3), "src": src, "text": text}
        with self._ev_lock:
            self._ev.write(json.dumps(rec, ensure_ascii=False) + "\n")
            self._ev.flush()
        return rec

    def mark(self, text=""):
        self.n_marks += 1
        return self.event(text or f"метка {self.n_marks}")

    def close(self, summary):
        ended = time.time()
        self.meta["ended_unix"] = round(ended, 3)
        self.meta["duration_s"] = round(ended - self.started, 1)
        self.meta["summary"] = summary
        self._write_meta()
        with self._ev_lock:
            self._ev.close()
