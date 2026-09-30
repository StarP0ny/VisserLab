"""Буферы в памяти: история скаляров для графиков и кольцо предзаписи."""
from array import array
from bisect import bisect_left, bisect_right
from collections import deque

import numpy as np


class History:
    """Скалярный канал за весь опыт. Клиент, подключившийся посреди записи,
    получает графики отсюда, а не из файлов, в которые идёт запись."""
    __slots__ = ("t", "v")

    def __init__(self):
        self.t = array("d")
        self.v = array("d")

    def __len__(self):
        return len(self.t)

    def append(self, t, v):
        self.t.append(t)
        self.v.append(v)

    def trim_before(self, edge):
        i = bisect_left(self.t, edge)
        if i:
            del self.t[:i]
            del self.v[:i]

    def query(self, t_from=None, t_to=None, points=2000):
        """Отрезок истории. Длинный прорежается: на бакет — минимум и максимум,
        чтобы не терять пики (дыхательная волна ΔP, шипы)."""
        i0 = 0 if t_from is None else bisect_left(self.t, t_from)
        i1 = len(self.t) if t_to is None else bisect_right(self.t, t_to)
        n = i1 - i0
        if n <= max(points, 2):
            return list(self.t[i0:i1]), list(self.v[i0:i1])
        t = np.array(self.t[i0:i1])
        v = np.array(self.v[i0:i1])
        edges = np.linspace(0, n, max(1, points // 2) + 1).astype(int)
        idx = []
        for a, b in zip(edges[:-1], edges[1:]):
            if b <= a:
                continue
            lo, hi = a + int(np.argmin(v[a:b])), a + int(np.argmax(v[a:b]))
            idx.extend(sorted({lo, hi}))
        return t[idx].tolist(), v[idx].tolist()


class Ring:
    """Кольцо предзаписи: последние `horizon` секунд отсчётов одного прибора.
    Кадры прорежены до `array_fps`, скаляры идут полной частотой."""

    def __init__(self, horizon, array_fps):
        self.horizon = horizon
        self.min_dt = 1 / array_fps if array_fps > 0 else float("inf")
        self.items = deque()
        self.last_array_t = float("-inf")

    def put(self, t, values, array_keys):
        if array_keys and array_keys & values.keys():
            if t - self.last_array_t < self.min_dt:
                values = {k: v for k, v in values.items() if k not in array_keys}
            else:
                self.last_array_t = t
        if values:
            self.items.append((t, values))
        edge = t - self.horizon
        while self.items and self.items[0][0] < edge:
            self.items.popleft()

    def drain(self):
        items = list(self.items)
        self.items.clear()
        return items
