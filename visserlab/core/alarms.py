"""Оповещения: пороги по каналам с выдержкой и потеря связи с приборами.

Уровни: warn — требует внимания (жёлтый), crit — ошибка (красный).
Правило из шаблона опыта:
  {channel: "pt100:T1", op: ">", value: 130, clear: 128, hold: 5, level: warn, text: "..."}
clear — порог возврата в норму (гистерезис), по умолчанию равен value.
"""
import operator

from .driver import fmt_num

OPS = {">": operator.gt, ">=": operator.ge, "<": operator.lt, "<=": operator.le}
LEVELS = ("warn", "crit")


class RuleError(ValueError):
    pass


class Rule:
    def __init__(self, d):
        try:
            self.channel = str(d["channel"])
            self.value = float(d["value"])
        except (KeyError, TypeError, ValueError):
            raise RuleError(f"правило оповещения: нужны channel и value — {d}") from None
        self.op = d.get("op", ">")
        self.level = d.get("level", "warn")
        if self.op not in OPS or self.level not in LEVELS:
            raise RuleError(f"правило оповещения {self.channel}: op из {list(OPS)}, level из {LEVELS}")
        self.clear = float(d.get("clear", self.value))
        self.hold = float(d.get("hold", 0))
        self.text = d.get("text", "")
        self.key = f"rule:{self.channel}{self.op}{self.value:g}"
        self.since = None

    def bad(self, v):
        return OPS[self.op](v, self.value)

    def good(self, v):
        return v < self.clear if self.op in (">", ">=") else v > self.clear


class Alarms:
    def __init__(self, rules, journal, describe):
        """journal(kind, text, t) — запись в журнал; describe(cid) -> (подпись, единица, dp)."""
        self.rules = {}
        for d in rules:
            r = Rule(d)
            self.rules.setdefault(r.channel, []).append(r)
        self.journal, self.describe = journal, describe
        self.active: dict[str, dict] = {}

    def feed(self, cid, t, v):
        for r in self.rules.get(cid, ()):
            if r.key in self.active:
                if r.good(v):
                    label, unit, dp = self.describe(cid)
                    self.clear(r.key, t, f"{label}: {fmt_num(v, dp)} {unit}, норма")
                continue
            if not r.bad(v):
                r.since = None
                continue
            r.since = t if r.since is None else r.since
            if t - r.since >= r.hold:
                label, unit, dp = self.describe(cid)
                text = r.text or f"{label}: {fmt_num(v, dp)} {unit} {r.op} {fmt_num(r.value)} {unit}"
                self.raise_(r.key, r.level, text, t)

    def raise_(self, key, level, text, t):
        cur = self.active.get(key)
        if cur and cur["level"] == level:
            return
        self.active[key] = {"key": key, "level": level, "text": text, "t": t}
        self.journal(level, text, t)

    def clear(self, key, t, text=None):
        if self.active.pop(key, None) is not None and text:
            self.journal("sys", text, t)

    def state(self):
        items = list(self.active.values())
        level = "crit" if any(a["level"] == "crit" for a in items) else "warn" if items else "ok"
        return {"level": level, "items": items}
