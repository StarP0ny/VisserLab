"""Веб-интерфейс: отдаёт страницу и мостит WebSocket браузера к сборщику.

  браузер ⇄ /ws ⇄ TCP 127.0.0.1:<порт сборщика>

Каждый браузер — отдельный клиент сборщика. Если сборщика нет, браузер
получает {"type": "collector", "up": false}, а мост пробует подключиться
каждые 2 с. Сам сборщик веб не запускает.

С этого ПК страница открывается просто. С других устройств (телефон) — только
по ссылке с токеном, которую печатает `visserlab web --host 0.0.0.0`.
"""
import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

STATIC = Path(__file__).with_name("static")


class FreshStatic(StaticFiles):
    """Статика с no-cache: браузер перепроверяет файл по ETag (ответ 304 — дёшево) и после
    обновления кода не выполняет старый app.js из кэша."""

    def file_response(self, *a, **kw):
        resp = super().file_response(*a, **kw)
        resp.headers["Cache-Control"] = "no-cache"
        return resp
RETRY_S = 2.0
LOOPBACK = {"127.0.0.1", "::1", "localhost"}
NO_TOKEN = 4401          # код закрытия WebSocket: нужна ссылка с токеном


def create_app(collector_port: int, token: str | None = None, collector_host="127.0.0.1") -> FastAPI:
    app = FastAPI(title="VisserLab", docs_url=None, redoc_url=None, openapi_url=None)
    app.mount("/static", FreshStatic(directory=STATIC), name="static")

    @app.get("/")
    async def index():
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        for name in ("app.js", "app.css"):     # версия в адресе: файл из кэша, взятый до обновления, не подхватится
            html = html.replace(f"/static/{name}", f"/static/{name}?v={(STATIC / name).stat().st_mtime_ns}")
        return HTMLResponse(html, headers={"Cache-Control": "no-cache"})

    @app.websocket("/ws")
    async def ws(websocket: WebSocket):
        host = websocket.client.host if websocket.client else ""
        if host not in LOOPBACK and (token is None or websocket.query_params.get("t") != token):
            await websocket.close(code=NO_TOKEN)
            return
        await websocket.accept()
        await bridge(websocket, collector_host, collector_port)

    return app


async def bridge(ws: WebSocket, host, port):
    """Пока браузер подключён — держит соединение со сборщиком и переподключается."""
    inbox: asyncio.Queue[str] = asyncio.Queue()
    closed = asyncio.Event()

    async def read_browser():
        try:
            while True:
                inbox.put_nowait(await ws.receive_text())
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            closed.set()

    async def say(msg):
        try:
            await ws.send_text(msg if isinstance(msg, str) else json.dumps(msg, ensure_ascii=False))
        except (WebSocketDisconnect, RuntimeError):
            closed.set()

    reader_task = asyncio.create_task(read_browser())
    loop = asyncio.get_running_loop()
    told_down = False
    try:
        while not closed.is_set():
            try:
                r, w = await asyncio.open_connection(host, port, limit=2 ** 23)
            except OSError:
                if not told_down:
                    await say({"type": "collector", "up": False, "port": port})
                    told_down = True
                deadline = loop.time() + RETRY_S
                while not closed.is_set() and (left := deadline - loop.time()) > 0:
                    try:
                        line = await asyncio.wait_for(inbox.get(), left)
                    except TimeoutError:
                        break
                    await say({"type": "reply", "id": _id(line), "ok": False, "error": "Сборщик не запущен"})
                continue

            told_down = False
            await say({"type": "collector", "up": True, "port": port})

            async def up():
                while line := await r.readline():
                    await say(line.decode("utf-8").rstrip("\n"))
                    if closed.is_set():
                        return

            async def down():
                while True:
                    w.write((await inbox.get()).encode("utf-8") + b"\n")
                    await w.drain()

            tasks = {asyncio.create_task(up()), asyncio.create_task(down()), asyncio.create_task(closed.wait())}
            _, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for t in pending:
                t.cancel()
            w.close()
            if not closed.is_set():
                await say({"type": "collector", "up": False, "port": port})
                told_down = True
    finally:
        reader_task.cancel()


def _id(line):
    try:
        return json.loads(line).get("id")
    except (ValueError, AttributeError):
        return None
