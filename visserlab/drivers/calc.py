"""Вычисляемые приборы: считают новую величину по каналам других приборов."""
import math

from ..core.driver import Channel, Driver, Field, register

MAX_SKEW_S = 5.0        # входы старше друг друга больше чем на это — не считаем


def abs_humidity(rh, t):
    """Абсолютная влажность, г/м³, по RH (%) и T (°C): давление насыщения по Магнусу."""
    e = 6.112 * math.exp(17.62 * t / (243.12 + t))
    return 216.7 * (rh / 100) * e / (273.15 + t)


@register
class AbsHumidity(Driver):
    type_id = "abs_humidity"
    title = "Абс. влажность"
    model = "вычисляемый канал"
    icon = "calc"
    group = "calc"
    settings = [
        Field("rh", "Канал RH", "text", "sht1:rh"),
        Field("t", "Канал T", "text", "sht1:t"),
        Field("formula", "Формула", "info",
              hint="ρ = 216,7 · RH/100 · 6,112·e^(17,62·T/(243,12+T)) / (273,15+T), г/м³"),
    ]

    def channels(self):
        return [Channel("rho", "ρ воды", "scalar", "г/м³", 0, dp=2)]

    def inputs(self):
        return [self.cfg["rh"], self.cfg["t"]]

    def compute(self, last):
        a, b = last.get(self.cfg["rh"]), last.get(self.cfg["t"])
        if not a or not b or a[1] is None or b[1] is None or abs(a[0] - b[0]) > MAX_SKEW_S:
            return None
        return {"rho": abs_humidity(a[1], b[1])}
