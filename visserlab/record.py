"""Регистратор прогона.

Каждый источник — свой поток и свой файл; падение одного не трогает остальные.
Метки оператора приходят построчно со stdin: сейчас из консоли, позже web-UI
будет запускать регистратор подпроцессом и писать в тот же stdin.

  Enter          быстрая метка («метка N»), текст дописать потом
  текст + Enter  метка с текстом
  q              стоп
"""
import sys
import threading
import time
from pathlib import Path

import yaml

from .run import REPO, Run
from .sources.pt100 import Pt100Source

SOURCES = {"pt100": Pt100Source}
STATUS_EVERY_S = 10


def load_stand(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _status_line(run, sources):
    parts = [f"[{time.time() - run.started:6.0f} с]"]
    for s in sources:
        if s.latest is None:
            parts.append(f"{s.name}: нет данных")
            continue
        _, T, _ = s.latest
        parts.append("  ".join(f"{label}={T[ch - 1]}" for ch, label in s.labels()))
        if s.n_fail:
            parts.append(f"(сбоев {s.n_fail})")
    return "  ".join(parts)


def _stdin_loop(run, stop, has_duration):
    while not stop.is_set():
        line = sys.stdin.readline()
        if not line:  # EOF: консоль закрыта или UI отпустил pipe
            if not has_duration:
                stop.set()
            return
        text = line.strip()
        if text.lower() == "q":
            stop.set()
            return
        rec = run.mark(text)
        print(f"  ✓ {time.strftime('%H:%M:%S', time.localtime(rec['t_unix']))}  {rec['text']}",
              flush=True)


def record(config, name="", note="", duration=None, runs_dir=None):
    stand = load_stand(config)
    runs_dir = Path(runs_dir or REPO / stand.get("runs_dir", "runs"))
    run = Run(runs_dir, name, stand, note)

    sources = [SOURCES[key](cfg, run) for key, cfg in (stand.get("sources") or {}).items()
               if key in SOURCES and cfg.get("enabled", True)]
    if not sources:
        sys.exit("В stand.yaml нет включённых источников")

    print(f"Прогон: {run.dir}")
    print("Enter — метка, текст+Enter — метка с текстом, q — стоп"
          + (f"; автостоп через {duration:g} с" if duration else ""), flush=True)

    run.event("старт записи", "system")
    for s in sources:
        s.start()

    stop = threading.Event()
    threading.Thread(target=_stdin_loop, args=(run, stop, bool(duration)), daemon=True).start()

    deadline = run.started + duration if duration else None
    next_status = time.time() + 2
    try:
        # короткие ожидания: на Windows Ctrl-C не прерывает долгий Event.wait()
        while not stop.is_set():
            now = time.time()
            if deadline and now >= deadline:
                break
            if now >= next_status:
                print(_status_line(run, sources), flush=True)
                next_status = now + STATUS_EVERY_S
            stop.wait(0.2)
    except KeyboardInterrupt:
        pass
    finally:
        for s in sources:
            s.stop()
        run.event("стоп записи", "system")
        summary = {s.name: s.summary() for s in sources}
        summary["marks"] = run.n_marks
        run.close(summary)
        print(f"\nСтоп. {summary}\nЛежит в {run.dir}")
    return run
