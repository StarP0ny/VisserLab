"""Плата PTA8D08 (eletechsup): 8 каналов Pt100, Modbus RTU.

Карта регистров (снята дампом 2026-09-29, PDF производителя не понадобился):
  0..7    температура, °C x10, знаковое
  32..39  сопротивление, Ом x10
Линеаризация платы совпадает с IEC 60751 / ГОСТ 6651 (111,6 Ом <-> 29,8 °C),
поэтому R пишется рядом с T: по нему калибровку можно пересчитать задним числом.

Незадействованные входы читаются как ~137,6 Ом / ~97,7 °C — это не данные и
по значению их не отличить (97 °C — нормальная температура корпуса). Какие
каналы подключены, решает только stand.yaml; в CSV пишутся все восемь.
"""
import csv
import threading
import time

from ..modbus import RtuClient, s16

T_BASE, R_BASE, NCH = 0, 32, 8
LOST_AFTER = 3  # подряд неудачных опросов до события «нет связи»


class Pt100Source:
    name = "pt100"

    def __init__(self, cfg, run):
        self.client = RtuClient(cfg["port"], cfg.get("baud", 9600))
        self.addr = cfg.get("addr", 1)
        self.period = float(cfg.get("period_s", 1.0))
        self.channels = {int(k): v or {} for k, v in (cfg.get("channels") or {}).items()}
        self.run = run
        self.latest = None  # (t_unix, [T1..T8], [R1..R8])
        self.n_rows = 0
        self.n_fail = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name=self.name, daemon=True)

    def labels(self):
        """(номер канала, подпись) для консоли и UI: подключённые, иначе все."""
        if self.channels:
            return [(ch, c.get("point", f"ch{ch}")) for ch, c in sorted(self.channels.items())]
        return [(ch, f"ch{ch}") for ch in range(1, NCH + 1)]

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=5)
        self.client.close()

    def summary(self):
        return {"rows": self.n_rows, "failed_polls": self.n_fail}

    def _loop(self):
        path = self.run.dir / f"{self.name}.csv"
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["t_unix", "t_mono"]
                       + [f"T{i}" for i in range(1, NCH + 1)]
                       + [f"R{i}" for i in range(1, NCH + 1)])
            online, fails = None, 0
            next_t = time.monotonic()
            while not self._stop.is_set():
                T = self.client.read_holding(self.addr, T_BASE, NCH)
                R = self.client.read_holding(self.addr, R_BASE, NCH)
                t_unix, t_mono = time.time(), time.monotonic()

                if T is None and R is None:
                    fails += 1
                    self.n_fail += 1
                    if online is not False and fails >= LOST_AFTER:
                        self.run.event(f"{self.name}: нет связи ({self.client.last_error})", "system")
                        online = False
                else:
                    if online is not True:
                        self.run.event(f"{self.name}: связь есть", "system")
                        online = True
                    fails = 0
                    Tv = [s16(x) / 10 for x in T] if T else [""] * NCH
                    Rv = [x / 10 for x in R] if R else [""] * NCH
                    w.writerow([f"{t_unix:.3f}", f"{t_mono:.3f}", *Tv, *Rv])
                    f.flush()
                    self.latest = (t_unix, Tv, Rv)
                    self.n_rows += 1

                # расписание от старта, а не sleep(period): иначе шаг плывёт на время опроса
                next_t += self.period
                delay = next_t - time.monotonic()
                if delay < 0:
                    next_t, delay = time.monotonic(), 0
                self._stop.wait(delay)
