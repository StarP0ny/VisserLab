"""Запись без веб-интерфейса: сборщик в этом же процессе, управление из консоли.

  Enter          метка
  текст + Enter  заметка
  p              пауза / продолжить
  q              стоп
"""
import sys
import threading
import time

from .core.collector import Collector, CollectorError, fmt_dur
from .core.driver import fmt_num

GLYPH = {"user": "✎", "mark": "▸", "sys": "·", "state": "●", "set": "⚙", "manual": "✚", "warn": "⚠", "crit": "✕"}
STATUS_EVERY_S = 10
BY = "консоль"


class ConsoleLog:
    """Печатает журнал и раз в STATUS_EVERY_S секунд строку значений."""
    frames = False

    def __init__(self, coll, status_every=STATUS_EVERY_S):
        self.coll, self.every, self.next = coll, status_every, time.time() + 2

    def send(self, msg):
        typ = msg["type"]
        if typ == "event":
            e = msg["event"]
            by = f"  · {e['by']}" if e.get("by") else ""
            print(f"  {time.strftime('%H:%M:%S', time.localtime(e['t']))}  {GLYPH.get(e['kind'], '·')} {e['text']}{by}", flush=True)
        elif typ == "status" and self.every and time.time() >= self.next:
            self.next = time.time() + self.every
            print(self._status(msg), flush=True)

    def _status(self, msg):
        el = fmt_dur(msg["elapsed"]) if msg.get("elapsed") is not None else "подготовка"
        parts = []
        for d in self.coll.devices.values():
            vis = [c for c in d.channels.values() if c.kind == "scalar" and not c.hidden][:6]
            vals = []
            for c in vis:
                v = msg["last"].get(f"{d.id}:{c.key}")
                vals.append(f"{c.key}={fmt_num(v, c.dp)}" if isinstance(v, float) else f"{c.key}=—")
            if vals:
                parts.append(f"{d.name}: " + " ".join(vals))
        lvl = {"ok": "", "warn": "  ⚠", "crit": "  ✕"}[msg["alarms"]["level"]]
        return f"[{el}]{lvl}  " + " | ".join(parts)


def record(cfg, name="", note="", devices=None, template=None, duration=None):
    coll = Collector(cfg).launch()
    coll.subscribe(ConsoleLog(coll))
    try:
        if not devices and not template:
            devices = cfg.record_default
        coll.request("prepare", name=name, devices=devices, template=template, note=note, by=BY)
        res = coll.request("start", by=BY)
        print(f"Опыт: {res['dir']}")
        print("Enter — метка, текст — заметка, p — пауза, q — стоп"
              + (f"; автостоп через {duration:g} с" if duration else ""), flush=True)
        stop = threading.Event()
        threading.Thread(target=_stdin, args=(coll, stop, bool(duration)), daemon=True).start()
        deadline = time.time() + duration if duration else None
        while not stop.is_set():                  # короткие ожидания: Ctrl-C на Windows
            if deadline and time.time() >= deadline:
                break
            stop.wait(0.2)
    except CollectorError as e:
        print(f"Ошибка: {e}", file=sys.stderr)
    except KeyboardInterrupt:
        pass
    finally:
        run = _finish(coll)
        coll.close(by=BY)
        if run:
            print(f"\nЗаписано {fmt_dur(run['duration_s'])} → {run['dir']}")


def _finish(coll):
    try:
        if coll.state == "rec":
            coll.request("pause", by=BY)
        if coll.state == "pause":
            return coll.request("stop", by=BY)
        if coll.state == "prep":
            coll.request("cancel", by=BY)
    except CollectorError as e:
        print(f"Ошибка: {e}", file=sys.stderr)
    return None


def _stdin(coll, stop, has_duration):
    while not stop.is_set():
        line = sys.stdin.readline()
        if not line:                              # EOF
            if not has_duration:
                stop.set()
            return
        text = line.strip()
        try:
            if text.lower() == "q":
                stop.set()
                return
            if text.lower() == "p":
                coll.request("pause" if coll.state == "rec" else "resume", by=BY)
            else:
                coll.request("note", text=text, by=BY)
        except CollectorError as e:
            print(f"  {e}", flush=True)
