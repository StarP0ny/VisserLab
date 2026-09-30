"""Тепловизор на UVC-модуле 256×192: VICTOR 328B (так же устроены InfiRay P2, Topdon TC001).

Проверено на этом экземпляре (Visser, ветка thermo, lab/README.md; и 2026-09-30):
  USB VID_0BDA PID_5840, «USB Camera», драйверов не нужно; открывается только через MSMF.
  Поток YUY2 256×384 @ 25 к/с идёт сам, размер задавать не нужно.
  Строки 0…191 — картинка с автоусилением (не количественная), 192…383 — сырое поле
  uint16 LE: T[°C] = raw/64 − 273,15, шаг 0,016 K.
  Первые ~3,5 с после открытия и в нижней половине картинка: старший байт каждого
  пикселя = 128 (≈ 239 °C по всему полю). Такие кадры выбрасываются.
  Управляющих команд у прибора нет, а опрос UVC-свойств (contrast, gamma…) переводит его
  в режим картинки до передёргивания USB. Поэтому из кода — только CONVERT_RGB: это флаг
  OpenCV, прибору он не уходит.
  ε = 0,95 зашита в приборе. Пишется сырое поле, поправка на ε — при анализе.

Прибор шлёт 25 к/с. Записанный кадр — среднее всех кадров за интервал записи: при 1 к/с
шум ниже примерно впятеро. Если внутри интервала щёлкнул затвор (NUC), кадр смешанный.
"""
import re
import time

import numpy as np

from ..core.driver import Channel, Driver, DriverError, Field, Found, fmt_num, register

W, H = 256, 192
FRAME_BYTES = W * H * 2 * 2          # две половины по 256×192 пикселя, 2 байта на пиксель
RAW_SCALE, RAW_OFFSET = 1 / 64, -273.15
PICTURE_HI = 128                     # старший байт в режиме картинки
WARMUP_S = 8.0                       # дольше этого без температур — прибор в режиме картинки
NO_FRAMES_S = 2.0                    # дольше этого без кадров — связи нет
FRAME_S = 1 / 25                     # прибор шлёт 25 к/с
ROI_R = 1                            # точка замера — среднее квадрата 3×3
ZONE_RE = re.compile(r"^\s*([\w-]+)\s*=\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*$")


def to_celsius(raw):
    return np.asarray(raw, dtype=np.float32) * RAW_SCALE + RAW_OFFSET


def split_raw(buf):
    """Плоский буфер кадра → сырое поле (192, 256) uint16 из нижней половины."""
    b = np.frombuffer(buf, dtype=np.uint8).reshape(2 * H, W, 2)[H:]
    return b[..., 0].astype(np.uint16) | (b[..., 1].astype(np.uint16) << 8)


def is_picture(raw):
    """Кадр без температур: в режиме картинки старший байт всех пикселей = 128.
    Проверять именно 128: у ровной сцены в пределах 4 K старший байт тоже одинаков."""
    return bool(np.all((raw >> 8) == PICTURE_HI))


def parse_zones(text):
    """«верх=120,30,24,18; бок=120,90,24,18» → [(имя, x, y, w, h)] в пикселях кадра 256×192."""
    out = []
    for part in re.split(r"[;\n]", text or ""):
        if not part.strip():
            continue
        m = ZONE_RE.match(part)
        if not m:
            raise DriverError(f"Зона «{part.strip()}»: нужно имя=x,y,w,h")
        name, x, y, w, h = m.group(1), *map(int, m.groups()[1:])
        if not (w > 0 and h > 0 and x + w <= W and y + h <= H):
            raise DriverError(f"Зона «{name}» вне кадра {W}×{H}")
        if any(z[0] == name for z in out):
            raise DriverError(f"Зона «{name}» задана дважды")
        out.append((name, x, y, w, h))
    return tuple(out)


def open_camera(which):
    """(cap, индекс) первой камеры с кадром 256×384. which — «auto» или номер камеры в Windows."""
    import cv2
    try:
        cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)
    except AttributeError:
        pass
    for i in (range(6) if which == "auto" else [int(which)]):
        cap = cv2.VideoCapture(i, cv2.CAP_MSMF)
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_CONVERT_RGB, 0.0)   # иначе OpenCV отдаст BGR и съест температуры
            ok, f = cap.read()
            if ok and f is not None and f.size == FRAME_BYTES:
                return cap, i
        cap.release()
    where = "ни на одной камере" if which == "auto" else f"на камере {which}"
    raise DriverError(f"Нет кадра 256×384 {where}: кабель? камера занята другой программой?")


@register
class UvcThermal(Driver):
    type_id = "uvc_thermal"
    title = "Тепловизор"
    model = "VICTOR 328B · UVC 256×192"
    icon = "thermal"
    actions = ["roi_add", "roi_del", "roi_clear"]
    settings = [
        Field("camera", "Камера", "select", "auto", options=[("auto", "авто"), "0", "1", "2", "3", "4", "5"],
              hint="Номер камеры в Windows. «Авто» — первая с кадром 256×384."),
        Field("fps", "Запись", "select", "5", unit="к/с", options=["1", "5", "25"],
              hint="Кадр 96 КБ: 1 к/с ≈ 350 МБ/ч, 5 к/с ≈ 1,8 ГБ/ч, 25 к/с ≈ 8,8 ГБ/ч."),
        Field("average", "Усреднять кадры", "toggle", True, live=True,
              hint="Прибор шлёт 25 к/с; записанный кадр — среднее за интервал, шум ниже."),
        Field("profile", "Профиль", "select", "col", options=[("col", "по столбцу"), ("row", "по строке")],
              hint="Столбец — T по высоте кадра, для вертикально стоящего патрона это T(z)."),
        Field("profile_at", "Профиль: где", "number", 128, unit="пкс", live=True, min=0, max=W - 1, step=1,
              hint="Номер столбца (0–255) или строки (0–191)."),
        Field("profile_w", "Профиль: ширина полосы", "number", 8, unit="пкс", live=True, min=1, max=64, step=1,
              hint="Температура усредняется поперёк полосы."),
        Field("zones", "Зоны", "text", "", live=True,
              hint="имя=x,y,w,h через «;», например верх=120,30,24,18. Каждая зона — канал: среднее по прямоугольнику."),
        Field("eps", "Излучательная способность", "info",
              hint="ε = 0,95 зашита в приборе, с ПК не меняется. Пишется сырое поле, поправка — при анализе."),
    ]

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.rois = ()                  # (имя, x, y); кортежи заменяются целиком — поток читает без блокировок
        self.zones = parse_zones(self.cfg["zones"])
        self.cap = None

    @classmethod
    def validate(cls, changes):
        out = super().validate(changes)
        if "zones" in out:
            parse_zones(out["zones"])
        return out

    @classmethod
    def discover(cls, cfg, children=None):
        cap, i = open_camera(cfg["camera"])
        try:
            end = time.monotonic() + WARMUP_S
            while time.monotonic() < end:
                ok, f = cap.read()
                if ok and f is not None and f.size == FRAME_BYTES and not is_picture(split_raw(f)):
                    return Found(True, f"камера {i}")
            return Found(False, "режим «картинка»: передёрните USB")
        finally:
            cap.release()

    # ---------- каналы
    def _profile_len(self):
        return H if self.cfg["profile"] == "col" else W

    def _band(self):
        """Полоса профиля на кадре: (начало, ширина) по оси поперёк профиля."""
        at, w = int(self.cfg["profile_at"]), int(self.cfg["profile_w"])
        n = W if self.cfg["profile"] == "col" else H
        a = min(max(at - w // 2, 0), n - 1)
        return a, min(w, n - a)

    def channels(self):
        fps, n = float(self.cfg["fps"]), self._profile_len()
        a, w = self._band()
        band = ("frame", a, 0, w, H) if self.cfg["profile"] == "col" else ("frame", 0, a, W, w)
        ch = [Channel("frame", "кадр", "frame", "°C", fps, shape=(H, W), dtype="<u2",
                      scale=RAW_SCALE, offset=RAW_OFFSET),
              Channel("profile", "профиль", "profile", "°C", fps, shape=(n,), dtype="<f4", axis=(0, n, "пкс"),
                      at=band),
              Channel("max", "максимум", "scalar", "°C", fps, dp=1),
              Channel("mean", "среднее по кадру", "scalar", "°C", fps, dp=2, hidden=True)]
        ch += [Channel(f"z_{n_}", f"зона {n_}", "scalar", "°C", fps, dp=2, at=("frame", x, y, zw, zh))
               for n_, x, y, zw, zh in self.zones]
        ch += [Channel(f"roi{n_}", f"точка {n_}", "scalar", "°C", fps, dp=1, at=("frame", x, y)) for n_, x, y in self.rois]
        return ch

    def apply(self, changes):
        if "zones" in changes:
            self.zones = parse_zones(changes["zones"])
        super().apply(changes)

    # ---------- поток
    def open(self):
        self.cap, _ = open_camera(self.cfg["camera"])

    def close(self):
        if self.cap is not None:
            self.cap.release()
            self.cap = None

    def run(self, stop):
        acc, ts = None, []
        last_frame = picture_since = time.monotonic()
        told, due = False, None
        while not stop.is_set():
            ok, f = self.cap.read()
            now = time.monotonic()
            if not ok or f is None or f.size != FRAME_BYTES:
                if now - last_frame > NO_FRAMES_S:
                    raise DriverError("нет кадров: кабель?")
                continue
            last_frame, t = now, time.time()
            raw = split_raw(f)
            if is_picture(raw):
                if not told and now - picture_since > WARMUP_S:
                    self.ctx.online(False, "режим «картинка»: передёрните USB")
                    told = True
                continue
            picture_since, told = now, False
            if self.cfg["average"]:
                acc = raw.astype(np.float64) if acc is None else acc + raw
                ts.append(t)
            else:
                acc, ts = raw.astype(np.float64), [t]
            if due is None:                          # интервал считается от первого кадра с температурой
                due = now
            if now < due - FRAME_S / 2:              # полкадра допуска: в интервал стабильно попадает fps/25 кадров
                continue
            period = 1 / float(self.cfg["fps"])
            due = max(due + period, now)             # подвисли — долг не копим
            self.ctx.emit(self.measure(acc / len(ts)), sum(ts) / len(ts))
            acc, ts = None, []

    def measure(self, raw):
        """Среднее сырое поле → отсчёт: кадр, профиль, максимум, зоны, точки."""
        T = to_celsius(raw)
        a, w = self._band()
        prof = T[:, a:a + w].mean(axis=1) if self.cfg["profile"] == "col" else T[a:a + w, :].mean(axis=0)
        v = {"frame": np.rint(raw).astype("<u2"), "profile": prof.astype("<f4"),
             "max": float(T.max()), "mean": float(T.mean())}
        for name, x, y, zw, zh in self.zones:
            v[f"z_{name}"] = float(T[y:y + zh, x:x + zw].mean())
        for n, x, y in self.rois:
            v[f"roi{n}"] = float(T[max(y - ROI_R, 0):y + ROI_R + 1, max(x - ROI_R, 0):x + ROI_R + 1].mean())
        return v

    # ---------- точки замера с экрана
    def action(self, name, args):
        if name == "roi_add":
            x, y = int(args["x"]), int(args["y"])
            if not (0 <= x < W and 0 <= y < H):
                raise DriverError(f"{self.name}: точка вне кадра")
            used = {n for n, _, _ in self.rois}
            n = next((c for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" if c not in used), None)
            if n is None:
                raise DriverError(f"{self.name}: точек больше 26")
            self.rois = self.rois + ((n, x, y),)
            return {"kind": "sys", "text": f"{self.name}: точка {n} ({x}, {y})", "name": n}
        if name == "roi_del":                # по имени «A» или по ключу канала «roiA»
            n = args.get("name") or str(args.get("key", ""))[3:]
            self.rois = tuple(r for r in self.rois if r[0] != n)
            return {"kind": "sys", "text": f"{self.name}: точка {n} удалена"}
        if name == "roi_clear":
            n, self.rois = len(self.rois), ()
            return {"kind": "sys", "text": f"{self.name}: удалены все точки ({fmt_num(n)})"}
        return super().action(name, args)
