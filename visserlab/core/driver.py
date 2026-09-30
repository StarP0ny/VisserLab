"""Контракт драйвера прибора.

Драйвер сам описывает себя (настройки, каналы) и читает железо в своём потоке.
Ядро ничего не знает про конкретные приборы: всё, что ему нужно, объявлено
здесь. Форма настроек в интерфейсе строится из `Driver.settings`.

Что ядро даёт драйверу (`ctx`):
  ctx.emit(values, t=None, dev=None)  отсчёт: {ключ канала: значение}; t — time.time()
                                      в момент получения; dev — прибор-ребёнок шлюза
  ctx.online(ok, reason="")           явный статус связи (данные сами означают «на связи»)
  ctx.t0()                            время старта записи или None
"""
from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass, field

KINDS = ("scalar", "points", "frame", "profile", "video")
ARRAY_KINDS = ("frame", "profile", "video")


class DriverError(Exception):
    """Ошибка с текстом, который можно показать человеку как есть."""


def fmt_num(x, dp=None):
    s = f"{x:.{dp}f}" if dp is not None else f"{x:g}"
    return s.replace(".", ",").replace("-", "−")


@dataclass
class Field:
    key: str
    label: str
    type: str = "text"            # text | number | select | toggle | port | action | info
    default: object = None
    unit: str = ""
    live: bool = False            # можно менять во время записи
    hint: str = ""
    options: list = field(default_factory=list)   # [(значение, подпись)] или [значение]
    min: float | None = None
    max: float | None = None
    step: float | None = None

    def __post_init__(self):
        self.options = [tuple(o) if isinstance(o, (list, tuple)) else (o, o) for o in self.options]

    @property
    def stored(self):
        return self.type not in ("action", "info")

    def coerce(self, v):
        if self.type == "number":
            try:
                x = float(str(v).replace(",", "."))
            except ValueError:
                raise DriverError(f"{self.label}: нужно число") from None
            if (self.min is not None and x < self.min) or (self.max is not None and x > self.max):
                raise DriverError(f"{self.label}: допустимо {fmt_num(self.min)}…{fmt_num(self.max)}")
            return int(x) if isinstance(self.default, int) and x.is_integer() else x
        if self.type == "toggle":
            if isinstance(v, str):
                return v.strip().lower() in ("1", "true", "yes", "on", "да", "вкл")
            return bool(v)
        if self.type == "select":
            for val, _ in self.options:
                if str(val) == str(v):
                    return val
            raise DriverError(f"{self.label}: нет варианта «{v}»")
        return str(v)

    def show(self, v):
        """Значение для журнала: «Период опроса 1 с → 2 с»."""
        if self.type == "toggle":
            return "вкл" if v else "выкл"
        if self.type == "select":
            v = next((lbl for val, lbl in self.options if str(val) == str(v)), v)
        elif isinstance(v, float):
            v = fmt_num(v)
        return f"{v} {self.unit}" if self.unit else str(v)

    def to_dict(self):
        d = asdict(self)
        d["options"] = [list(o) for o in self.options]
        return d


@dataclass
class Channel:
    key: str
    name: str
    kind: str = "scalar"          # см. KINDS
    unit: str = ""
    rate: float = 0.0             # ожидаемая частота, Гц; 0 — по событию
    dp: int = 2                   # знаков после запятой в интерфейсе
    shape: tuple = ()             # frame/profile
    dtype: str = ""               # frame/profile: '<u2', '<f4'
    hidden: bool = False          # в интерфейсе свёрнут по умолчанию
    scale: float = 1.0            # физическая величина = сырое · scale + offset (в файлах — сырое)
    offset: float = 0.0
    at: tuple = ()                # на кадре другого канала: точка (ключ кадра, x, y) или прямоугольник (…, x, y, w, h)
    axis: tuple = ()              # ось профиля: (от, до, единица)

    def to_dict(self):
        d = asdict(self)
        for k in ("shape", "at", "axis"):
            d[k] = list(getattr(self, k))
        return d

    def signature(self):
        return (self.key, self.kind, tuple(self.shape), self.dtype)


@dataclass
class Found:
    ok: bool
    note: str = ""
    children: list = field(default_factory=list)   # шлюз: id детей, которые ответили


class Ticker:
    """Расписание от первого тика, а не sleep(period): шаг не плывёт на время опроса."""

    def __init__(self, period):
        self.period = period
        self.next = time.monotonic()

    def wait(self, stop: threading.Event, period=None):
        """Ждёт следующего тика. True — пора выходить."""
        if period:
            self.period = period
        self.next += self.period
        delay = self.next - time.monotonic()
        if delay < 0:
            self.next, delay = time.monotonic(), 0
        return stop.wait(delay)


REGISTRY: dict[str, type["Driver"]] = {}


def register(cls):
    REGISTRY[cls.type_id] = cls
    return cls


class Driver:
    """Базовый прибор.

    group:
      direct   свой поток и своё подключение;
      gateway  свой поток, данные идут от имени детей: ctx.emit(..., dev=child.id);
      child    без потока, данные даёт шлюз (sample/rate — по договорённости со шлюзом);
      manual   без потока, отсчёт приходит действием «add»;
      calc     без потока, считает по входным каналам: inputs() и compute().
    """
    type_id = ""
    title = ""
    model = ""
    icon = "device"
    group = "direct"
    settings: list[Field] = []
    actions: list[str] = []       # действия прибора, которые интерфейс может предложить (кроме reconnect)
    scan_what = ""                # что перебирает поиск, для подсказки; пусто — перебора нет

    def __init__(self, dev_id, name, cfg, ctx):
        self.id, self.name, self.ctx = dev_id, name or self.title, ctx
        self.cfg = self.defaults()
        self.cfg.update(self.validate(cfg or {}))

    # --- описание
    @classmethod
    def defaults(cls):
        return {f.key: f.default for f in cls.settings if f.stored}

    @classmethod
    def field(cls, key):
        return next((f for f in cls.settings if f.key == key and f.stored), None)

    @classmethod
    def validate(cls, changes):
        out = {}
        for k, v in changes.items():
            f = cls.field(k)
            if f is None:
                raise DriverError(f"{cls.title}: нет настройки «{k}»")
            out[k] = f.coerce(v)
        return out

    @classmethod
    def describe(cls):
        return {"driver": cls.type_id, "title": cls.title, "model": cls.model, "icon": cls.icon,
                "group": cls.group, "settings": [f.to_dict() for f in cls.settings], "actions": list(cls.actions),
                "scan": cls.scan_what}

    @classmethod
    def discover(cls, cfg, children=None) -> Found:
        """Одна проверка на заданных параметрах. Шлюз отвечает ещё и за детей."""
        return Found(True)

    @classmethod
    def scan(cls, cfg, report, stop, taken=()) -> dict | None:
        """Перебор параметров подключения, начиная с cfg (порт в нём уже выбран).

        report(frac, text) — доля 0…1 и что пробуем сейчас; stop — threading.Event отмены;
        taken — настройки других приборов стенда: двое на одной шине не должны найти
        одно и то же. Возвращает настройки, на которых прибор ответил, или None.
        """
        return None

    # --- работа
    def channels(self) -> list[Channel]:
        return []

    def open(self):
        pass

    def run(self, stop: threading.Event):
        stop.wait()

    def close(self):
        pass

    def apply(self, changes):
        """Изменения полей с live=True, во время работы."""
        self.cfg.update(changes)

    def action(self, name, args) -> dict | None:
        """Действие прибора. Может вернуть {'text': ..., 'kind': ...} для журнала."""
        raise DriverError(f"{self.name}: нет действия «{name}»")

    # --- шлюз
    def attach(self, child: "Driver"):
        raise DriverError(f"{self.name}: не шлюз")

    # --- вычисляемый
    def inputs(self) -> list[str]:
        return []

    def compute(self, last: dict) -> dict | None:
        return None
