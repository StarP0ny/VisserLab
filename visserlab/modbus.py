"""Modbus RTU поверх pyserial: только чтение (функция 03), с переподключением порта.

Своя реализация вместо pymodbus: протокол на 40 строк, а поведение при выдернутом
USB (закрыть порт, раз в пару секунд пробовать открыть снова) нужно своё.
"""
import re
import struct
import time

import serial
from serial.tools import list_ports


def crc16(data: bytes) -> bytes:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return struct.pack("<H", crc)


def s16(w: int) -> int:
    return w - 0x10000 if w & 0x8000 else w


def reply_timeout(baud, margin=0.03):
    """Сколько ждать начала ответа: 8 байт запроса и 3 байта ответа по 11 бит плюс запас."""
    return margin + 11 * 11 / baud


def port_error(e):
    """Причина, по которой порт не открылся, коротко: «порт: нет в системе»."""
    s = str(e)
    if "FileNotFoundError" in s or "No such file" in s:
        return "порт: нет в системе"
    if "PermissionError" in s or "Access is denied" in s or "Busy" in s:
        return "порт: занят другой программой"
    return f"порт: {e}"


def serial_ports():
    """[(порт, описание)] — что сейчас видно в системе, COM3 раньше COM26."""
    key = lambda p: [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", p.device)]
    desc = lambda p: re.sub(r"\s*\(%s\)$" % re.escape(p.device), "", p.description or "")   # «… (COM26)»
    return [(p.device, desc(p)) for p in sorted(list_ports.comports(), key=key)]


class RtuClient:
    REOPEN_EVERY_S = 2.0

    def __init__(self, port, baud=9600, timeout=0.3):
        self.port, self.baud, self.timeout = port, baud, timeout
        self.ser = None
        self.last_error = None
        self._next_open = 0.0

    def connect(self):
        """Открыть порт сейчас. False — не открылся, причина в last_error."""
        self._next_open = 0.0
        return self._ensure_open()

    def set_line(self, baud=None, timeout=None):
        """Сменить скорость и таймаут, не закрывая порт: перебор скоростей без переоткрытия."""
        if baud is not None:
            self.baud = baud
        if timeout is not None:
            self.timeout = timeout
        if self.ser is not None:
            self.ser.baudrate, self.ser.timeout = self.baud, self.timeout

    def _ensure_open(self):
        if self.ser is not None:
            return True
        now = time.monotonic()
        if now < self._next_open:
            return False
        self._next_open = now + self.REOPEN_EVERY_S
        try:
            self.ser = serial.Serial(self.port, self.baud, bytesize=8, parity="N",
                                     stopbits=1, timeout=self.timeout)
            return True
        except serial.SerialException as e:
            self.last_error = port_error(e)
            return False

    def close(self):
        if self.ser is not None:
            try:
                self.ser.close()
            except serial.SerialException:
                pass
            self.ser = None

    def read_holding(self, addr, start, count, verbose=False):
        """Список слов или None. Порт, отвалившийся посреди прогона, переоткрывается сам."""
        if not self._ensure_open():
            return None
        try:
            return self._transact(addr, start, count, verbose)
        except serial.SerialException as e:
            self.last_error = f"порт: {e}"
            self.close()
            return None

    def _transact(self, addr, start, count, verbose):
        req = struct.pack(">BBHH", addr, 0x03, start, count)
        req += crc16(req)
        self.ser.reset_input_buffer()
        self.ser.write(req)
        if verbose:
            print("  ->", req.hex(" "))

        head = self.ser.read(3)
        if len(head) < 3:
            self.last_error = "таймаут"
            return None
        if head[1] & 0x80:
            self.ser.read(2)
            self.last_error = f"exception {head[2]}"
            return None
        nbytes = head[2]
        body = self.ser.read(nbytes + 2)
        frame = head + body
        if len(body) < nbytes + 2 or crc16(frame[:-2]) != frame[-2:]:
            self.last_error = "битый кадр"
            if verbose:
                print("  <- ", frame.hex(" "), "(битый)")
            return None
        if verbose:
            print("  <-", frame.hex(" "))
        return list(struct.unpack(">%dH" % (nbytes // 2), body[:nbytes]))
