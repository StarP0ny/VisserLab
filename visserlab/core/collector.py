"""Сборщик: приборы, состояние опыта, запись, журнал, тревоги.

Всё состояние меняет один поток — диспетчер. Потоки приборов и команды
клиентов кладут сообщения в одну очередь, поэтому «Старт» попадает ровно
между двумя отсчётами, а блокировки не нужны.

  IDLE ──prepare──▶ PREP ──start──▶ REC ⇄ PAUSE ──stop──▶ IDLE
                    PREP ──cancel──▶ IDLE   (на диске ничего не остаётся)
"""
import base64
import queue
import re
import sys
import threading
import time
import traceback
from collections import defaultdict
from concurrent.futures import Future
from pathlib import Path

import numpy as np

from ..config import code_version
from .alarms import Alarms, RuleError
from .buffers import History, Ring
from .driver import ARRAY_KINDS, KINDS, REGISTRY, DriverError, Found
from .storage import RunStorage

IDLE, PREP, REC, PAUSE = "idle", "prep", "rec", "pause"
STATE_RU = {IDLE: "нет опыта", PREP: "подготовка", REC: "запись", PAUSE: "пауза"}
RETRY_S = 2.0          # пауза перед повторным открытием отвалившегося прибора
WAIT_GRACE_S = 5.0     # сколько ждать первых данных после открытия


class CollectorError(Exception):
    """Команда не выполнена; текст — для человека."""


def fmt_dur(sec):
    a = max(0, round(sec))
    return f"{a // 3600}:{a % 3600 // 60:02d}:{a % 60:02d}"


def _reason(e):
    if isinstance(e, DriverError):
        return str(e)
    return f"{type(e).__name__}: {e}" if str(e) else type(e).__name__


class _Ctx:
    def __init__(self, coll, dev_id):
        self.c, self.dev_id = coll, dev_id

    def emit(self, values, t=None, dev=None):
        self.c._q.put(("S", dev or self.dev_id, time.time() if t is None else t, values))

    def online(self, ok, reason=""):
        self.c._q.put(("L", self.dev_id, ok, reason))

    def t0(self):
        return self.c.t0


class Device:
    """Прибор в текущем опыте: драйвер, его поток и статус."""

    def __init__(self, dev_id, inv, ctx):
        cls = REGISTRY.get(inv.get("driver"))
        if cls is None:
            raise CollectorError(f"{dev_id}: нет драйвера «{inv.get('driver')}»")
        self.id, self.inv, self.parent = dev_id, inv, inv.get("parent")
        self.drv = cls(dev_id, inv.get("name"), inv.get("settings"), ctx)
        self.names = {str(k): v for k, v in (inv.get("channels") or {}).items()}
        self.status, self.reason, self.since = "wait", "", time.time()
        self.last_t, self.samples = None, 0
        self.thread, self.stop = None, threading.Event()
        self.closing = self.restart = False
        self.channels = {}
        self.refresh_channels()

    @property
    def name(self):
        return self.drv.name

    @property
    def threaded(self):
        return self.drv.group in ("direct", "gateway")

    def refresh_channels(self):
        new = {}
        for ch in self.drv.channels():
            if ch.kind not in KINDS:
                raise CollectorError(f"{self.name}: канал {ch.key} неизвестного типа {ch.kind}")
            ch.name = self.names.get(ch.key, ch.name)
            new[ch.key] = ch
        changed = [c.signature() for c in new.values()] != [c.signature() for c in self.channels.values()]
        self.channels = new
        return changed

    def rate(self):
        return max((c.rate for c in self.channels.values()), default=0)

    def array_keys(self):
        return {k for k, c in self.channels.items() if c.kind in ARRAY_KINDS}

    def info(self):
        d = self.drv
        return {"id": self.id, "name": self.name, "driver": d.type_id, "model": d.model, "icon": d.icon,
                "group": d.group, "parent": self.parent, "status": self.status, "reason": self.reason,
                "settings": dict(d.cfg), "schema": [f.to_dict() for f in d.settings],
                "channels": [c.to_dict() for c in self.channels.values()]}


class Collector:
    def __init__(self, cfg):
        self.cfg = cfg
        self._q = queue.Queue()
        self._subs, self._sub_lock = [], threading.Lock()
        self._thread, self._alive = None, False
        self.found = {}
        self.last_run = None
        self._reset()

    def _reset(self):
        self.state = IDLE
        self.devices: dict[str, Device] = {}
        self.t0 = None
        self.session = None
        self.storage = None
        self.hist: dict[str, History] = {}
        self.rings: dict[str, Ring] = {}
        self.last: dict[str, tuple] = {}
        self._calc_by_input = defaultdict(list)
        self._pend = defaultdict(list)
        self._pend_arr = {}
        self._frame_sent = {}
        self.alarms = Alarms([], self._journal, self._describe)

    # ================= запуск, остановка, подписчики =================
    def launch(self):
        self._alive = True
        self._thread = threading.Thread(target=self._loop, name="dispatcher", daemon=True)
        self._thread.start()
        return self

    def close(self, by="сборщик"):
        """Останавливает сборщик. Идущий опыт останавливается и сохраняется."""
        if not self._alive:
            return
        try:
            self.request("shutdown", by=by)
        finally:
            self._thread.join(timeout=15)

    def subscribe(self, sub):
        """sub.send(msg: dict) вызывается из потока диспетчера и не должен блокировать;
        sub.frames — нужны ли ему кадры."""
        with self._sub_lock:
            self._subs.append(sub)

    def unsubscribe(self, sub):
        with self._sub_lock:
            if sub in self._subs:
                self._subs.remove(sub)

    def _publish(self, msg, frames=False):
        with self._sub_lock:
            subs = list(self._subs)
        for s in subs:
            if frames and not getattr(s, "frames", False):
                continue
            try:
                s.send(msg)
            except Exception:
                traceback.print_exc()

    def _wants_frames(self):
        with self._sub_lock:
            return any(getattr(s, "frames", False) for s in self._subs)

    # ================= команды =================
    def request(self, cmd, **args):
        """Выполняет команду в потоке диспетчера и возвращает результат.
        Потокобезопасно: так команды приходят из сервера и консоли."""
        if cmd == "discover":           # опрашивает железо — не держим очередь
            return self._discover()
        fn = getattr(self, "_cmd_" + cmd, None)
        if fn is None:
            raise CollectorError(f"Нет команды «{cmd}»")
        if threading.current_thread() is self._thread:
            return fn(**args)
        if not self._alive:
            raise CollectorError("Сборщик остановлен")
        fut = Future()
        self._q.put(("C", fn, args, fut))
        return fut.result(timeout=60)

    def _need(self, *states):
        if self.state not in states:
            raise CollectorError(f"Сейчас {STATE_RU[self.state]}: команда недоступна")

    def _dev(self, dev_id):
        d = self.devices.get(dev_id)
        if d is None:
            raise CollectorError(f"Прибор «{dev_id}» не в опыте")
        return d

    def _cmd_hello(self):
        s = self.session
        return {
            "state": self.state, "t": time.time(),
            "session": None if s is None else {
                "name": s["name"], "note": s["note"], "t0": self.t0, "pauses": s["pauses"],
                "prepared": s["prepared"], "dir": str(self.storage.dir) if self.storage else None,
                "alarms": s["rules"]},
            "last_run": self.last_run,
            "devices": [d.info() for d in self.devices.values()],
            "inventory": self._inventory(),
            "templates": {k: {"name": v.get("name", k), "devices": v.get("devices", [])}
                          for k, v in self.cfg.templates.items()},
            "alarms": self.alarms.state(),
            "events": list(s["events"]) if s else [],
            "last": self._last_scalars(),
        }

    def _inventory(self):
        out = []
        for i, inv in self.cfg.devices.items():
            cls = REGISTRY[inv["driver"]]
            out.append({"id": i, "name": inv.get("name") or cls.title, "parent": inv.get("parent"),
                        "settings": {**cls.defaults(), **(inv.get("settings") or {})},
                        "found": self.found.get(i), **cls.describe()})
        return out

    def _discover(self):
        busy = dict(self.devices)
        res = {}
        for i, inv in self.cfg.devices.items():
            if inv.get("parent"):
                continue
            cls = REGISTRY[inv["driver"]]
            kids = {c: ci for c, ci in self.cfg.devices.items() if ci.get("parent") == i}
            if i in busy:
                f = Found(busy[i].status == "ok", "в работе", [c for c in kids if c in busy])
            else:
                try:
                    f = cls.discover({**cls.defaults(), **cls.validate(inv.get("settings") or {})}, kids)
                except Exception as e:
                    f = Found(False, _reason(e))
            res[i] = {"ok": f.ok, "note": f.note}
            for c in kids:
                ok = f.ok and c in f.children
                res[c] = {"ok": ok, "note": "" if ok else
                          f"{inv.get('name', i)}: {'нет ответа от прибора' if f.ok else 'нет связи'}"}
        self.found = res
        self._publish({"type": "found", "found": res})
        return res

    def _cmd_prepare(self, name="", devices=None, template=None, settings=None, note="", alarms=None, by=""):
        self._need(IDLE)
        tpl = {}
        if template:
            tpl = self.cfg.templates.get(template)
            if tpl is None:
                raise CollectorError(f"Нет шаблона «{template}»")
        ids = [str(i) for i in (devices or tpl.get("devices") or [])]
        if not ids:
            raise CollectorError("Не выбраны приборы")
        inv = self.cfg.devices
        for i in ids:
            if i not in inv:
                raise CollectorError(f"Нет прибора «{i}»")
        full = []
        for i in ids:                     # шлюз поднимается сам, если выбран хоть один его ребёнок
            p = inv[i].get("parent")
            if p and p not in full:
                full.append(p)
        full += [i for i in ids if i not in full]
        over = {**(tpl.get("settings") or {}), **(settings or {})}
        devs = {}
        try:
            for i in full:
                d = dict(inv[i])
                d["settings"] = {**(d.get("settings") or {}), **(over.get(i) or {})}
                devs[i] = Device(i, d, _Ctx(self, i))
            for d in devs.values():
                if d.parent:
                    devs[d.parent].drv.attach(d.drv)
        except DriverError as e:
            raise CollectorError(str(e)) from None
        calc_by = defaultdict(list)
        for d in devs.values():
            for cid in d.drv.inputs():
                if cid.split(":")[0] not in devs:
                    raise CollectorError(f"{d.name}: нужен прибор «{cid.split(':')[0]}»")
                calc_by[cid].append(d)
        rules = list(alarms if alarms is not None else tpl.get("alarms") or [])
        rules = [r for r in rules if str(r.get("channel", "")).split(":")[0] in devs]
        self.devices = devs
        try:
            self.alarms = Alarms(rules, self._journal, self._describe)
        except RuleError as e:
            self._reset()
            raise CollectorError(str(e)) from None
        self._calc_by_input = calc_by
        self.session = {"name": _safe_name(name or tpl.get("name") or "опыт"), "note": note, "rules": rules,
                        "events": [], "pauses": [], "marks": 0, "prepared": time.time(), "preroll": 0.0}
        for d in devs.values():
            self._index_channels(d)
            self.rings[d.id] = Ring(self.cfg.preroll_s, self.cfg.preroll_fps)
        self.state = PREP
        for d in devs.values():
            if d.threaded:
                self._spawn(d)
        self._journal("state", "Подготовка: " + ", ".join(devs[i].name for i in ids), by=by)
        self._publish_state()
        return self._cmd_hello()

    def _cmd_start(self, by=""):
        self._need(PREP)
        now = time.time()
        stamp = time.strftime("%Y-%m-%d_%H%M%S", time.localtime(now))
        self.storage = RunStorage(Path(self.cfg.runs_dir) / f"{stamp}_{self.session['name']}")
        first = now
        for d in self.devices.values():
            self.storage.add_device(d.id, list(d.channels.values()))
            items = self.rings[d.id].drain()
            for t, v in items:
                self.storage.write(d.id, t, v)
            if items:
                first = min(first, items[0][0])
        for ev in self.session["events"]:
            self.storage.event(ev)
        self.t0, self.state = now, REC
        self.session["preroll"] = now - first
        self._journal("state", f"Старт записи, предзапись {fmt_dur(now - first)}", t=now, by=by)
        self._write_meta()
        self._publish_state()
        return {"dir": str(self.storage.dir), "t0": now}

    def _cmd_pause(self, by=""):
        self._need(REC)
        now = time.time()
        self.session["pauses"].append([now, None])
        self.state = PAUSE
        self._journal("state", "Пауза", t=now, by=by)
        self._publish_state()

    def _cmd_resume(self, by=""):
        self._need(PAUSE)
        now = time.time()
        self.session["pauses"][-1][1] = now
        self.state = REC
        self._journal("state", "Продолжить", t=now, by=by)
        self._publish_state()

    def _cmd_stop(self, by=""):
        if self.state == REC:
            raise CollectorError("Стоп — только из паузы")
        self._need(PAUSE)
        now = time.time()
        self.session["pauses"][-1][1] = now
        self._journal("state", f"Стоп, записано {fmt_dur(now - self.t0)}", t=now, by=by)
        self._close_devices()
        self._write_meta(ended=now)
        self.storage.close()
        self.last_run = {"name": self.session["name"], "dir": str(self.storage.dir), "t0": self.t0,
                         "duration_s": round(now - self.t0, 3)}
        self._reset()
        self._publish_state()
        return self.last_run

    def _cmd_cancel(self, by=""):
        self._need(PREP)
        self._close_devices()
        self._reset()
        self._publish_state()

    def _cmd_note(self, text="", t=None, by=""):
        self._need(PREP, REC, PAUSE)
        text = (text or "").strip()
        if not text:
            return self._cmd_mark(by=by)
        return self._journal("user", text, t=float(t) if t else None, by=by)

    def _cmd_mark(self, by=""):
        self._need(PREP, REC, PAUSE)
        self.session["marks"] += 1
        return self._journal("mark", f"метка {self.session['marks']}", by=by)

    def _cmd_set(self, device, changes, by=""):
        self._need(PREP, REC, PAUSE)
        dev = self._dev(device)
        drv = dev.drv
        try:
            parsed = drv.validate(changes or {})
        except DriverError as e:
            raise CollectorError(str(e)) from None
        diff = {k: v for k, v in parsed.items() if drv.cfg.get(k) != v}
        if not diff:
            return {"changed": {}}
        fields = {k: drv.field(k) for k in diff}
        fixed = [f.label for f in fields.values() if not f.live]
        if self.state == REC and fixed:
            raise CollectorError(f"Идёт запись: {', '.join(fixed)} — меняется на паузе")
        old = {k: drv.cfg.get(k) for k in diff}
        if fixed:
            drv.cfg.update(diff)       # применится при переоткрытии прибора
            target = dev if dev.threaded else self.devices.get(dev.parent)
            if target is not None and target.thread is not None:
                target.restart = True
                target.stop.set()
        else:
            drv.apply(diff)
        self._channels_changed(dev)
        text = f"{dev.name}: " + "; ".join(
            f"{fields[k].label.lower()} {fields[k].show(old[k])} → {fields[k].show(diff[k])}" for k in diff)
        changed = {k: [old[k], diff[k]] for k in diff}
        self._journal("set", text, by=by, device=dev.id, changes=changed)
        return {"changed": changed}

    def _cmd_action(self, device, name, args=None, by=""):
        self._need(PREP, REC, PAUSE)
        dev = self._dev(device)
        if name == "reconnect":
            target = dev if dev.threaded else self.devices.get(dev.parent)
            if target is None or target.thread is None:
                raise CollectorError(f"{dev.name}: переподключать нечего")
            target.restart = True
            target.stop.set()
            self._journal("sys", f"{target.name}: переподключение", by=by, device=target.id)
            return {}
        try:
            res = dev.drv.action(name, args or {}) or {}
        except DriverError as e:
            raise CollectorError(str(e)) from None
        self._channels_changed(dev)
        if res.get("text"):
            self._journal(res.get("kind", "set"), res["text"], by=by, device=dev.id)
        return res

    def _cmd_history(self, channel, t_from=None, t_to=None, points=2000):
        h = self.hist.get(channel)
        if h is None:
            raise CollectorError(f"Нет скалярного канала «{channel}»")
        t, v = h.query(t_from, t_to, int(points))
        return {"channel": channel, "t": t, "v": v}

    def _cmd_shutdown(self, by="сборщик"):
        if self.state == REC:
            self._cmd_pause(by=by)
        if self.state == PAUSE:
            self._cmd_stop(by=by)
        elif self.state == PREP:
            self._cmd_cancel(by=by)
        self._alive = False
        return self.last_run

    # ================= приборы =================
    def _spawn(self, dev):
        dev.thread = threading.Thread(target=self._device_loop, args=(dev,), name=f"dev-{dev.id}", daemon=True)
        dev.thread.start()

    def _device_loop(self, dev):
        while not dev.closing:
            dev.stop.clear()
            failed = False
            try:
                dev.drv.open()
                dev.drv.run(dev.stop)
            except Exception as e:
                failed = True
                self._q.put(("L", dev.id, False, _reason(e)))
            finally:
                try:
                    dev.drv.close()
                except Exception:
                    pass
            if dev.closing:
                break
            if dev.restart:
                dev.restart = False
                continue
            if not failed and not dev.stop.is_set():
                self._q.put(("L", dev.id, False, "драйвер остановился"))
            dev.stop.wait(RETRY_S)

    def _close_devices(self):
        for d in self.devices.values():
            d.closing = True
            d.stop.set()
        for d in self.devices.values():
            if d.thread is not None:
                d.thread.join(timeout=5)

    def _index_channels(self, dev):
        for k, ch in dev.channels.items():
            if ch.kind in ("scalar", "points"):
                self.hist.setdefault(f"{dev.id}:{k}", History())

    def _channels_changed(self, dev):
        if not dev.refresh_channels():
            return
        self._index_channels(dev)
        for cid in [c for c in self.last if c.startswith(dev.id + ":") and c.split(":", 1)[1] not in dev.channels]:
            del self.last[cid]
        if self.storage is not None:
            self.storage.rollover(dev.id, list(dev.channels.values()))
        self._publish({"type": "device", "device": dev.info()})

    def _set_status(self, dev, status, reason=""):
        old = dev.status
        if old == status and dev.reason == reason:
            return
        dev.status, dev.reason, dev.since = status, reason, time.time()
        key, now = f"dev:{dev.id}", time.time()
        parent = self.devices.get(dev.parent) if dev.parent else None
        via_parent = parent is not None and parent.status == "lost"
        kids = [d for d in self.devices.values() if d.parent == dev.id]
        if status == "lost":
            if not via_parent:      # у детей шлюза общая причина — одна тревога на шлюз
                text = f"{dev.name}: нет связи"
                if kids:
                    text += ", без данных: " + ", ".join(k.name for k in kids)
                elif reason:
                    text += f" ({reason})"
                self.alarms.raise_(key, "crit", text, now)
            for k in kids:
                self._set_status(k, "lost", f"{dev.name}: нет связи")
        elif status == "stale":
            if not via_parent:
                self.alarms.raise_(key, "warn", f"{dev.name}: нет данных", now)
        elif status == "ok" and old in ("lost", "stale"):
            self.alarms.clear(key, now, f"{dev.name}: {'связь есть' if old == 'lost' else 'данные идут'}")
        self._publish({"type": "device_status", "id": dev.id, "status": status, "reason": reason})

    # ================= диспетчер =================
    def _loop(self):
        next_tick = next_push = time.monotonic()
        while self._alive:
            try:
                item = self._q.get(timeout=0.05)
            except queue.Empty:
                item = None
            if item is not None:
                try:
                    self._handle(item)
                except Exception:
                    traceback.print_exc(file=sys.stderr)
            now = time.monotonic()
            try:
                if now >= next_push:
                    next_push = now + 1 / self.cfg.push_hz
                    self._push()
                if now >= next_tick:
                    next_tick = now + 1.0
                    self._tick()
            except Exception:
                traceback.print_exc(file=sys.stderr)

    def _handle(self, item):
        kind = item[0]
        if kind == "S":
            self._on_sample(*item[1:])
        elif kind == "L":
            dev = self.devices.get(item[1])
            if dev is not None and not dev.closing:
                if item[2]:
                    if dev.status != "ok":
                        self._set_status(dev, "ok")
                else:
                    self._set_status(dev, "lost", item[3])
        elif kind == "C":
            _, fn, args, fut = item
            try:
                fut.set_result(fn(**args))
            except Exception as e:
                fut.set_exception(e)

    def _on_sample(self, dev_id, t, values, depth=0):
        dev = self.devices.get(dev_id)
        if dev is None or dev.closing:
            return
        if dev.status != "ok":
            self._set_status(dev, "ok")
        clean = {}
        for key, v in values.items():
            ch = dev.channels.get(key)
            if ch is None:
                continue                      # канал уже убран
            cid = f"{dev_id}:{key}"
            if ch.kind in ("scalar", "points"):
                v = None if v is None else float(v)
                if v is not None and v == v:
                    self.hist[cid].append(t, v)
                    self._pend[cid].append((t, v))
                    self.alarms.feed(cid, t, v)
            else:
                self._pend_arr[cid] = (t, v, ch)
            self.last[cid] = (t, v)
            clean[key] = v
        if not clean:
            return
        dev.last_t, dev.samples = t, dev.samples + 1
        if self.state in (REC, PAUSE):
            self.storage.write(dev_id, t, clean)
        elif self.state == PREP:
            self.rings[dev_id].put(t, clean, dev.array_keys())
        if depth < 3:
            calcs = {c.id: c for key in clean for c in self._calc_by_input.get(f"{dev_id}:{key}", ())}
            for c in calcs.values():
                out = c.drv.compute(self.last)
                if out:
                    self._on_sample(c.id, t, out, depth + 1)

    def _tick(self):
        now = time.time()
        for dev in self.devices.values():
            if dev.closing or dev.drv.group in ("manual", "calc", "gateway"):
                continue
            r = dev.rate()
            if r <= 0 or dev.status not in ("ok", "wait"):
                continue
            limit = max(3 / r, 2.0) + (WAIT_GRACE_S if dev.status == "wait" else 0)
            ref = dev.last_t or dev.since
            if now - ref > limit:
                self._set_status(dev, "stale", f"нет данных {now - ref:.0f} с")
        if self.state == PREP:
            edge = now - self.cfg.preroll_s
            for h in self.hist.values():
                h.trim_before(edge)
        if self.storage is not None:
            self.storage.flush()
        if self.state != IDLE:
            self._publish({"type": "status", "t": now, "state": self.state,
                           "elapsed": now - self.t0 if self.t0 else None,
                           "devices": {d.id: {"status": d.status, "reason": d.reason,
                                              "age": round(now - d.last_t, 2) if d.last_t else None}
                                       for d in self.devices.values()},
                           "alarms": self.alarms.state(), "last": self._last_scalars()})

    def _push(self):
        if self._pend:
            ch = {cid: _envelope(pts) for cid, pts in self._pend.items()}
            self._pend = defaultdict(list)
            self._publish({"type": "data", "ch": ch})
        if not self._pend_arr:
            return
        if not self._wants_frames():
            self._pend_arr.clear()
            return
        now = time.time()
        for cid, (t, v, ch) in list(self._pend_arr.items()):
            if now - self._frame_sent.get(cid, 0) < 1 / self.cfg.frame_push_fps:
                continue
            self._frame_sent[cid] = now
            del self._pend_arr[cid]
            if ch.kind == "video":
                msg = {"type": "frame", "ch": cid, "t": t, "format": "jpeg",
                       "b64": base64.b64encode(v).decode()}
            else:
                a = np.ascontiguousarray(v, dtype=ch.dtype)
                msg = {"type": "frame", "ch": cid, "t": t, "format": "raw", "dtype": a.dtype.str,
                       "shape": list(a.shape), "b64": base64.b64encode(a.tobytes()).decode()}
            self._publish(msg, frames=True)

    # ================= журнал и метаданные =================
    def _journal(self, kind, text, t=None, by="", **data):
        rec = {"t": round(t if t is not None else time.time(), 3), "kind": kind, "text": text}
        if by:
            rec["by"] = by
        rec.update(data)
        if self.session is not None:
            self.session["events"].append(rec)
        if self.storage is not None:
            self.storage.event(rec)
        self._publish({"type": "event", "event": rec})
        return rec

    def _publish_state(self):
        s = self.session
        self._publish({"type": "state", "state": self.state, "t0": self.t0,
                       "name": s["name"] if s else None, "pauses": s["pauses"] if s else [],
                       "dir": str(self.storage.dir) if self.storage else None, "last_run": self.last_run})

    def _describe(self, cid):
        dev_id, key = cid.split(":", 1)
        dev = self.devices.get(dev_id)
        ch = dev.channels.get(key) if dev else None
        if ch is None:
            return cid, "", 2
        return f"{dev.name} · {ch.name}", ch.unit, ch.dp

    def _last_scalars(self):
        return {cid: v for cid, (t, v) in self.last.items() if not isinstance(v, (bytes, np.ndarray))}

    def _write_meta(self, ended=None):
        s = self.session
        meta = {
            "run": self.storage.dir.name, "name": s["name"], "note": s["note"], "code": code_version(),
            "started_unix": round(self.t0, 3),
            "started_local": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.t0)),
            "preroll_s": round(s["preroll"], 1),
            "devices": {d.id: {"driver": d.drv.type_id, "name": d.name, "parent": d.parent,
                               "settings": dict(d.drv.cfg),
                               "channels": [c.to_dict() for c in d.channels.values()],
                               "files": self.storage.describe(d.id)}
                        for d in self.devices.values()},
            "alarms": s["rules"],
        }
        if ended is not None:
            meta.update({
                "ended_unix": round(ended, 3), "duration_s": round(ended - self.t0, 1),
                "pauses_s": [[round(a - self.t0, 1), round(b - self.t0, 1)] for a, b in s["pauses"]],
                "marks": s["marks"],
                "summary": {d.id: {"samples": d.samples, "status": d.status} for d in self.devices.values()},
            })
        self.storage.write_meta(meta)


def _envelope(pts):
    """Для живых графиков: не больше четырёх точек на канал за такт — края и экстремумы."""
    if len(pts) <= 4:
        return [[round(t, 3), v] for t, v in pts]
    lo = min(pts, key=lambda p: p[1])
    hi = max(pts, key=lambda p: p[1])
    keep = sorted({pts[0], lo, hi, pts[-1]}, key=lambda p: p[0])
    return [[round(t, 3), v] for t, v in keep]


def _safe_name(name):
    """Имя опыта идёт в имя папки: без символов, запрещённых в Windows."""
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", str(name)).strip(" .")
    return s[:80] or "опыт"
