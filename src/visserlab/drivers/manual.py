"""Ручной прибор: весы, шприц-проба, линейка — отсчёт вводит человек."""
import time

from ..core.driver import Channel, Driver, DriverError, Field, fmt_num, register


@register
class Manual(Driver):
    type_id = "manual"
    title = "Ручной прибор"
    model = "ручной ввод"
    icon = "manual"
    group = "manual"
    actions = ["add"]
    settings = [
        Field("channel", "Величина", "text", "значение"),
        Field("unit", "Единица", "text", ""),
        Field("dp", "Знаков после запятой", "number", 2, min=0, max=6, step=1),
    ]

    def channels(self):
        return [Channel("v", self.cfg["channel"], "points", self.cfg["unit"], 0, dp=int(self.cfg["dp"]))]

    def action(self, name, args):
        if name != "add":
            return super().action(name, args)
        try:
            x = float(str(args["value"]).replace(",", "."))
        except (KeyError, ValueError):
            raise DriverError(f"{self.name}: нужно число") from None
        t = float(args["t"]) if args.get("t") else time.time()
        self.ctx.emit({"v": x}, t)
        unit = f" {self.cfg['unit']}" if self.cfg["unit"] else ""
        return {"kind": "manual", "text": f"{self.name}: {self.cfg['channel']} {fmt_num(x, int(self.cfg['dp']))}{unit}"}
