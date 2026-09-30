"""Сетевой вход сборщика: TCP 127.0.0.1, JSON-строки в обе стороны.

Клиент → сборщик:  {"id": 1, "cmd": "start", "args": {...}}
Сборщик → клиент:  {"type": "reply", "id": 1, "ok": true, "result": ...}
                   {"type": "reply", "id": 1, "ok": false, "error": "Стоп — только из паузы"}
                   {"type": "state" | "status" | "event" | "data" | "frame" | "device" | ...}

Команды и сообщения описаны в docs/COLLECTOR.md. Клиентов может быть несколько;
если клиент не успевает читать, живые данные для него выбрасываются, а в
следующем сообщении приходит {"type": "lag"} — пора заново спросить hello.
"""
import asyncio
import json
import math

from .collector import CollectorError
from .driver import DriverError

QUEUE_MAX = 2000
LIVE = ("data", "frame", "status")
LOCAL_ONLY = ("shutdown",)          # сборщик запускает и гасит человек, не клиент


def _clean(o):
    if isinstance(o, float):
        return None if math.isnan(o) or math.isinf(o) else o
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    return o


def encode(msg):
    return (json.dumps(_clean(msg), ensure_ascii=False, separators=(",", ":")) + "\n").encode()


class _Client:
    def __init__(self, loop, writer):
        self.loop, self.writer = loop, writer
        self.q = asyncio.Queue()
        self.frames = False
        self.lagging = False

    def send(self, msg):                     # из потока диспетчера
        data = encode(msg)
        self.loop.call_soon_threadsafe(self._put, data, msg.get("type"))

    def _put(self, data, typ):
        if typ in LIVE and self.q.qsize() > QUEUE_MAX:
            self.lagging = True
            return
        if self.lagging and typ not in LIVE:
            self.q.put_nowait(encode({"type": "lag"}))
            self.lagging = False
        self.q.put_nowait(data)

    async def pump(self):
        while True:
            data = await self.q.get()
            self.writer.write(data)
            await self.writer.drain()


async def _handle(coll, reader, writer):
    loop = asyncio.get_running_loop()
    client = _Client(loop, writer)
    coll.subscribe(client)
    pump = asyncio.create_task(client.pump())
    try:
        while True:
            line = await reader.readline()
            if not line:
                break
            try:
                req = json.loads(line)
                rid, cmd, args = req.get("id"), req["cmd"], req.get("args") or {}
            except (ValueError, KeyError, AttributeError):
                client._put(encode({"type": "reply", "id": None, "ok": False, "error": "Неверный запрос"}), "reply")
                continue
            if cmd == "hello":
                client.frames = bool(args.pop("frames", False))
            if cmd in LOCAL_ONLY:
                client._put(encode({"type": "reply", "id": rid, "ok": False,
                                    "error": "Остановить сборщик можно только в его окне: Ctrl-C"}), "reply")
                continue
            try:
                res = await loop.run_in_executor(None, lambda: coll.request(cmd, **args))
                reply = {"type": "reply", "id": rid, "ok": True, "result": res}
            except (CollectorError, DriverError) as e:
                reply = {"type": "reply", "id": rid, "ok": False, "error": str(e)}
            except TypeError:
                reply = {"type": "reply", "id": rid, "ok": False, "error": f"{cmd}: неверные аргументы"}
            client._put(encode(reply), "reply")
    except (ConnectionError, asyncio.IncompleteReadError):
        pass
    finally:
        coll.unsubscribe(client)
        pump.cancel()
        writer.close()


async def serve(coll, host="127.0.0.1", port=8765, ready=None):
    server = await asyncio.start_server(lambda r, w: _handle(coll, r, w), host, port, limit=2 ** 22)
    if ready is not None:
        ready(server.sockets[0].getsockname()[1])
    async with server:
        await server.serve_forever()
