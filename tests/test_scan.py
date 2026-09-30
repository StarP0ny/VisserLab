"""Поиск приборов: «Обновить» на текущих настройках, перебор скорости и адреса, local.yaml."""
import sys
import threading

import pytest
import yaml

import visserlab.drivers.pta8d08 as pta
from visserlab.config import load, save_local
from visserlab.core.collector import CollectorError
from visserlab.core.driver import REGISTRY, DriverError
from test_collector import make, wait_for


# ---------- PTA8D08 на имитации шины
class Bus:
    """Платы на одной шине: {адрес: скорость}. На 255 отвечают все сразу — одна даёт ответ, две сталкиваются."""

    def __init__(self, boards, port="COM9", any_addr=True):
        self.boards, self.port, self.any_addr, self.calls = boards, port, any_addr, 0

    def client(self, port, baud=9600, timeout=0.3):
        bus = self

        class FakeRtu:
            def __init__(self):
                self.port, self.baud, self.last_error = port, int(baud), None

            def connect(self):
                if self.port != bus.port:
                    self.last_error = "порт: нет в системе"
                    return False
                return True

            def set_line(self, baud=None, timeout=None):
                self.baud = baud or self.baud

            def close(self):
                pass

            def read_holding(self, addr, start, count):
                bus.calls += 1
                here = [a for a, b in bus.boards.items() if b == self.baud]
                who = here if addr == pta.ANY_ADDR and bus.any_addr else [a for a in here if a == addr]
                if len(who) != 1:
                    self.last_error = "битый кадр" if who else "таймаут"
                    return None
                return [who[0]] if start == pta.REG_ADDR else [250] * count

        return FakeRtu()


def scan(monkeypatch, bus, taken=(), stop=None, **cfg):
    monkeypatch.setattr(pta, "RtuClient", bus.client)
    cfg = {**pta.PTA8D08.defaults(), "port": "COM9", **cfg}
    seen = []
    res = pta.PTA8D08.scan(cfg, lambda f, t: seen.append((f, t)), stop or threading.Event(), taken)
    return res, seen


def test_pta_scan_by_common_address(monkeypatch):
    bus = Bus({7: 19200})
    res, seen = scan(monkeypatch, bus)
    assert res == {"port": "COM9", "baud": "19200", "addr": 7}
    assert bus.calls < 20                                  # хватило быстрого круга по адресу 255
    assert all(0 <= f < 1 for f, _ in seen) and "бод" in seen[-1][1]


def test_pta_scan_full_sweep_skips_taken(monkeypatch):
    bus = Bus({7: 19200, 9: 19200})                        # две платы: ответы на 255 сталкиваются
    res, _ = scan(monkeypatch, bus, taken=[{"port": "COM9", "addr": 7}, {"port": "COM5", "addr": 9}])
    assert res == {"port": "COM9", "baud": "19200", "addr": 9}
    assert bus.calls > 247


def test_pta_scan_stop_and_errors(monkeypatch):
    stop = threading.Event()
    stop.set()
    assert scan(monkeypatch, Bus({7: 19200}), stop=stop)[0] is None
    assert scan(monkeypatch, Bus({}, any_addr=False))[0] is None
    with pytest.raises(DriverError, match="COM8: нет в системе"):
        scan(monkeypatch, Bus({7: 19200}), port="COM8")


# ---------- сборщик
class Sub:
    frames = False

    def __init__(self):
        self.msgs = []

    def send(self, msg):
        self.msgs.append(msg)


@pytest.fixture
def fast_bus(monkeypatch):
    mod = sys.modules[REGISTRY["sim_rtu"].__module__]
    monkeypatch.setattr(mod, "SIM_STEP_S", 0)          # без пауз: на Windows wait() не короче ~15 мс
    return mod


def test_refresh_uses_drafts(tmp_path, fast_bus):
    coll = make(tmp_path)
    try:
        assert coll.request("discover")["sim_rtu"] == {"ok": False, "note": "таймаут"}
        found = coll.request("discover", settings={"sim_rtu": {"baud": "19200", "addr": 7}})
        assert found["sim_rtu"]["ok"]
        assert not coll.cfg.local                           # правки из ⚙ не запоминаются
    finally:
        coll.close()


def test_scan_finds_and_remembers(tmp_path, fast_bus):
    coll = make(tmp_path)
    sub = Sub()
    coll.subscribe(sub)
    try:
        coll.request("discover")
        assert coll.request("scan") == {"devices": ["sim_rtu"]}         # все ненайденные, кто умеет перебор
        assert wait_for(lambda: not coll.scan["run"], timeout=10)
        assert coll.scan["done"]["sim_rtu"] == {"ok": True, "note": "", "settings": {"port": "SIM1", "baud": "19200", "addr": 7}}
        assert coll.found["sim_rtu"]["ok"]
        inv = {i["id"]: i for i in coll.request("hello")["inventory"]}
        assert inv["sim_rtu"]["settings"]["addr"] == 7 and inv["sim_rtu"]["local"] == {"baud": "19200", "addr": 7}
        assert coll.request("discover")["sim_rtu"]["ok"]                 # «Обновить» теперь находит сразу
        with pytest.raises(CollectorError, match="Искать некого"):
            coll.request("scan")
    finally:
        coll.close()
    kinds = [m["type"] for m in sub.msgs]
    assert "inventory" in kinds
    assert any(m["type"] == "scan" and m["scan"]["run"] and "адрес" in m["scan"]["text"] for m in sub.msgs)
    local = yaml.safe_load((tmp_path / "local.yaml").read_text(encoding="utf-8"))
    assert local == {"devices": {"sim_rtu": {"addr": 7, "baud": "19200"}}}   # только то, что изменилось


def test_scan_nobody_and_other_port(tmp_path, fast_bus):
    coll = make(tmp_path)
    try:
        coll.request("scan", devices=["sim_rtu"], port="SIM2")
        assert wait_for(lambda: not coll.scan["run"], timeout=10)
        assert coll.scan["done"]["sim_rtu"] == {"ok": False, "note": "перебор: никто не ответил"}
        assert coll.found["sim_rtu"]["ok"] is False and not coll.cfg.local
        fast_bus.BUS["SIM2"] = ("4800", 3)
        coll.request("scan", devices=["sim_rtu"], port="SIM2")
        assert wait_for(lambda: not coll.scan["run"], timeout=10)
        assert coll.cfg.local["sim_rtu"] == {"port": "SIM2", "baud": "4800", "addr": 3}
    finally:
        fast_bus.BUS.pop("SIM2", None)
        coll.close()


def test_scan_excludes_prepare(tmp_path, fast_bus, monkeypatch):
    monkeypatch.setattr(fast_bus, "SIM_STEP_S", 0.01)
    coll = make(tmp_path)
    try:
        with pytest.raises(CollectorError, match="не поддерживается"):
            coll.request("scan", devices=["syringe"])
        coll.request("scan", devices=["sim_rtu"], port="SIM2")            # на SIM2 никого: идёт долго
        with pytest.raises(CollectorError, match="перебор"):
            coll.request("prepare", devices=["sim_pt100"])
        with pytest.raises(CollectorError, match="перебор"):
            coll.request("discover")
        with pytest.raises(CollectorError, match="уже идёт"):
            coll.request("scan", devices=["sim_rtu"])
        coll.request("scan_stop")
        assert wait_for(lambda: not coll.scan["run"], timeout=3)
        assert coll.scan["done"]["sim_rtu"]["note"] == "остановлено"
        coll.request("prepare", devices=["sim_pt100"])
        with pytest.raises(CollectorError, match="до подготовки"):
            coll.request("scan", devices=["sim_rtu"])
    finally:
        coll.close()


def test_local_yaml_overrides_config(tmp_path):
    (tmp_path / "devices.yaml").write_text(
        'devices:\n  pt100: {driver: pta8d08, settings: {port: COM26, baud: "9600", addr: 1}}\n', encoding="utf-8")
    (tmp_path / "local.yaml").write_text("devices:\n  pt100: {port: COM27, addr: 3}\n", encoding="utf-8")
    cfg = load(tmp_path)
    assert cfg.devices["pt100"]["settings"] == {"port": "COM27", "baud": "9600", "addr": 3}
    assert load(tmp_path, local_on=False).devices["pt100"]["settings"]["port"] == "COM26"
    save_local(cfg, "pt100", {"baud": "19200"})
    assert load(tmp_path).devices["pt100"]["settings"] == {"port": "COM27", "baud": "19200", "addr": 3}
    assert (tmp_path / "local.yaml").read_text(encoding="utf-8").startswith("# Найдено перебором")
