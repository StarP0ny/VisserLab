"""Веб: страница, мост WebSocket ⇄ сборщик, «сборщика нет», токен для чужих устройств."""
import asyncio
import json
import socket
import threading

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from visserlab.core.server import serve
from visserlab.web.server import NO_TOKEN, create_app
from test_collector import FAST, make

LOCAL = ("127.0.0.1", 50000)


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def collector(tmp_path):
    coll = make(tmp_path)
    ready, box = threading.Event(), {}
    threading.Thread(target=lambda: asyncio.run(serve(coll, port=0, ready=lambda p: (box.update(p=p), ready.set()))),
                     daemon=True).start()
    assert ready.wait(5)
    yield coll, box["p"]
    coll.close()


def until(ws, pred, n=400):
    for _ in range(n):
        m = ws.receive_json()
        if pred(m):
            return m
    raise AssertionError("не дождались сообщения")


def test_page_and_static():
    c = TestClient(create_app(free_port()), client=LOCAL)
    r = c.get("/")
    assert r.status_code == 200 and "<title>VisserLab</title>" in r.text
    assert c.get("/static/app.js").status_code == 200
    assert c.get("/static/app.css").status_code == 200


def test_bridge_to_collector(collector):
    coll, port = collector
    c = TestClient(create_app(port), client=LOCAL)
    with c.websocket_connect("/ws") as ws:
        assert ws.receive_json() == {"type": "collector", "up": True, "port": port}
        ws.send_text(json.dumps({"id": 1, "cmd": "hello", "args": {"frames": True}}))
        m = until(ws, lambda m: m.get("id") == 1)
        assert m["ok"] and m["result"]["state"] == "idle"
        inv = {i["id"]: i for i in m["result"]["inventory"]}
        assert inv["pt100"]["settings"]["port"] == "COM26"            # значения не затёрты схемой
        assert inv["pt100"]["schema"][0]["key"] == "port"
        ws.send_text(json.dumps({"id": 2, "cmd": "prepare", "args": {"devices": ["sim_pt100", "sim_thermal"], "settings": FAST, "by": "ПК"}}))
        until(ws, lambda m: m.get("id") == 2 and m["ok"])
        until(ws, lambda m: m.get("type") == "data" and "sim_pt100:T1" in m["ch"])
        f = until(ws, lambda m: m.get("type") == "frame" and m["ch"] == "sim_thermal:frame")
        assert f["shape"] == [192, 256]
        ws.send_text(json.dumps({"id": 3, "cmd": "action", "args": {"device": "sim_thermal", "name": "roi_add", "args": {"x": 100, "y": 96}}}))
        d = until(ws, lambda m: m.get("type") == "device")        # новый канал приходит раньше ответа
        assert until(ws, lambda m: m.get("id") == 3)["ok"]
        roi = [ch for ch in d["device"]["channels"] if ch["key"] == "roiA"][0]
        assert roi["at"] == ["frame", 100, 96]
        ws.send_text(json.dumps({"id": 4, "cmd": "shutdown"}))
        m = until(ws, lambda m: m.get("id") == 4)
        assert not m["ok"] and "Ctrl-C" in m["error"]
    assert coll.state == "prep"                                           # закрытие вкладки опыт не трогает


def test_collector_down():
    c = TestClient(create_app(free_port()), client=LOCAL)
    with c.websocket_connect("/ws") as ws:
        m = ws.receive_json()
        assert m["type"] == "collector" and m["up"] is False
        ws.send_text(json.dumps({"id": 9, "cmd": "hello"}))
        m = until(ws, lambda m: m.get("id") == 9)
        assert not m["ok"] and m["error"] == "Сборщик не запущен"


def test_phone_needs_token():
    app = create_app(free_port(), token="секрет")
    phone = TestClient(app, client=("192.168.1.50", 40000))
    with pytest.raises(WebSocketDisconnect) as e:
        with phone.websocket_connect("/ws") as ws:
            ws.receive_json()
    assert e.value.code == NO_TOKEN
    with phone.websocket_connect("/ws?t=%D1%81%D0%B5%D0%BA%D1%80%D0%B5%D1%82") as ws:
        assert ws.receive_json()["type"] == "collector"
