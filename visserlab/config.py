"""Конфигурация стенда: приборы (config/devices.yaml) и шаблоны опытов (config/templates/*.yaml)."""
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import drivers  # noqa: F401  регистрирует драйверы
from .core.driver import REGISTRY

REPO = Path(__file__).resolve().parents[1]
CONFIG_DIR = REPO / "config"


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


def load(config_dir=None) -> Config:
    d = Path(config_dir or CONFIG_DIR)
    path = d / "devices.yaml"
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError:
        raise ConfigError(f"Нет файла {path}") from None
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
        record_default=[str(x) for x in col.get("record_default") or []])


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
