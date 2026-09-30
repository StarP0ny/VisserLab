"""Приборы-симуляторы: ядро и интерфейс разрабатываются и тестируются без стенда.

Физика та же, что в макете: от старта записи патрон греется, фронт идёт от
входа к выходу, мешок копит CO₂. Настройка «Скорость времени» ускоряет процесс.
"""
import math
import random
import time

import numpy as np

from ..core.driver import Channel, Driver, Field, Found, Ticker, fmt_num, register

AMB, LEN = 23.0, 180.0      # °C среды; мм корпуса под полосой


def rise(t, d, tau):
    if t is None or t < d:
        return 0.0
    return 1 - math.exp(-(t - d) / tau)


def corpus_t(x, t):
    f = x / LEN
    return AMB + (112 - 26 * f) * rise(t, 40 + 300 * f, 380 + 90 * f)


def corpus_t_vec(x, t):
    if t is None:
        return np.full(x.shape, AMB)
    f = x / LEN
    d, tau = 40 + 300 * f, 380 + 90 * f
    r = np.where(t < d, 0.0, 1 - np.exp(-np.clip(t - d, 0, None) / tau))
    return AMB + (112 - 26 * f) * r


def sht_rh(t):
    return 42.0 if t is None else 91.5 + 4 * math.sin(2 * math.pi * t / 310)


def sht_t(t):
    return AMB if t is None else AMB + (34.8 - AMB) * rise(t, 0, 25) + 0.4 * math.sin(t / 37)


def g(sigma):
    return random.gauss(0, sigma)


SPEED = Field("speed", "Скорость времени", "select", "1", live=True,
              options=[("1", "×1"), ("10", "×10"), ("60", "×60")], hint="Только у симулятора: ускоряет процесс.")


class _Sim(Driver):
    _pt = None

    def clock(self):
        """Время процесса, с: от старта записи, с ускорением; до старта — None."""
        t0, now = self.ctx.t0(), time.time()
        if t0 is None:
            self._pt = None
            return None
        speed = float(self.cfg.get("speed", 1))
        if self._pt is None:
            self._pt = (now - t0) * speed
        else:
            self._pt += (now - self._wall) * speed
        self._wall = now
        return self._pt


@register
class SimPt100(_Sim):
    type_id = "sim_pt100"
    title = "Pt100 ×8 (сим)"
    model = "симулятор PTA8D08"
    icon = "thermo"
    settings = [Field("period", "Период опроса", "select", "1", unit="с", live=True,
                      options=[("0.05", "0,05"), ("0.5", "0,5"), "1", "2"]), SPEED]
    GEN = [
        lambda t, a: corpus_t(10, t),
        lambda t, a: corpus_t(90, t),
        lambda t, a: corpus_t(170, t),
        lambda t, a: corpus_t(90, t) + 1.4 * rise(t, 0, 300),
        lambda t, a: AMB if t is None else AMB + 12.1 * rise(t, 0, 20) + 0.5 * math.sin(2 * math.pi * a / 4),
        lambda t, a: AMB + 58 * rise(t, 20, 300),
        lambda t, a: AMB + 222 * rise(t, 60, 210),
        lambda t, a: AMB + 0.6 * rise(t, 0, 900),
    ]

    def channels(self):
        rate = 1 / float(self.cfg["period"])
        return [Channel(f"T{i}", f"ch{i}", "scalar", "°C", rate, dp=1) for i in range(1, 9)]

    def run(self, stop):
        tick = Ticker(float(self.cfg["period"]))
        while True:
            t, a = self.clock(), time.time()
            self.ctx.emit({f"T{i + 1}": f(t, a) + g(0.06) for i, f in enumerate(self.GEN)}, a)
            if tick.wait(stop, float(self.cfg["period"])):
                return


# ---------- тепловизор: кадр 256×192, корпус с чёрной полосой, гофра слева, мешок справа
W, H = 256, 192
BX0, BX1, BY0, BY1 = 38, 218, 74, 118
SY0, SY1 = 93, 99
_rows = np.arange(H, dtype=float)[:, None]
_cols = np.arange(W, dtype=float)[None, :]
_BG = AMB - 0.8 + 1.4 * _rows / H + np.random.default_rng(7).normal(0, 0.12, (H, W))
_BODY = (_cols >= BX0) & (_cols < BX1) & (_rows >= BY0) & (_rows < BY1)
_STRIPE = _BODY & (_rows >= SY0) & (_rows < SY1)
_GOFRA = (_cols >= 12) & (_cols < BX0) & (_rows >= 86) & (_rows < 106)
_BAG = (_cols >= BX1 + 3) & (_cols < 250) & (_rows >= 60) & (_rows < 132)
_SHADE = 0.86 + 0.14 * np.sin(np.pi * (_rows - BY0 + 0.5) / (BY1 - BY0))
_MM = np.clip((_cols - BX0) / (BX1 - BX0) * LEN, 0, LEN)


def scene(t, eps):
    """Кажущаяся температура кадра, °C. Голый металл (ε≈0,25) тепловизор занижает."""
    k = 0.95 / eps
    T = corpus_t_vec(_MM, t)
    img = np.where(_BODY, AMB + 1 + (T - AMB) * 0.28 * k * _SHADE, _BG)
    img = np.where(_STRIPE, AMB + (T - AMB) * k * _SHADE, img)
    gofra = AMB if t is None else AMB + 12 * rise(t, 0, 30)
    img = np.where(_GOFRA, AMB + (gofra - AMB) * 0.9, img)
    bag = AMB + 16 * rise(t, 120, 500)
    return np.where(_BAG, AMB + (bag - AMB) * 0.9, img)


@register
class SimThermal(_Sim):
    type_id = "sim_thermal"
    title = "Тепловизор (сим)"
    model = "симулятор UVC 256×192"
    icon = "thermal"
    actions = ["roi_add", "roi_del", "roi_clear"]
    settings = [
        Field("fps", "Частота кадров", "select", "5", unit="к/с", options=["1", "5", "9", "25"],
              hint="Сырые кадры 256×192×16 бит: 5 к/с ≈ 1,8 ГБ/ч, 25 к/с ≈ 8,8 ГБ/ч."),
        Field("eps", "Излучательная способность ε", "number", 0.95, min=0.1, max=1, step=0.01, live=True,
              hint="Чёрная матовая полоса ≈ 0,95, голый металл 0,1–0,3."),
        SPEED,
    ]

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.rois = ()          # (имя, столбец, строка); заменяется целиком — поток читает без блокировок

    def channels(self):
        fps = float(self.cfg["fps"])
        ch = [Channel("frame", "кадр", "frame", "°C", fps, shape=(H, W), dtype="<u2", scale=1 / 64, offset=-273.15),
              Channel("profile", "профиль", "profile", "°C", fps, shape=(BX1 - BX0,), dtype="<f4", axis=(0, LEN, "мм")),
              Channel("max", "максимум", "scalar", "°C", fps, dp=1)]
        ch += [Channel(f"roi{n}", f"точка {n}", "scalar", "°C", fps, dp=1, at=("frame", c, r)) for n, c, r in self.rois]
        return ch

    def run(self, stop):
        tick = Ticker(1 / float(self.cfg["fps"]))
        while True:
            img = scene(self.clock(), float(self.cfg["eps"]))
            v = {"frame": np.clip((img + 273.15) * 64, 0, 65535).astype("<u2"),
                 "profile": img[(SY0 + SY1) // 2, BX0:BX1].astype("<f4"),
                 "max": float(img[SY0:SY1, BX0:BX1].max())}
            for n, c, r in self.rois:
                v[f"roi{n}"] = float(img[r, c])
            self.ctx.emit(v)
            if tick.wait(stop):
                return

    def action(self, name, args):
        if name == "roi_add":
            c, r = int(args["x"]), int(args["y"])
            if not (0 <= c < W and 0 <= r < H):
                return super().action(name, args)
            used = {n for n, _, _ in self.rois}
            n = next((ch for ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" if ch not in used), None)
            if n is None:
                return {"text": ""}
            self.rois = self.rois + ((n, c, r),)
            where = f"{fmt_num(float(_MM[0, c]), 0)} мм от входа" if BX0 <= c < BX1 else "вне корпуса"
            return {"kind": "sys", "text": f"{self.name}: точка {n}, {where}", "name": n}
        if name == "roi_del":             # по имени «A» или по ключу канала «roiA»
            n = args.get("name") or str(args.get("key", ""))[3:]
            self.rois = tuple(x for x in self.rois if x[0] != n)
            return {"kind": "sys", "text": f"{self.name}: точка {n} удалена"}
        if name == "roi_clear":
            n, self.rois = len(self.rois), ()
            return {"kind": "sys", "text": f"{self.name}: удалены все точки ({n})"}
        return super().action(name, args)


# ---------- МК-шлюз и приборы за ним
@register
class SimMK(_Sim):
    type_id = "sim_mk"
    title = "МК-шлюз (сим)"
    model = "симулятор МК"
    icon = "chip"
    group = "gateway"
    settings = [Field("link_down", "Имитация обрыва", "toggle", False, live=True), SPEED]

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.kids = []

    @classmethod
    def discover(cls, cfg, children=None):
        return Found(True, children=[c for c, ci in (children or {}).items() if not ci.get("sim_absent")])

    def attach(self, child):
        self.kids.append(child)

    def run(self, stop):
        self.ctx.online(True)
        down = False
        due = {k.id: 0.0 for k in self.kids}
        while not stop.wait(0.005):
            if self.cfg["link_down"]:
                if not down:
                    self.ctx.online(False, "нет ответа по USB")
                    down = True
                continue
            if down:
                self.ctx.online(True)
                down = False
            now = time.time()
            t = self.clock()
            for k in self.kids:
                if now >= due[k.id]:
                    due[k.id] = max(due[k.id] + 1 / k.rate(), now)
                    self.ctx.emit(k.sample(t, now), now, dev=k.id)


class _SimChild(Driver):
    group = "child"

    def rate(self):
        return max(c.rate for c in self.channels())


@register
class SimSCD41(_SimChild):
    type_id = "sim_scd41"
    title = "SCD41 (сим)"
    model = "симулятор Sensirion SCD41"
    icon = "gas"
    settings = [
        Field("mode", "Режим измерения", "select", "p5", options=[("p5", "Периодический, 5 с"), ("lp", "Экономичный, 30 с")]),
        Field("asc", "Автокалибровка ASC", "toggle", False, hint="Тянет базу к 400 ppm. На стенде выключать."),
        Field("range", "Диапазон", "select", "full", live=True,
              options=[("full", "Полный 0–40 000 ppm"), ("spec", "Паспортный 400–5000 ppm")],
              hint="Датчик всегда отдаёт 0–40 000 ppm. «Паспортный» помечает значения выше 5000 ppm."),
        Field("pcomp", "Давление для компенсации", "number", 101.3, unit="кПа", min=70, max=120, step=0.1, live=True),
    ]

    def channels(self):
        r = 0.2 if self.cfg["mode"] == "p5" else 1 / 30
        return [Channel("co2", "CO₂", "scalar", "ppm", r, dp=0),
                Channel("t", "T", "scalar", "°C", r, dp=1),
                Channel("rh", "RH", "scalar", "%", r, dp=1)]

    def sample(self, t, now):
        return {"co2": 430 + 9000 * rise(t, 30, 1200) + g(25),
                "t": AMB + 20 * rise(t, 60, 600) + g(0.1),
                "rh": (45 if t is None else 45 + 52.5 * rise(t, 0, 90)) + g(0.3)}


@register
class SimSHT45(_SimChild):
    type_id = "sim_sht45"
    title = "SHT45 (сим)"
    model = "симулятор Sensirion SHT45"
    icon = "drop"
    settings = [
        Field("rate", "Частота опроса", "select", "1", unit="Гц", options=[("0.5", "0,5"), "1", "2"]),
        Field("heat", "Импульс нагревателя", "select", "off", live=True,
              options=[("off", "Выключен"), ("20", "20 мВт, 1 с"), ("110", "110 мВт, 1 с"), ("200", "200 мВт, 1 с")],
              hint="Снимает дрейф после долгой работы выше 90 % RH."),
        Field("place", "Место (сим)", "select", "room", options=[("inlet", "Вход патрона"), ("room", "Комната")]),
    ]

    def channels(self):
        r = float(self.cfg["rate"])
        return [Channel("rh", "RH", "scalar", "%", r, dp=1), Channel("t", "T", "scalar", "°C", r, dp=2)]

    def sample(self, t, now):
        if self.cfg["place"] == "inlet":
            return {"rh": sht_rh(t) + g(0.25), "t": sht_t(t) + g(0.03)}
        return {"rh": 48 + g(0.3), "t": 24 + g(0.03)}


@register
class SimSDP810(_SimChild):
    type_id = "sim_sdp810"
    title = "SDP810 (сим)"
    model = "симулятор Sensirion SDP810-500Pa"
    icon = "gauge"
    settings = [
        Field("rate", "Частота", "select", "25", unit="Гц", options=["10", "25", "50"]),
        Field("zero", "Ноль", "action", hint="Снимать без потока."),
    ]

    def channels(self):
        return [Channel("dp", "ΔP", "scalar", "Па", float(self.cfg["rate"]), dp=1)]

    def sample(self, t, now):
        if t is None:
            return {"dp": g(0.8)}
        return {"dp": (110 + 180 * min(1, t / 1800)) * math.sin(2 * math.pi * now / 4) + g(6)}

    def action(self, name, args):
        if name == "zero":
            return {"kind": "set", "text": f"{self.name}: ноль снят ({fmt_num(g(0.4), 1)} Па)"}
        return super().action(name, args)
