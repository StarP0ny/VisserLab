"""Конфигурация стенда: приборы (config/devices.yaml) и шаблоны опытов (config/templates/*.yaml).

Рядом может лежать local.yaml — параметры подключения, найденные перебором на этом ПК.
Они перекрывают settings из devices.yaml и в git не попадают.
"""
import hashlib
import importlib.util
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import drivers  # noqa: F401  регистрирует драйверы
from .core.driver import REGISTRY

REPO = Path(__file__).resolve().parents[1]      # visserlab/config.py → корень репо
CONFIG_DIR = REPO / "config"
LOCAL = "local.yaml"
LOCAL_HEAD = ("# Найдено перебором на этом ПК. Перекрывает settings из devices.yaml, в git не идёт.\n"
              "# Удалите прибор отсюда — вернутся значения из devices.yaml.\n")


class ConfigError(Exception):
    pass


@dataclass
class Config:
    devices: dict                 # id -> {driver, name, settings, channels, parent}
    templates: dict = field(default_factory=dict)
    runs_dir: Path = REPO / "runs"
    port: int = 8765
    preroll_s: float = 300.0      # предзапись, с
    preroll_fps: float = 1.0      # частота кадров в предзаписи
    push_hz: float = 10.0         # живые данные клиентам, раз в секунду
    frame_push_fps: float = 2.0   # кадры клиентам, не чаще
    record_default: list = field(default_factory=list)
    local: dict = field(default_factory=dict)       # id -> {настройка: значение} из local.yaml
    local_path: Path | None = None                  # куда сохранять найденное перебором


def load(config_dir=None, local_on=True) -> Config:
    """local_on=False — без local.yaml: тестам нужен стенд как в git."""
    d = Path(config_dir or CONFIG_DIR)
    path = d / "devices.yaml"
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError:
        raise ConfigError(f"Нет файла {path}") from None
    for p in raw.get("plugins") or []:
        _load_plugin(d / p)
    col = raw.get("collector") or {}
    flat = {}
    for i, inv in (raw.get("devices") or {}).items():
        inv = dict(inv or {})
        kids = inv.pop("children", None) or {}
        flat[str(i)] = inv
        for ci, c in kids.items():
            flat[str(ci)] = {**(c or {}), "parent": str(i)}
    for i, inv in flat.items():
        if inv.get("driver") not in REGISTRY:
            raise ConfigError(f"{path.name}: у прибора «{i}» нет драйвера «{inv.get('driver')}»")
    local = {}
    if local_on and (d / LOCAL).is_file():
        try:
            local = (yaml.safe_load((d / LOCAL).read_text(encoding="utf-8")) or {}).get("devices") or {}
        except yaml.YAMLError as e:
            raise ConfigError(f"{LOCAL}: {e}") from None
    local = {str(i): dict(s or {}) for i, s in local.items()}
    for i, s in local.items():
        if i in flat:
            flat[i]["settings"] = {**(flat[i].get("settings") or {}), **s}
    templates = {}
    tdir = d / "templates"
    if tdir.is_dir():
        for p in sorted(tdir.glob("*.yaml")):
            templates[p.stem] = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    runs = Path(col.get("runs_dir", "runs"))
    return Config(
        devices=flat, templates=templates, runs_dir=runs if runs.is_absolute() else REPO / runs,
        port=int(col.get("port", 8765)), preroll_s=float(col.get("preroll_s", 300)),
        preroll_fps=float(col.get("preroll_fps", 1)), push_hz=float(col.get("push_hz", 10)),
        frame_push_fps=float(col.get("frame_push_fps", 2)),
        record_default=[str(x) for x in col.get("record_default") or []],
        local=local, local_path=d / LOCAL)


def save_local(cfg: Config, dev_id, changes):
    """Запоминает найденное перебором: в памяти сразу, на диске — local.yaml."""
    cfg.local.setdefault(dev_id, {}).update(changes)
    if dev_id in cfg.devices:
        cfg.devices[dev_id]["settings"] = {**(cfg.devices[dev_id].get("settings") or {}), **changes}
    if cfg.local_path is None:
        return
    text = LOCAL_HEAD + yaml.safe_dump({"devices": cfg.local}, allow_unicode=True, sort_keys=True,
                                       default_flow_style=None)
    tmp = cfg.local_path.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, cfg.local_path)


def _load_plugin(path: Path):
    """Драйверы из файла рядом с конфигом (например, симуляторы в tests/stand)."""
    path = path.resolve()
    name = f"visserlab_plugin_{path.stem}_{hashlib.md5(str(path).encode()).hexdigest()[:6]}"
    if name in sys.modules:
        return
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or not path.is_file():
        raise ConfigError(f"Нет файла драйверов {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception:
        del sys.modules[name]
        raise


def code_version():
    """Коммит + признак незакоммиченных правок: какой код писал этот опыт."""
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO,
                             capture_output=True, text=True, timeout=5).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--", "visserlab", "config"], cwd=REPO,
                               capture_output=True, text=True, timeout=5).stdout.strip()
        return sha + ("-dirty" if dirty else "") if sha else "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"
