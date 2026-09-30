"""Ядро сборщика на симуляторах: состояния, запись, предзапись, настройки, шлюз, оповещения, сеть."""
import asyncio
import csv
import json
import math
import socket
import threading
import time
from pathlib import Path

import pytest
import yaml

import visserlab.core.collector as collector_mod
from visserlab.config import Config, load
from visserlab.core.buffers import History, Ring
from visserlab.core.collector import Collector, CollectorError
from visserlab.core.driver import Channel, Driver, register
from visserlab.core.server import serve
from visserlab.drivers.calc import abs_humidity

FAST = {"sim_pt100": {"period": "0.05"}, "sim_thermal": {"fps": "25"}, "sim_sdp": {"rate": "50"}}


@register
class Silent(Driver):
    """Прибор, который открылся и молчит."""
    type_id = "test_silent"
    title = "Молчун"

    def channels(self):
        return [Channel("x", "x", "scalar", "", 20)]


STAND = Path(__file__).with_name("stand")         # симуляторы: tests/stand/sims.py


def make(tmp_path, **kw):
    base = load(STAND, local_on=False)
    devices = dict(base.devices, silent={"driver": "test_silent"})
    cfg = Config(devices=devices, templates=base.templates, runs_dir=tmp_path / "runs",
                 preroll_s=2, preroll_fps=5, push_hz=20, frame_push_fps=10,
                 local_path=tmp_path / "local.yaml", **kw)
    return Collector(cfg).launch()


def wait_for(pred, timeout=5.0, step=0.05):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(step)
    return False


def events(d):
    return [json.loads(line) for line in (d / "events.jsonl").read_text(encoding="utf-8").splitlines()]


def test_lifecycle_and_files(tmp_path):
    coll = make(tmp_path)
    try:
        coll.request("prepare", name="t/1", devices=["sim_pt100", "sim_thermal", "syringe"], settings=FAST, by="тест")
        time.sleep(0.6)                                   # набираем предзапись
        coll.request("start", by="тест")
        time.sleep(0.4)
        coll.request("note", text="заметка", t=time.time() - 0.2)
        coll.request("action", device="syringe", name="add", args={"value": "0,56"})
        with pytest.raises(CollectorError, match="только из паузы"):
            coll.request("stop")
        coll.request("pause")
        time.sleep(0.2)
        run = coll.request("stop")
    finally:
        coll.close()
    d = Path(run["dir"])
    assert d.name.endswith("_t_1")                        # «/» не попал в имя папки
    meta = yaml.safe_load((d / "meta.yaml").read_text(encoding="utf-8"))
    assert meta["duration_s"] > 0.5 and meta["preroll_s"] > 0.4
    assert meta["devices"]["sim_pt100"]["channels"][0]["name"] == "ch1 корпус, вход"
    assert len(meta["pauses_s"]) == 1

    rows = list(csv.reader((d / "sim_pt100.csv").open(encoding="utf-8")))
    assert rows[0][:3] == ["t_unix", "T1", "T2"]
    ts = [float(r[0]) for r in rows[1:]]
    assert ts[0] < meta["started_unix"] < ts[-1]          # предзапись до старта, запись после
    assert ts == sorted(ts)

    n = len((d / "sim_thermal.frame.index.csv").read_text().splitlines()) - 1
    assert n >= 5
    assert (d / "sim_thermal.frame.bin").stat().st_size == n * 192 * 256 * 2
    frames_pre = [float(line.split(",")[0]) for line in (d / "sim_thermal.frame.index.csv").read_text().splitlines()[1:]]
    assert frames_pre[0] < meta["started_unix"]            # кадры в предзаписи тоже есть

    syr = list(csv.reader((d / "syringe.csv").open(encoding="utf-8")))
    assert syr[1][1] == "0.56"

    ev = events(d)
    kinds = [(e["kind"], e["text"]) for e in ev]
    assert kinds[0][1].startswith("Подготовка")
    assert ("user", "заметка") in kinds
    assert any(k == "manual" and "0,56 %" in t for k, t in kinds)
    texts = [t for _, t in kinds]
    assert texts.index("Пауза") < next(i for i, t in enumerate(texts) if t.startswith("Стоп"))
    note = next(e for e in ev if e["text"] == "заметка")
    start = next(e for e in ev if e["text"].startswith("Старт записи"))
    assert note["t"] > start["t"] and note.get("by") is None


def test_cancel_leaves_nothing(tmp_path):
    coll = make(tmp_path)
    try:
        coll.request("prepare", devices=["sim_pt100"], settings=FAST)
        time.sleep(0.3)
        coll.request("cancel")
        assert coll.state == "idle"
    finally:
        coll.close()
    assert not (tmp_path / "runs").exists()


def test_state_errors(tmp_path):
    coll = make(tmp_path)
    try:
        with pytest.raises(CollectorError, match="Нет прибора"):
            coll.request("prepare", devices=["нет_такого"])
        with pytest.raises(CollectorError, match="недоступна"):
            coll.request("note", text="x")
        coll.request("prepare", devices=["sim_pt100"], settings=FAST)
        with pytest.raises(CollectorError, match="недоступна"):
            coll.request("prepare", devices=["sim_pt100"])
        with pytest.raises(CollectorError, match="Нет команды"):
            coll.request("взлететь")
    finally:
        coll.close()


def test_settings_live_and_fixed(tmp_path):
    coll = make(tmp_path)
    try:
        coll.request("prepare", devices=["sim_pt100", "sim_thermal"], settings=FAST)
        coll.request("start")
        res = coll.request("set", device="sim_pt100", changes={"period": "0.5"})
        assert res["changed"]["period"] == ["0.05", "0.5"]
        with pytest.raises(CollectorError, match="меняется на паузе"):
            coll.request("set", device="sim_thermal", changes={"fps": "5"})
        coll.request("pause")
        before = coll.devices["sim_thermal"].samples
        coll.request("set", device="sim_thermal", changes={"fps": "9"})   # прибор переоткроется
        assert wait_for(lambda: coll.devices["sim_thermal"].samples > before + 3)
        texts = [e["text"] for e in coll.session["events"] if e["kind"] == "set"]
        assert "Pt100 ×8 (сим): период опроса 0,05 с → 0,5 с" in texts
        assert any("частота кадров 25 к/с → 9 к/с" in t for t in texts)
        coll.request("stop")
    finally:
        coll.close()


def test_roi_adds_channel_and_segment(tmp_path):
    coll = make(tmp_path)
    try:
        coll.request("prepare", devices=["sim_thermal"], settings=FAST)
        coll.request("start")
        time.sleep(0.2)
        res = coll.request("action", device="sim_thermal", name="roi_add", args={"x": 100, "y": 96})
        assert res["name"] == "A"
        assert wait_for(lambda: "sim_thermal:roiA" in coll.last)
        coll.request("pause")
        run = coll.request("stop")
    finally:
        coll.close()
    d = Path(run["dir"])
    assert (d / "sim_thermal.csv").read_text().splitlines()[0] == "t_unix,max"
    assert (d / "sim_thermal.2.csv").read_text().splitlines()[0] == "t_unix,max,roiA"
    meta = yaml.safe_load((d / "meta.yaml").read_text(encoding="utf-8"))
    files = [f["file"] for f in meta["devices"]["sim_thermal"]["files"]]
    assert "sim_thermal.csv" in files and "sim_thermal.2.csv" in files


def test_gateway_loss_is_one_alarm(tmp_path):
    coll = make(tmp_path)
    try:
        coll.request("prepare", devices=["sim_scd41", "sim_sht1", "sim_sdp"], settings=FAST)
        assert "sim_mk" in coll.devices                    # шлюз поднялся сам
        assert wait_for(lambda: all(coll.devices[i].status == "ok" for i in ("sim_mk", "sim_sht1", "sim_sdp")))
        coll.request("set", device="sim_mk", changes={"link_down": True})
        assert wait_for(lambda: coll.devices["sim_sdp"].status == "lost")
        st = coll.alarms.state()
        assert st["level"] == "crit" and len(st["items"]) == 1
        assert "без данных" in st["items"][0]["text"] and "SDP810" in st["items"][0]["text"]
        assert coll.devices["sim_sdp"].reason == "МК-1 (сим): нет связи"
        coll.request("set", device="sim_mk", changes={"link_down": False})
        assert wait_for(lambda: coll.alarms.state()["level"] == "ok")
        assert wait_for(lambda: coll.devices["sim_sdp"].status == "ok")
    finally:
        coll.close()


def test_alarm_rule_with_hold(tmp_path):
    coll = make(tmp_path)
    try:
        rule = {"channel": "sim_sht1:rh", "op": ">", "value": 40, "hold": 0.4, "level": "warn"}
        coll.request("prepare", devices=["sim_sht1"], alarms=[rule])
        assert wait_for(lambda: coll.alarms.state()["level"] == "warn", timeout=4)
        item = coll.alarms.state()["items"][0]
        assert item["text"].startswith("SHT45 #1 (сим) · RH:") and "> 40 %" in item["text"]
        assert any(e["kind"] == "warn" for e in coll.session["events"])
    finally:
        coll.close()


def test_silent_device_goes_stale(tmp_path, monkeypatch):
    monkeypatch.setattr(collector_mod, "WAIT_GRACE_S", 0)
    coll = make(tmp_path)
    try:
        coll.request("prepare", devices=["silent"])
        assert wait_for(lambda: coll.devices["silent"].status == "stale", timeout=5)
        assert coll.alarms.state()["level"] == "warn"
    finally:
        coll.close()


def test_calc_device(tmp_path):
    coll = make(tmp_path)
    try:
        coll.request("prepare", devices=["sim_sht1", "sim_ah"])
        assert wait_for(lambda: "sim_ah:rho" in coll.last, timeout=4)
        rh, t = coll.last["sim_sht1:rh"][1], coll.last["sim_sht1:t"][1]
        assert coll.last["sim_ah:rho"][1] == pytest.approx(abs_humidity(rh, t), rel=0.05)
        with pytest.raises(CollectorError):
            coll.request("cancel") or coll.request("prepare", devices=["sim_ah"])   # без SHT считать не из чего
    finally:
        coll.close()


def test_history_keeps_extremes():
    h = History()
    for i in range(20000):
        h.append(i * 0.01, math.sin(i * 0.05) + (5 if i == 12345 else 0))
    t, v = h.query(points=200)
    assert len(t) <= 200 and t == sorted(t)
    assert max(v) == pytest.approx(5 + math.sin(12345 * 0.05))
    assert min(v) == pytest.approx(-1, abs=1e-3)


def test_ring_thins_frames_only():
    r = Ring(horizon=10, array_fps=1)
    for i in range(30):
        r.put(i * 0.1, {"x": i, "frame": b"."}, {"frame"})
    items = r.drain()
    assert len(items) == 30
    assert sum("frame" in v for _, v in items) == 3


def test_server_roundtrip(tmp_path):
    coll = make(tmp_path)
    port_box = {}
    ready = threading.Event()

    def on_ready(p):
        port_box["p"] = p
        ready.set()

    threading.Thread(target=lambda: asyncio.run(serve(coll, port=0, ready=on_ready)), daemon=True).start()
    assert ready.wait(5)
    s = socket.create_connection(("127.0.0.1", port_box["p"]), timeout=5)
    buf = b""

    def send(i, cmd, **args):
        s.sendall((json.dumps({"id": i, "cmd": cmd, "args": args}) + "\n").encode())

    def read_until(pred, timeout=5):
        nonlocal buf
        seen, end = [], time.time() + timeout
        while time.time() < end:
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                m = json.loads(line)
                seen.append(m)
                if pred(m):
                    return m, seen
            buf += s.recv(1 << 20)
        raise AssertionError(f"не дождались, видели: {[m.get('type') for m in seen][-20:]}")

    try:
        send(1, "hello", frames=True)
        m, _ = read_until(lambda m: m.get("id") == 1)
        assert m["ok"] and m["result"]["state"] == "idle"
        assert any(d["id"] == "sim_mk" and d["group"] == "gateway" for d in m["result"]["inventory"])
        send(2, "prepare", devices=["sim_pt100", "sim_thermal"], settings=FAST)
        read_until(lambda m: m.get("id") == 2 and m["ok"])
        m, _ = read_until(lambda m: m.get("type") == "data" and "sim_pt100:T1" in m["ch"])
        assert len(m["ch"]["sim_pt100:T1"]) <= 4
        m, _ = read_until(lambda m: m.get("type") == "frame" and m["ch"] == "sim_thermal:frame")
        assert m["shape"] == [192, 256] and m["dtype"] == "<u2"
        read_until(lambda m: m.get("type") == "status")
        send(3, "stop")
        m, _ = read_until(lambda m: m.get("id") == 3)
        assert not m["ok"] and "недоступна" in m["error"]
        send(4, "history", channel="sim_pt100:T1", points=50)
        m, _ = read_until(lambda m: m.get("id") == 4)
        assert m["ok"] and 0 < len(m["result"]["t"]) <= 50
    finally:
        s.close()
        coll.close()
