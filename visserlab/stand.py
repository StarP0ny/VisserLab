"""Правка config/devices.yaml из интерфейса: добавить, переименовать, подписать каналы, удалить.

Через ruamel.yaml: комментарии, порядок и стиль записи файла сохраняются, меняется
только то, что правили.
"""
import io
import os
import re
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap

ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")


class StandError(Exception):
    """Текст — для человека."""


def _yaml():
    y = YAML()
    y.preserve_quotes = True
    y.width = 4096
    y.indent(mapping=2, sequence=4, offset=2)
    return y


def _edit(cfg_dir, fn):
    path = Path(cfg_dir) / "devices.yaml"
    y = _yaml()
    doc = y.load(path.read_text(encoding="utf-8"))
    if doc.get("devices") is None:
        doc["devices"] = CommentedMap()
    fn(doc["devices"])
    buf = io.StringIO()
    y.dump(doc, buf)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(buf.getvalue(), encoding="utf-8")
    os.replace(tmp, path)


def _box(devs, dev_id):
    """Словарь, где лежит прибор: верхний уровень или children шлюза."""
    if dev_id in devs:
        return devs
    for v in devs.values():
        kids = v.get("children") if isinstance(v, dict) else None
        if kids and dev_id in kids:
            return kids
    raise StandError(f"Прибора «{dev_id}» нет в devices.yaml")


def _set_labels(e, labels):
    """Подписи каналов: {ключ: подпись}, пустая — убрать; остальные каналы не трогаем.
    Правим на месте, чтобы не потерять комментарии внутри channels."""
    ch = e.get("channels")
    if not isinstance(ch, dict):
        ch = CommentedMap()
    for k, v in labels.items():
        if v:
            ch[k] = v
        elif k in ch:
            del ch[k]
    if ch:
        e["channels"] = ch
    else:
        e.pop("channels", None)


def add_device(cfg_dir, dev_id, driver, name, settings, labels):
    def fn(devs):
        e = CommentedMap()
        e["driver"] = driver
        e["name"] = name
        if settings:
            s = CommentedMap(settings)
            s.fa.set_flow_style()
            e["settings"] = s
        if labels:
            e["channels"] = CommentedMap(labels)
        devs[dev_id] = e
        devs.yaml_set_comment_before_after_key(dev_id, before="\n", indent=2)
    _edit(cfg_dir, fn)


def edit_device(cfg_dir, dev_id, name=None, labels=None):
    def fn(devs):
        e = _box(devs, dev_id)[dev_id]
        if name is not None:
            if "name" in e:
                e["name"] = name
            else:
                e.insert(list(e).index("driver") + 1, "name", name)
        if labels is not None:
            _set_labels(e, labels)
    _edit(cfg_dir, fn)


def delete_device(cfg_dir, dev_id):
    _edit(cfg_dir, lambda devs: _box(devs, dev_id).pop(dev_id))
