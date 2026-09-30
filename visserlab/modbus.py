"""Modbus RTU поверх pyserial: только чтение (функция 03), с переподключением порта.

Своя реализация вместо pymodbus: протокол на 40 строк, а поведение при выдернутом
USB (закрыть порт, раз в пару секунд пробовать открыть снова) нужно своё.
"""
import struct
import time

import serial


def crc16(data: bytes) -> bytes:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return struct.pack("<H", crc)


def s16(w: int) -> int:
    return w - 0x10000 if w & 0x8000 else w


class RtuClient:
    REOPEN_EVERY_S = 2.0

    def __init__(self, port, baud=9600, timeout=0.3):
        self.port, self.baud, self.timeout = port, baud, timeout
        self.ser = None
        self.last_error = None
        self._next_open = 0.0

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
            self.last_error = f"порт: {e}"
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
