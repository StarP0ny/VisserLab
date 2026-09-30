"""PTA8D08 (eletechsup): 8 каналов Pt100, Modbus RTU по RS485.

Карта регистров снята дампом 2026-09-29:
  0..7    температура, °C ×10, знаковое
  32..39  сопротивление, Ом ×10
Линеаризация платы совпадает с IEC 60751 (111,6 Ом ↔ 29,8 °C), поэтому R пишется
рядом с T: по омам калибровку можно пересчитать задним числом.

Пустой вход читается как ~137,6 Ом / ~97,7 °C, и по значению его не отличить от
горячего корпуса. Какие входы подключены, видно по подписям каналов в конфиге;
пишутся все восемь.
"""
import time

from ..core.driver import Channel, Driver, Field, Found, Ticker, register
from ..modbus import RtuClient, s16

T_BASE, R_BASE, NCH = 0, 32, 8
LOST_AFTER = 3          # подряд пустых опросов до «нет связи»


@register
class PTA8D08(Driver):
    type_id = "pta8d08"
    title = "Pt100 ×8"
    model = "PTA8D08 · eletechsup"
    icon = "thermo"
    settings = [
        Field("port", "Порт", "text", "COM26"),
        Field("baud", "Скорость", "select", "9600", unit="бод", options=["4800", "9600", "19200", "38400"]),
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

    def channels(self):
        rate = 1 / float(self.cfg["period"])
        ch = [Channel(f"T{i}", f"ch{i}", "scalar", "°C", rate, dp=1) for i in range(1, NCH + 1)]
        if self.cfg["write_r"]:
            ch += [Channel(f"R{i}", f"R{i}", "scalar", "Ом", rate, dp=1, hidden=True) for i in range(1, NCH + 1)]
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
