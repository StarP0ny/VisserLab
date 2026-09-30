"""Веб-интерфейс: отдаёт страницу и мостит WebSocket браузера к сборщику.

  браузер ⇄ /ws ⇄ TCP 127.0.0.1:<порт сборщика>

Каждый браузер — отдельный клиент сборщика. Если сборщика нет, браузер
получает {"type": "collector", "up": false}, а мост пробует подключиться
каждые 2 с. Сам сборщик веб не запускает.

С этого ПК страница открывается просто. С других устройств (телефон) — только
по ссылке с токеном: её печатает `visserlab web` и показывает кнопка «Телефон» (QR).
"""
import asyncio
import json
import socket
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
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


def lan_ips():
    """Адреса ПК в локальной сети, вероятный первым: 192.168.*, потом 10.*, потом 172.16–31.*
    (там обычно Docker, WSL и VPN-туннели). Маршрут по умолчанию не годится: его забирает VPN."""
    try:
        ips = socket.gethostbyname_ex(socket.gethostname())[2]
    except OSError:
        ips = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))          # пакет не уходит: только выбор маршрута
            ips.append(s.getsockname()[0])
    except OSError:
        pass

    def rank(ip):
        a, b = (int(x) for x in ip.split(".")[:2])
        return 0 if (a, b) == (192, 168) else 1 if a == 10 else 2 if a == 172 and 16 <= b <= 31 else 3

    ips = [ip for i, ip in enumerate(ips) if ip not in ips[:i] and not ip.startswith(("127.", "169.254."))]
    return sorted(ips, key=rank)


def phone_urls(port, token):
    return [f"http://{ip}:{port}/?t={token}" for ip in lan_ips()]


def qr_svg(text):
    import segno
    return segno.make(text, error="m").svg_inline(border=2, dark="#000", light="#fff", omitsize=True)


def create_app(collector_port: int, token: str | None = None, collector_host="127.0.0.1", port=8080) -> FastAPI:
    """token — ссылка для телефона (None: веб только для этого ПК); port — свой порт, для ссылки."""
    app = FastAPI(title="VisserLab", docs_url=None, redoc_url=None, openapi_url=None)
    app.mount("/static", FreshStatic(directory=STATIC), name="static")

    @app.get("/")
    async def index():
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        for name in ("app.js", "app.css"):     # версия в адресе: файл из кэша, взятый до обновления, не подхватится
            html = html.replace(f"/static/{name}", f"/static/{name}?v={(STATIC / name).stat().st_mtime_ns}")
        return HTMLResponse(html, headers={"Cache-Control": "no-cache"})

    @app.get("/api/phone")
    async def phone(request: Request):
        """Ссылка и QR для телефона. Только этому ПК: телефону токен показывать незачем."""
        if (request.client.host if request.client else "") not in LOOPBACK:
            return JSONResponse({"error": "только с этого ПК"}, status_code=403)
        if token is None:
            return {"lan": False}
        return {"lan": True, "links": [{"url": u, "qr": qr_svg(u)} for u in phone_urls(port, token)]}

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
