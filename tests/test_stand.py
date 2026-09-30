"""Стенд из интерфейса: добавить, подписать, удалить прибор — devices.yaml правится, комментарии живы."""
import shutil
from pathlib import Path

import pytest
import yaml

from visserlab.config import load
from visserlab.core.collector import Collector, CollectorError
from test_collector import STAND


@pytest.fixture
def coll(tmp_path):
    d = tmp_path / "cfg"
    shutil.copytree(STAND, d, ignore=shutil.ignore_patterns("local.yaml", "web_token", "__pycache__"))
    cfg = load(d)
    cfg.runs_dir = tmp_path / "runs"
    c = Collector(cfg).launch()
    yield c
    c.close()


def text(c):
    return (c.cfg.dir / "devices.yaml").read_text(encoding="utf-8")


def test_drivers_list(coll):
    kinds = {d["driver"]: d for d in coll.request("drivers")}
    assert {"pta8d08", "uvc_thermal", "manual", "abs_humidity"} <= set(kinds)
    assert "sim_scd41" not in kinds                         # дети шлюза добавляются не отсюда
    assert kinds["pta8d08"]["schema"][0]["key"] == "port" and kinds["pta8d08"]["defaults"]["baud"] == "9600"


def test_add_edit_delete(coll):
    before = text(coll)
    r = coll.request("device_add", driver="pta8d08", name="Pt100 крышка",
                     settings={"port": "COM27", "baud": "9600", "addr": 3}, channels={"T1": "ch1 крышка", "T2": " "})
    assert r == {"id": "pta8d08"}
    after = text(coll)
    assert after.startswith(before.rstrip("\n"))              # старое не тронуто, в том числе комментарии
    added = yaml.safe_load(after)["devices"]["pta8d08"]
    assert added == {"driver": "pta8d08", "name": "Pt100 крышка", "settings": {"port": "COM27", "addr": 3},
                     "channels": {"T1": "ch1 крышка"}}           # скорость по умолчанию и пустая подпись не пишутся
    inv = {i["id"]: i for i in coll.request("hello")["inventory"]}
    assert inv["pta8d08"]["name"] == "Pt100 крышка"
    ch = {c["key"]: c for c in inv["pta8d08"]["channels"]}
    assert ch["T1"]["name"] == "ch1 крышка" and ch["T2"]["name"] == ch["T2"]["default"] == "ch2"

    assert coll.request("device_add", driver="pta8d08")["id"] == "pta8d08_2"
    with pytest.raises(CollectorError, match="уже есть"):
        coll.request("device_add", driver="manual", id="syringe")
    with pytest.raises(CollectorError, match="латиница"):
        coll.request("device_add", driver="manual", id="Шприц")
    with pytest.raises(CollectorError, match="Адрес"):
        coll.request("device_add", driver="pta8d08", settings={"addr": 999})

    coll.request("device_edit", id="sim_pt100", name="Pt100 сим", channels={"T1": "вход", "T2": "", "T4": "плёнка"})
    e = yaml.safe_load(text(coll))["devices"]["sim_pt100"]
    assert e["name"] == "Pt100 сим"                         # пустая подпись убрана, не переданные не тронуты
    assert e["channels"] == {"T1": "вход", "T3": "ch3 корпус, выход", "T8": "ch8 среда", "T4": "плёнка"}
    assert "# на шине сидит по другому адресу" in text(coll)   # комментарий в середине файла жив

    coll.request("device_del", id="sim_mk")                  # шлюз — вместе с детьми
    devs = coll.request("hello")["inventory"]
    assert not {"sim_mk", "sim_scd41", "sim_sht1"} & {i["id"] for i in devs}
    coll.request("device_del", id="pta8d08_2")
    assert "pta8d08_2" not in yaml.safe_load(text(coll))["devices"]


def test_stand_frozen_during_run(coll):
    coll.request("prepare", devices=["sim_pt100"])
    with pytest.raises(CollectorError, match="недоступна"):
        coll.request("device_add", driver="manual")


def test_template_from_run(coll):
    coll.request("prepare", devices=["sim_pt100", "sim_thermal"], template="sim", settings={"sim_pt100": {"period": "0.5"}})
    coll.request("start")
    coll.request("set", device="sim_pt100", changes={"period": "2"})
    layout = [{"series": ["sim_pt100:T1", "sim_pt100:T2"], "w": 2, "h": 1}, {"series": ["sim_thermal:frame"], "h": 2}, {"series": []}]
    r = coll.request("template_save", name="Сухой прогон", layout=layout, by="ПК")
    assert r == {"id": "сухой_прогон", "exists": False}
    path = coll.cfg.dir / "templates" / "сухой_прогон.yaml"
    tpl = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert tpl["name"] == "Сухой прогон" and tpl["devices"] == ["sim_pt100", "sim_thermal"]
    assert tpl["settings"]["sim_pt100"] == {"period": "2", "speed": "10"}     # что отличается от стенда
    assert [a["channel"] for a in tpl["alarms"]] == ["sim_pt100:T1"]           # правила — только своих приборов
    assert tpl["layout"] == [{"series": ["sim_pt100:T1", "sim_pt100:T2"], "w": 2, "h": 1},
                             {"series": ["sim_thermal:frame"], "w": 1, "h": 2}]
    assert coll.request("template_save", name="сухой прогон")["exists"]
    assert not coll.request("template_save", name="сухой прогон", overwrite=True)["exists"]
    assert coll.request("hello")["templates"]["сухой_прогон"]["layout"] == []    # перезаписан без раскладки
    coll.request("pause")
    coll.request("stop")
    assert not coll.request("template_save", name="после стопа")["exists"]   # и сразу после стопа
    with pytest.raises(CollectorError, match="Нужно имя"):
        coll.request("template_save", name=" / ")
