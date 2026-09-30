"""Тепловизор на имитации UVC-потока: режим «картинка», усреднение, профиль, зоны, запись через сборщик."""
import threading
import time
from pathlib import Path

import numpy as np
import pytest

import visserlab.drivers.uvc_thermal as th
from visserlab.core.driver import DriverError
from test_collector import make


def frame(temp=None, picture=False):
    """Буфер кадра 256×384 YUY2: сверху картинка, снизу сырое поле (или картинка, старший байт 128)."""
    buf = np.zeros((2 * th.H, th.W, 2), np.uint8)
    buf[:th.H, :, 1] = 128
    if picture:
        buf[th.H:, :, 0], buf[th.H:, :, 1] = 90, th.PICTURE_HI
    else:
        raw = np.rint((np.broadcast_to(temp, (th.H, th.W)) + 273.15) * 64).astype(np.uint16)
        buf[th.H:, :, 0], buf[th.H:, :, 1] = raw & 0xFF, raw >> 8
    return buf.reshape(1, -1)


class Clock:
    """Время драйвера: кадр каждые 40 мс, как у прибора."""

    def __init__(self):
        self.t = 1000.0

    def monotonic(self):
        return self.t

    def time(self):
        return self.t


class Cap:
    def __init__(self, frames, clock=None, real_fps=None):
        self.frames, self.clock, self.real_fps = list(frames), clock, real_fps

    def read(self):
        if self.clock:
            self.clock.t += 0.04
        if self.real_fps:
            time.sleep(1 / self.real_fps)
        if not self.frames:
            return False, None
        f = self.frames.pop(0)
        return (f is not None), f

    def release(self):
        pass


class Ctx:
    def __init__(self, stop, n):
        self.stop, self.n, self.emits, self.status = stop, n, [], []

    def emit(self, values, t=None, dev=None):
        self.emits.append((t, values))
        if len(self.emits) >= self.n:
            self.stop.set()

    def online(self, ok, reason=""):
        self.status.append((ok, reason))

    def t0(self):
        return None


def driver(n, frames, **cfg):
    stop = threading.Event()
    ctx = Ctx(stop, n)
    d = th.UvcThermal("cam", "", cfg, ctx)
    d.cap = Cap(frames, CLOCK)
    return d, ctx, stop


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    global CLOCK
    CLOCK = Clock()
    monkeypatch.setattr(th, "time", CLOCK)
    return CLOCK


def test_picture_frames_and_uniform_scene():
    assert th.is_picture(th.split_raw(frame(picture=True).tobytes()))
    raw = th.split_raw(frame(25.0).tobytes())                 # ровная сцена: старший байт тоже одинаков
    assert not th.is_picture(raw)
    assert th.to_celsius(raw).mean() == pytest.approx(25.0, abs=0.01)


def test_warmup_is_skipped_and_frames_are_averaged():
    frames = [frame(picture=True)] * 10 + [frame(20.0 + k) for k in range(12)]
    d, ctx, stop = driver(3, frames, fps="5")
    d.run(stop)
    (t0, v0), (t1, v1), (t2, v2) = ctx.emits
    assert th.to_celsius(v0["frame"]).mean() == pytest.approx(20.0, abs=0.01)          # первый — один кадр
    assert th.to_celsius(v1["frame"]).mean() == pytest.approx(23.0, abs=0.01)          # 21…25: пять кадров за 0,2 с
    assert t1 - t0 == pytest.approx(0.12, abs=1e-6)                                  # время — середина интервала
    assert t2 - t1 == pytest.approx(0.2, abs=1e-6)
    assert v1["frame"].dtype == np.dtype("<u2") and v1["frame"].shape == (192, 256)
    assert ctx.status == []


def test_no_average_writes_last_frame():
    frames = [frame(20.0 + k) for k in range(12)]
    d, ctx, stop = driver(2, frames, fps="5", average=False)
    d.run(stop)
    assert th.to_celsius(ctx.emits[1][1]["frame"]).mean() == pytest.approx(25.0, abs=0.01)


def test_picture_mode_is_reported():
    d, ctx, stop = driver(1, [frame(picture=True)] * 250 + [frame(22.0)])
    d.run(stop)
    assert ctx.status and ctx.status[0][0] is False and "USB" in ctx.status[0][1]


def test_lost_frames_raise():
    d, ctx, stop = driver(2, [frame(22.0)] + [None] * 100)
    d.cfg["fps"] = "1"
    with pytest.raises(DriverError, match="нет кадров"):
        d.run(stop)


def test_profile_zones_points():
    T = np.full((th.H, th.W), 20.0, np.float32)
    T[:, 100:108] = np.linspace(30, 50, th.H)[:, None]        # тёплая полоса по вертикали
    T[10:20, 30:40] = 60.0
    raw = (T + 273.15) * 64
    d, _, _ = driver(1, [], profile_at=104, profile_w=8, zones="горячо=30,10,10,10; фон=200,150,20,20")
    d.action("roi_add", {"x": 35, "y": 15})
    v = d.measure(raw)
    assert v["profile"].shape == (192,) and v["profile"][0] == pytest.approx(30.0, abs=0.01)
    assert v["profile"][-1] == pytest.approx(50.0, abs=0.01)
    assert v["z_горячо"] == pytest.approx(60.0, abs=0.01) and v["z_фон"] == pytest.approx(20.0, abs=0.01)
    assert v["roiA"] == pytest.approx(60.0, abs=0.01)
    ch = {c.key: c for c in d.channels()}
    assert ch["profile"].at == ("frame", 100, 0, 8, 192) and ch["z_горячо"].at == ("frame", 30, 10, 10, 10)
    assert ch["roiA"].at == ("frame", 35, 15)
    d.apply({"profile_at": 50})
    assert d.channels()[1].at == ("frame", 46, 0, 8, 192)
    d2, _, _ = driver(1, [], profile="row", profile_at=15, profile_w=4)
    assert d2.measure(raw)["profile"].shape == (256,) and d2.channels()[1].at == ("frame", 0, 13, 256, 4)


def test_zone_errors():
    assert th.parse_zones("") == ()
    with pytest.raises(DriverError, match="имя=x,y,w,h"):
        th.parse_zones("верх=1,2,3")
    with pytest.raises(DriverError, match="вне кадра"):
        th.parse_zones("край=250,0,10,10")
    with pytest.raises(DriverError, match="дважды"):
        th.parse_zones("a=0,0,1,1; a=1,1,1,1")
    with pytest.raises(DriverError):
        th.UvcThermal.validate({"zones": "плохо"})


def test_recorded_through_collector(tmp_path, monkeypatch):
    monkeypatch.setattr(th, "time", time)                    # здесь время настоящее
    frames = [frame(picture=True)] * 5 + [frame(21.0 + 0.01 * k) for k in range(2000)]
    monkeypatch.setattr(th, "open_camera", lambda which: (Cap(frames, real_fps=100), 0))
    coll = make(tmp_path)
    coll.cfg.devices["cam"] = {"driver": "uvc_thermal", "settings": {"fps": "25", "zones": "z=0,0,8,8"}}
    try:
        coll.request("prepare", devices=["cam"])
        coll.request("start")
        time.sleep(1.0)
        coll.request("pause")
        run = coll.request("stop")
    finally:
        coll.close()
    d = Path(run["dir"])
    n = (d / "cam.frame.bin").stat().st_size // (192 * 256 * 2)
    assert n >= 5
    assert (d / "cam.profile.bin").stat().st_size >= n * 192 * 4
    head = (d / "cam.csv").read_text(encoding="utf-8").splitlines()[0]
    assert head == "t_unix,max,mean,z_z"
