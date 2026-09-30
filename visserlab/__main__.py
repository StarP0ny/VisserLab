"""VisserLab: регистратор опытов.

  python -m visserlab collect                    сборщик: держит приборы, пишет опыты, ждёт клиентов
  python -m visserlab web                        веб-интерфейс (к уже запущенному сборщику), с телефона — по QR
  python -m visserlab ctl <команда> [аргументы]  управление запущенным сборщиком (ctl без команды — справка)
  python -m visserlab record [--template ID]     запись из консоли, без сборщика и веба
  python -m visserlab devices                    приборы из конфига и проверка, отвечают ли
  python -m visserlab probe scan|dump            разведка Modbus-шины
"""
import argparse
import asyncio
import sys

from . import probe


def main():
    p = argparse.ArgumentParser(prog="python -m visserlab", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", default=None, help="папка конфига (по умолчанию VisserLab/config)")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("collect", help="запустить сборщик")
    c.add_argument("--port", type=int, default=None)
    c.add_argument("--runs-dir", default=None, help="куда писать опыты (по умолчанию из конфига)")

    w = sub.add_parser("web", help="веб-интерфейс")
    w.add_argument("--host", default="0.0.0.0", help="127.0.0.1 — только для этого ПК; по умолчанию и для телефона, по ссылке с токеном")
    w.add_argument("--new-token", action="store_true", help="выдать новый токен: старые ссылки на телефонах перестанут работать")
    w.add_argument("--port", type=int, default=8080)
    w.add_argument("--collector-port", type=int, default=None, help="порт сборщика (по умолчанию из конфига)")

    k = sub.add_parser("ctl", help="команда запущенному сборщику", add_help=False)
    k.add_argument("--port", type=int, default=None)
    k.add_argument("args", nargs=argparse.REMAINDER)

    r = sub.add_parser("record", help="записать опыт из консоли")
    r.add_argument("--name", default="")
    r.add_argument("--note", default="")
    r.add_argument("--devices", default="", help="id приборов через запятую")
    r.add_argument("--template", default=None)
    r.add_argument("--duration", type=float, default=None, help="автостоп, с")
    r.add_argument("--runs-dir", default=None)

    sub.add_parser("devices", help="приборы из конфига и проверка связи")

    pr = sub.add_parser("probe", help="разведка Modbus-шины")
    pr.add_argument("what", choices=["scan", "dump"])
    pr.add_argument("--port", default="COM26")
    pr.add_argument("--baud", type=int, default=None)
    pr.add_argument("--addr", type=int, default=1)
    pr.add_argument("--count", type=int, default=64)
    pr.add_argument("-v", "--verbose", action="store_true")

    a = p.parse_args()

    if a.cmd == "probe":
        if a.what == "scan":
            probe.scan(a.port, bauds=(a.baud,) if a.baud else (9600, 19200, 4800, 38400, 115200))
        else:
            probe.dump(a.port, a.baud or 9600, a.addr, a.count, a.verbose)
        return 0

    from .config import ConfigError, load
    try:
        cfg = load(a.config)
    except ConfigError as e:
        print(e, file=sys.stderr)
        return 2

    if a.cmd == "web":
        if a.collector_port:
            cfg.port = a.collector_port
        return web(cfg, a.host, a.port, a.new_token)

    if a.cmd == "ctl":
        from . import ctl
        return ctl.main(a.port or cfg.port, a.args)

    if a.cmd == "record":
        from pathlib import Path
        from .record import record
        if a.runs_dir:
            cfg.runs_dir = Path(a.runs_dir)
        devices = [x for x in a.devices.split(",") if x]
        record(cfg, a.name, a.note, devices or None, a.template, a.duration)
        return 0

    from .core.collector import Collector
    from .core.driver import REGISTRY

    if a.cmd == "devices":
        found = Collector(cfg).request("discover")
        for i, inv in cfg.devices.items():
            f = found.get(i, {})
            name = inv.get("name") or REGISTRY[inv["driver"]].title
            pad = "    " if inv.get("parent") else ""
            print(f"{pad}{'✓' if f.get('ok') else '✕'} {i:<12} {inv['driver']:<14} {name}  {f.get('note', '')}")
        return 0

    if a.cmd == "collect":
        from .core.server import serve
        from .record import ConsoleLog
        port = a.port or cfg.port
        if a.runs_dir:
            from pathlib import Path
            cfg.runs_dir = Path(a.runs_dir)
        coll = Collector(cfg).launch()
        coll.subscribe(ConsoleLog(coll, status_every=0))
        print(f"Сборщик: 127.0.0.1:{port}, опыты в {cfg.runs_dir}. Ctrl-C — остановить "
              f"(идущий опыт будет остановлен и сохранён).", flush=True)
        try:
            asyncio.run(serve(coll, port=port))
        except KeyboardInterrupt:
            pass
        except OSError as e:
            print(f"Порт {port} занят — сборщик уже запущен? ({e})", file=sys.stderr)
            return 2
        finally:
            run = coll.request("shutdown", by="сборщик") if coll._alive else None
            coll.close()
            if run:
                print(f"Опыт сохранён: {run['dir']}")
        return 0


def web(cfg, host, port, new_token=False):
    import uvicorn

    from .config import web_token
    from .web.server import LOOPBACK, create_app, phone_urls
    token = None if host in LOOPBACK else web_token(cfg, new=new_token)
    print(f"Веб: http://127.0.0.1:{port}/  (сборщик ждём на 127.0.0.1:{cfg.port})")
    if token:
        for url in phone_urls(port, token)[:1]:
            print(f"  с телефона: {url}   (или кнопка «Телефон» — QR)")
        print("  Windows при первом запуске спросит про брандмауэр: разрешите для частной сети.")
    print("Ctrl-C — остановить веб. Сборщик и опыт это не трогает.", flush=True)
    try:
        uvicorn.run(create_app(cfg.port, token, port=port), host=host, port=port, log_level="warning")
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
