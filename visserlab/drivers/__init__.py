"""Драйверы приборов. Импорт модуля регистрирует его драйверы в core.driver.REGISTRY."""
from . import calc, manual, pta8d08, uvc_thermal  # noqa: F401
