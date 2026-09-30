"""Консольный клиент сборщика: одна команда или поток сообщений.

  ctl hello | discover | ports | start | pause | resume | stop | cancel | mark
  ctl scan [devices=pt100] [port=COM27]      перебор; ctl scan_stop — остановить
  ctl prepare name=dry03 devices=pt100,syringe [template=visser_patron] [note=текст]
  ctl note текст заметки
  ctl set pt100 period=2
  ctl action syringe add value=0,56
  ctl history pt100:T1 points=200
  ctl watch [--data]
  ctl <команда> '{"json": "аргументы"}'
"""
import json
import socket
import sys

import yaml

LIST_KEYS = {"devices"}
TEXT_KEYS = {"name", "note", "text", "template", "port"}


class NoCollector(Exception):
    pass


def connect(port, timeout=5):
    try:
        return socket.create_connection(("127.0.0.1", port), timeout=timeout)
    except OSError:
        raise NoCollector(f"Сборщик не отвечает на 127.0.0.1:{port}. Запустите: python -m visserlab collect") from None


def _value(k, v):
    if k in LIST_KEYS:
        return [x for x in v.split(",") if x]
    if k in TEXT_KEYS:
        return v
    for conv in (int, float):
        try:
            return conv(v)
        except ValueError:
            pass
    return v


def _kv(tokens):
    out = {}
    for tok in tokens:
        if "=" not in tok:
            raise SystemExit(f"Ожидалось ключ=значение, а не «{tok}»")
        k, v = tok.split("=", 1)
        out[k] = _value(k, v)
    return out


SIGNED = {"prepare", "start", "pause", "resume", "stop", "cancel", "note", "mark", "set", "action"}


def parse(cmd, rest):
    if len(rest) == 1 and rest[0].lstrip().startswith("{"):
        args = json.loads(rest[0])
    elif cmd == "note":
        args = {"text": " ".join(rest)}
    elif cmd == "set":
        args = {"device": rest[0], "changes": _kv(rest[1:])}
    elif cmd == "action":
        args = {"device": rest[0], "name": rest[1], "args": _kv(rest[2:])}
    elif cmd == "history":
        args = {"channel": rest[0], **_kv(rest[1:])}
    else:
        args = _kv(rest)
    if cmd in SIGNED:
        args.setdefault("by", "ctl")          # в журнале видно, откуда пришла команда
    return args


def _lines(sock):
    buf = b""
    while True:
        chunk = sock.recv(65536)
        if not chunk:
            return
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            yield json.loads(line)


def call(port, cmd, args):
    with connect(port) as s:
        s.sendall((json.dumps({"id": 1, "cmd": cmd, "args": args}, ensure_ascii=False) + "\n").encode())
        for msg in _lines(s):
            if msg.get("type") == "reply" and msg.get("id") == 1:
                return msg
    raise NoCollector("Сборщик закрыл соединение")


def watch(port, data=False):
    with connect(port, timeout=None) as s:
        s.sendall(b'{"id": 0, "cmd": "hello", "args": {"frames": false}}\n')
        for msg in _lines(s):
            typ = msg.get("type")
            if typ == "event":
                e = msg["event"]
                print(f"[{e['kind']}] {e['text']}" + (f"  · {e['by']}" if e.get("by") else ""), flush=True)
            elif typ == "state":
                print(f"== {msg['state']}  {msg.get('name') or ''}", flush=True)
            elif typ == "status":
                bad = [f"{i}:{d['status']}" for i, d in msg["devices"].items() if d["status"] != "ok"]
                print(f"status {msg['state']} {msg['alarms']['level']} {' '.join(bad)}", flush=True)
            elif typ == "data" and data:
                print("data " + " ".join(f"{c}={p[-1][1]:.2f}" for c, p in msg["ch"].items()), flush=True)
            elif typ in ("device_status", "device", "found", "lag"):
                print(f"{typ} {json.dumps({k: v for k, v in msg.items() if k != 'type'}, ensure_ascii=False)[:200]}", flush=True)


def main(port, argv):
    if not argv:
        print(__doc__)
        return 1
    cmd, rest = argv[0], argv[1:]
    try:
        if cmd == "watch":
            watch(port, data="--data" in rest)
            return 0
        msg = call(port, cmd, parse(cmd, rest))
    except NoCollector as e:
        print(e, file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 0
    if not msg["ok"]:
        print(f"Ошибка: {msg['error']}", file=sys.stderr)
        return 1
    if msg.get("result") is not None:
        print(yaml.safe_dump(msg["result"], allow_unicode=True, sort_keys=False, width=120).rstrip())
    return 0
