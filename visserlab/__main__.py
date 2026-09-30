"""Стенд Visser: запись прогонов.

  python -m visserlab record --name dry01 --note "пустой патрон, проверка"
  python -m visserlab record --duration 60          # автостоп через минуту
  python -m visserlab probe scan                    # найти плату на шине
  python -m visserlab probe dump --addr 1           # регистры 0..63
"""
import argparse
from pathlib import Path

from . import probe
from .record import load_stand, record

DEFAULT_CONFIG = Path(__file__).with_name("stand.yaml")


def main():
    p = argparse.ArgumentParser(prog="python -m visserlab", description=__doc__,
                               formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", default=DEFAULT_CONFIG, help="stand.yaml (по умолчанию visserlab/stand.yaml)")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("record", help="записать прогон")
    r.add_argument("--name", default="", help="суффикс имени папки прогона")
    r.add_argument("--note", default="", help="заметка в meta.yaml")
    r.add_argument("--duration", type=float, default=None, help="автостоп, с")
    r.add_argument("--runs-dir", default=None, help="куда класть прогоны (по умолчанию runs/)")

    pr = sub.add_parser("probe", help="разведка Modbus-шины")
    pr.add_argument("what", choices=["scan", "dump"])
    pr.add_argument("--port", default=None)
    pr.add_argument("--baud", type=int, default=None)
    pr.add_argument("--addr", type=int, default=None)
    pr.add_argument("--count", type=int, default=64)
    pr.add_argument("-v", "--verbose", action="store_true")

    a = p.parse_args()
    if a.cmd == "record":
        record(a.config, a.name, a.note, a.duration, a.runs_dir)
        return

    bus = (load_stand(a.config).get("sources") or {}).get("pt100", {})
    port = a.port or bus.get("port", "COM26")
    if a.what == "scan":
        probe.scan(port, bauds=(a.baud,) if a.baud else (9600, 19200, 4800, 38400, 115200))
    else:
        probe.dump(port, a.baud or bus.get("baud", 9600), a.addr or bus.get("addr", 1),
                   a.count, a.verbose)


if __name__ == "__main__":
    main()
