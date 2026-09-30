"""PTA8D08 (eletechsup): 8 каналов Pt100, Modbus RTU по RS485.

Карта регистров снята дампом 2026-09-29 и 2026-09-30:
  0..7    температура, °C ×10, знаковое
  32..39  сопротивление, Ом ×10
  0xFD    свой адрес платы, 0xFE — код скорости (3 = 9600), 0xFF — чётность; дальше exception 2
На адрес 255 плата отвечает при любом своём адресе, поэтому перебор скоростей
занимает секунду. Полный перебор адресов нужен, только если на шине несколько плат:
тогда ответы на 255 сталкиваются.

Линеаризация платы совпадает с IEC 60751 (111,6 Ом ↔ 29,8 °C), поэтому R пишется
рядом с T: по омам калибровку можно пересчитать задним числом.

Пустой вход читается как ~137,6 Ом / ~97,7 °C, и по значению его не отличить от
горячего корпуса. Какие входы подключены, видно по подписям каналов в конфиге;
пишутся все восемь.
"""
import time

from ..core.driver import Channel, Driver, DriverError, Field, Found, Ticker, register
from ..modbus import RtuClient, reply_timeout, s16

T_BASE, R_BASE, NCH = 0, 32, 8
REG_ADDR = 0xFD
ANY_ADDR = 255
LOST_AFTER = 3          # подряд пустых опросов до «нет связи»
BAUDS = ["1200", "2400", "4800", "9600", "19200", "38400", "57600", "115200"]
LIKELY = ["9600", "19200", "4800", "38400", "115200", "57600", "2400", "1200"]   # порядок перебора


@register
class PTA8D08(Driver):
    type_id = "pta8d08"
    title = "Pt100 ×8"
    model = "PTA8D08 · eletechsup"
    icon = "thermo"
    scan_what = "скорость и адрес Modbus"
    settings = [
        Field("port", "Порт", "port", "COM26"),
        Field("baud", "Скорость", "select", "9600", unit="бод", options=BAUDS),
        Field("addr", "Адрес Modbus", "number", 1, min=1, max=247, step=1),
        Field("period", "Период опроса", "select", "1", unit="с", live=True,
              options=[("0.5", "0,5"), "1", "2", "5"]),
        Field("write_r", "Писать сопротивление R1–R8", "toggle", True,
              hint="Чтобы пересчитать калибровку задним числом."),
    ]

    @classmethod
    def discover(cls, cfg, children=None):
        c = RtuClient(cfg["port"], int(cfg["baud"]), timeout=0.3)
        try:
            ok = c.read_holding(int(cfg["addr"]), T_BASE, NCH) is not None
            return Found(ok, "" if ok else (c.last_error or "нет ответа"))
        finally:
            c.close()

    @classmethod
    def scan(cls, cfg, report, stop, taken=()):
        port = cfg["port"]
        busy = {int(t["addr"]) for t in taken if t.get("port") == port and t.get("addr") is not None}
        bauds = [cfg["baud"]] + [b for b in LIKELY if b != cfg["baud"]]
        quick = [a for a in dict.fromkeys([int(cfg["addr"]), ANY_ADDR]) if a not in busy]
        full = [a for a in range(1, 248) if a not in busy and a not in quick]
        total, n = len(bauds) * (len(quick) + len(full)), 0
        c = RtuClient(port, int(bauds[0]))
        if not c.connect():
            raise DriverError(f"{port}: {c.last_error.removeprefix('порт: ')}")
        try:
            for addrs in (quick, full):        # сначала адрес из настроек и общий 255, потом все
                for b in bauds:
                    c.set_line(int(b), reply_timeout(int(b)))
                    for a in addrs:
                        if stop.is_set():
                            return None
                        report(n / total, f"{port} · {b} бод · " + ("общий адрес" if a == ANY_ADDR else f"адрес {a}"))
                        n += 1
                        got = cls._whoami(c, a)
                        if got is not None and got not in busy and (a != ANY_ADDR or cls._whoami(c, got) == got):
                            return {"port": port, "baud": b, "addr": got}
            return None
        finally:
            c.close()

    @staticmethod
    def _whoami(c, a):
        """Адрес, которым плата назвалась в ответ на запрос по адресу a, или None."""
        r = c.read_holding(a, REG_ADDR, 1)
        if r is None:
            if (c.last_error or "").startswith("порт"):
                raise DriverError(f"{c.port}: {c.last_error.removeprefix('порт: ')}")
            return None
        if not 1 <= r[0] <= 247 or (a != ANY_ADDR and r[0] != a):
            return None
        return r[0]

    def channels(self):
        rate = 1 / float(self.cfg["period"])
        ch = [Channel(f"T{i}", f"ch{i}", "scalar", "°C", rate, dp=1) for i in range(1, NCH + 1)]
        if self.cfg["write_r"]:
            ch += [Channel(f"R{i}", f"R{i}", "scalar", "Ом", rate, dp=1, hidden=True, of=f"T{i}") for i in range(1, NCH + 1)]
        return ch

    def open(self):
        self.client = RtuClient(self.cfg["port"], int(self.cfg["baud"]))

    def close(self):
        self.client.close()

    def run(self, stop):
        tick = Ticker(float(self.cfg["period"]))
        fails = 0
        while True:
            addr = int(self.cfg["addr"])
            T = self.client.read_holding(addr, T_BASE, NCH)
            R = self.client.read_holding(addr, R_BASE, NCH) if self.cfg["write_r"] else None
            t = time.time()
            if T is None and R is None:
                fails += 1
                if fails == LOST_AFTER:
                    self.ctx.online(False, self.client.last_error or "нет ответа")
            else:
                fails = 0
                values = {}
                if T is not None:
                    values.update({f"T{i + 1}": s16(x) / 10 for i, x in enumerate(T)})
                if R is not None:
                    values.update({f"R{i + 1}": x / 10 for i, x in enumerate(R)})
                self.ctx.emit(values, t)
            if tick.wait(stop, float(self.cfg["period"])):
                return
