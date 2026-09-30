"""Запись опыта на диск.

  <прибор>.csv                 скаляры: t_unix и столбцы каналов, строка на отсчёт
  <прибор>.<канал>.bin         кадры/профили подряд, сырые байты (dtype и shape — в meta.yaml)
  <прибор>.<канал>.index.csv   t_unix и номер кадра
  <прибор>.<канал>/000001.jpg  видео, + index.csv
  events.jsonl                 журнал
  meta.yaml                    снимок приборов и настроек, итоги

Если набор каналов прибора меняется посреди опыта (добавили точку замера),
начинается новый сегмент: <прибор>.2.csv и т.д. Всё пишется только дописыванием,
поэтому при падении процесса файлы остаются читаемыми.
"""
import csv
import json
from pathlib import Path

import numpy as np
import yaml


def _cell(v):
    if v is None:
        return ""
    if isinstance(v, float):
        return "" if v != v else repr(v)
    return v


class CsvStream:
    def __init__(self, path: Path, keys):
        self.path, self.keys = path, list(keys)
        self.f = open(path, "w", newline="", encoding="utf-8")
        self.w = csv.writer(self.f)
        self.w.writerow(["t_unix", *self.keys])
        self.rows = 0

    def write(self, t, values):
        self.w.writerow([f"{t:.3f}", *(_cell(values.get(k)) for k in self.keys)])
        self.rows += 1

    def flush(self):
        self.f.flush()

    def close(self):
        self.f.close()

    def describe(self):
        return {"file": self.path.name, "kind": "csv", "columns": ["t_unix", *self.keys], "rows": self.rows}


class ArrayStream:
    def __init__(self, root: Path, stem, ch):
        self.data_path = root / f"{stem}.bin"
        self.index_path = root / f"{stem}.index.csv"
        self.shape, self.dtype = tuple(ch.shape), np.dtype(ch.dtype)
        self.f = open(self.data_path, "ab")
        self.idx = open(self.index_path, "w", newline="", encoding="utf-8")
        self.idx.write("t_unix,n\n")
        self.n = 0

    def write(self, t, arr):
        a = np.ascontiguousarray(arr, dtype=self.dtype)
        if a.shape != self.shape:
            raise ValueError(f"{self.data_path.name}: форма {a.shape}, ожидалась {self.shape}")
        self.f.write(a.tobytes())
        self.idx.write(f"{t:.3f},{self.n}\n")
        self.n += 1

    def flush(self):
        self.f.flush()
        self.idx.flush()

    def close(self):
        self.f.close()
        self.idx.close()

    def describe(self):
        return {"file": self.data_path.name, "kind": "array", "index": self.index_path.name,
                "dtype": self.dtype.str, "shape": list(self.shape), "frames": self.n}


class JpegStream:
    def __init__(self, folder: Path):
        self.dir = folder
        self.dir.mkdir(exist_ok=True)
        self.idx = open(self.dir / "index.csv", "a", newline="", encoding="utf-8")
        if self.idx.tell() == 0:
            self.idx.write("t_unix,file\n")
        self.n = len(list(self.dir.glob("*.jpg")))

    def write(self, t, data: bytes):
        self.n += 1
        name = f"{self.n:06d}.jpg"
        (self.dir / name).write_bytes(data)
        self.idx.write(f"{t:.3f},{name}\n")

    def flush(self):
        self.idx.flush()

    def close(self):
        self.idx.close()

    def describe(self):
        return {"file": self.dir.name + "/", "kind": "jpeg", "index": "index.csv", "frames": self.n}


class DeviceFiles:
    def __init__(self, root: Path, dev_id, channels):
        self.root, self.id = root, dev_id
        self.segment = 0
        self.closed = []            # описания закрытых сегментов
        self._open(channels)

    def _open(self, channels):
        self.segment += 1
        stem = self.id if self.segment == 1 else f"{self.id}.{self.segment}"
        scal = [c.key for c in channels if c.kind in ("scalar", "points")]
        self.csv = CsvStream(self.root / f"{stem}.csv", scal) if scal else None
        self.scalar_keys = set(scal)
        self.arrays = {c.key: ArrayStream(self.root, f"{stem}.{c.key}", c)
                       for c in channels if c.kind in ("frame", "profile")}
        self.videos = {c.key: JpegStream(self.root / f"{self.id}.{c.key}")
                       for c in channels if c.kind == "video"}

    def _streams(self):
        return [s for s in (self.csv, *self.arrays.values(), *self.videos.values()) if s]

    def write(self, t, values):
        row = {k: v for k, v in values.items() if k in self.scalar_keys}
        if row:
            self.csv.write(t, row)
        for k, s in self.arrays.items():
            if k in values:
                s.write(t, values[k])
        for k, s in self.videos.items():
            if k in values:
                s.write(t, values[k])

    def rollover(self, channels):
        for s in self._streams():
            s.close()
        self.closed.extend(s.describe() for s in self._streams())
        self._open(channels)

    def flush(self):
        for s in self._streams():
            s.flush()

    def close(self):
        for s in self._streams():
            s.close()

    def describe(self):
        return self.closed + [s.describe() for s in self._streams()]

    def rows(self):
        return sum(d.get("rows", 0) for d in self.describe())


class RunStorage:
    def __init__(self, run_dir: Path):
        self.dir = run_dir
        self.dir.mkdir(parents=True, exist_ok=False)
        self.devs: dict[str, DeviceFiles] = {}
        self.events = open(self.dir / "events.jsonl", "a", encoding="utf-8")

    def add_device(self, dev_id, channels):
        self.devs[dev_id] = DeviceFiles(self.dir, dev_id, channels)

    def write(self, dev_id, t, values):
        self.devs[dev_id].write(t, values)

    def rollover(self, dev_id, channels):
        self.devs[dev_id].rollover(channels)

    def event(self, rec):
        self.events.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def flush(self):
        for d in self.devs.values():
            d.flush()
        self.events.flush()

    def close(self):
        for d in self.devs.values():
            d.close()
        self.events.close()

    def describe(self, dev_id):
        return self.devs[dev_id].describe()

    def write_meta(self, meta):
        tmp = self.dir / "meta.yaml.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            yaml.safe_dump(meta, f, allow_unicode=True, sort_keys=False)
        tmp.replace(self.dir / "meta.yaml")
