"""USB CDC / UART gateway for SensorsMotherboard protocol v1."""
from __future__ import annotations

import queue
import struct
import threading
import time

import serial

from ..core.driver import Channel, Driver, DriverError, Field, Found, register
from ..gwproto import EPOCH_UNIX_S, UTC_THRESHOLD_US, Frame, Parser, Type, samples, values


def utc_us():
    return time.time_ns() // 1000 - EPOCH_UNIX_S * 1_000_000


class Link:
    """One reader owns parsing; a lock serializes commands and automatic PONGs."""
    def __init__(self, port, baud=460800):
        self.serial = serial.serial_for_url(port, baudrate=int(baud), timeout=0.02, write_timeout=1)
        self.parser = Parser()
        self.sequence = 0
        self.last_sequence = None
        self.lost_frames = 0
        self.lock = threading.Lock()
        self.pending = {}
        self.events = queue.Queue(maxsize=1024)
        self.failure = None
        self.stopping = threading.Event()
        self.last_rx = time.monotonic()
        self.thread = threading.Thread(target=self._read, name="vgw-reader", daemon=True)
        self.thread.start()

    def send(self, kind, payload=b"", response=None):
        with self.lock:
            seq = self.sequence
            self.sequence = (seq + 1) & 0xFFFFFFFF
            if response is not None:
                self.pending[seq] = response
            try:
                frame = Frame(kind, seq, utc_us(), payload)
                self.serial.write(frame.encode())
            except Exception:
                self.pending.pop(seq, None)
                raise
            return seq

    def request(self, kind, payload=b"", expected=Type.RESULT, timeout=2):
        answer = queue.Queue(maxsize=1)
        seq = self.send(kind, payload, response=answer)
        try:
            frame, received = answer.get(timeout=timeout)
            if isinstance(frame, Exception):
                raise DriverError(str(frame))
            if frame.type == Type.RESULT:
                if len(frame.payload) != 6:
                    raise DriverError("Неверная длина RESULT")
                code, = struct.unpack_from("<H", frame.payload, 4)
                if code:
                    raise DriverError(f"Шлюз отклонил команду {kind:#x}: код {code}")
            if frame.type != expected:
                raise DriverError(f"Неожиданный ответ шлюза: {frame.type:#x}")
            return frame, received
        except queue.Empty:
            raise DriverError("Шлюз: нет ответа на команду") from None
        finally:
            with self.lock:
                self.pending.pop(seq, None)

    def _dispatch(self, frame):
        received = utc_us()
        if self.last_sequence is not None and frame.type != Type.HELLO:
            gap = (frame.sequence - self.last_sequence - 1) & 0xFFFFFFFF
            if gap < 0x80000000:
                self.lost_frames += gap
        self.last_sequence = frame.sequence
        if frame.type == Type.PING and not frame.payload:
            self.send(Type.PONG, struct.pack("<I", frame.sequence))
            return
        if frame.type in (Type.HELLO, Type.ENUM, Type.CONFIG, Type.RESULT, Type.TIME_SYNC_RESP) and len(frame.payload) >= 4:
            req, = struct.unpack_from("<I", frame.payload)
            with self.lock:
                waiter = self.pending.get(req)
            if waiter is not None:
                try:
                    waiter.put_nowait((frame, received))
                except queue.Full:
                    pass
                return
        try:
            self.events.put_nowait((frame, received))
        except queue.Full:
            raise DriverError("Шлюз: переполнена очередь данных на ПК")

    def _read(self):
        try:
            while not self.stopping.is_set():
                data = self.serial.read(self.serial.in_waiting or 1)
                now = time.monotonic()
                if data:
                    self.last_rx = now
                    frames = self.parser.feed(data)
                elif self.parser.buffer and now - self.last_rx > 0.25:
                    frames = self.parser.expire()
                else:
                    frames = []
                for frame in frames:
                    self._dispatch(frame)
        except Exception as exc:
            self.failure = exc
            with self.lock:
                waiters = list(self.pending.values())
            for waiter in waiters:
                try:
                    waiter.put_nowait((exc, None))
                except queue.Full:
                    pass

    def hello(self):
        frame, _ = self.request(Type.HELLO_REQ, struct.pack("<H", 1), Type.HELLO)
        if len(frame.payload) != 38 or struct.unpack_from("<H", frame.payload, 4)[0] != 1:
            raise DriverError("Несовместимая версия протокола шлюза")
        return frame

    def enumerate(self):
        frame, _ = self.request(Type.ENUM_REQ, expected=Type.ENUM)
        if len(frame.payload) < 6:
            raise DriverError("Неверный ответ ENUM")
        count, = struct.unpack_from("<H", frame.payload, 4)
        if len(frame.payload) != 6 + 16 * count:
            raise DriverError("Неверная длина ENUM")
        return {rec[0]: rec for rec in (struct.unpack_from("<HHBBBBIHH", frame.payload, 6 + i * 16) for i in range(count))}

    def sync(self, probes=5):
        best = None
        for _ in range(probes):
            frame, t4 = self.request(Type.TIME_SYNC_REQ, expected=Type.TIME_SYNC_RESP)
            if len(frame.payload) != 20:
                raise DriverError("Неверный ответ синхронизации времени")
            _, t1, m2 = struct.unpack("<IQQ", frame.payload)
            m3 = frame.time
            delay = (t4 - t1) - (m3 - m2)
            if delay < 0 or m3 < m2:
                continue
            offset = ((t1 - m2) + (t4 - m3)) // 2
            if best is None or delay < best[0]:
                best = delay, offset
        if best is None:
            raise DriverError("Не удалось оценить задержку синхронизации")
        self.request(Type.TIME_SYNC_SET, struct.pack("<q", best[1]))
        return best

    def close(self):
        self.stopping.set()
        self.thread.join(timeout=1.2)
        self.serial.close()


@register
class Gateway(Driver):
    type_id = "vgw"
    title = "SensorsMotherboard"
    model = "CH32V303 / протокол v1"
    group = "gateway"
    settings = [Field("port", "Порт", "port", ""),
                Field("baud", "Скорость UART", "number", 460800, min=9600, max=3000000),
                Field("ping_ms", "Период пингов", "number", 1000, unit="мс", min=100, max=60000),
                Field("missed_pings", "Пропущенных пингов", "number", 1, min=1, max=100),
                Field("tx_interval_us", "Интервал передачи", "number", 0, unit="мкс", min=0, max=1000000,
                      hint="0 — отправлять сразу после получения измерения."),
                Field("sync_interval_ms", "Период синхронизации", "number", 30000, unit="мс", min=0, max=3600000,
                      hint="0 — только при подключении; остальные значения от 1000 мс.")]

    def __init__(self, *args):
        super().__init__(*args)
        self.kids = {}
        self.link = None

    def attach(self, child):
        sensor = int(child.cfg["sensor_id"])
        if sensor in self.kids:
            raise DriverError("Один ID датчика назначен двум приборам")
        self.kids[sensor] = child

    @classmethod
    def discover(cls, cfg, children=None):
        link = None
        try:
            link = Link(cfg["port"], cfg.get("baud", 460800))
            link.hello()
            descriptors = link.enumerate()
            wanted = {int(c.get("settings", {}).get("sensor_id", 1 if c.get("driver") == "scd41" else 2))
                      for c in (children or {}).values()}
            if wanted:
                link.request(Type.START, struct.pack("<H", len(wanted)) +
                             b"".join(struct.pack("<H", i) for i in sorted(wanted)))
                seen = set()
                deadline = time.monotonic() + 7
                while wanted - seen and time.monotonic() < deadline:
                    if link.failure:
                        raise DriverError(str(link.failure))
                    try:
                        frame, _ = link.events.get(timeout=0.05)
                    except queue.Empty:
                        continue
                    if frame.type == Type.DATA:
                        seen.update(i for i, _, _ in samples(frame))
                link.request(Type.STOP, struct.pack("<H", 0))
                descriptors = link.enumerate()
            ids = [i for i, c in (children or {}).items()
                   if (rec := descriptors.get(int(c.get("settings", {}).get("sensor_id", 1 if c.get("driver") == "scd41" else 2)))) and rec[7]]
            return Found(True, "Подключён; датчики подтверждаются измерением", ids)
        except (serial.SerialException, DriverError, ValueError) as exc:
            return Found(False, str(exc))
        finally:
            if link:
                link.close()

    def open(self):
        self.link = Link(self.cfg["port"], self.cfg["baud"])
        try:
            self.link.hello()
            settings = [(1, int(self.cfg["ping_ms"])), (2, int(self.cfg["missed_pings"])),
                        (3, int(self.cfg["tx_interval_us"])), (4, int(self.cfg["sync_interval_ms"]))]
            self.link.request(Type.SET_CONFIG, struct.pack("<HH", 0, len(settings)) +
                              b"".join(struct.pack("<HI", *v) for v in settings))
            self.link.sync()
            descriptors = self.link.enumerate()
            for sensor, child in self.kids.items():
                if sensor not in descriptors or descriptors[sensor][1] != child.model_id:
                    raise DriverError(f"Датчик ID {sensor}: модель не совпадает с конфигурацией")
            sensor_ids = list(self.kids)
            if sensor_ids:
                self.link.request(Type.START, struct.pack("<H", len(sensor_ids)) +
                                  b"".join(struct.pack("<H", i) for i in sensor_ids))
            self.ctx.online(True)
        except Exception:
            self.link.close()
            self.link = None
            raise

    def run(self, stop):
        sync_period = float(self.cfg["sync_interval_ms"]) / 1000
        next_sync = time.monotonic() + sync_period if sync_period else float("inf")
        while not stop.is_set():
            if self.link.failure:
                raise DriverError(str(self.link.failure))
            if time.monotonic() - self.link.last_rx > max(2, float(self.cfg["ping_ms"]) / 1000 * 2):
                raise DriverError("Нет пингов от шлюза")
            if time.monotonic() >= next_sync:
                self.link.sync()
                next_sync = time.monotonic() + sync_period
            try:
                frame, received = self.link.events.get(timeout=0.05)
            except queue.Empty:
                continue
            if frame.type == Type.DATA:
                for sensor, timestamp, words in samples(frame):
                    child = self.kids.get(sensor)
                    if child is None:
                        continue
                    # open() synchronizes before START; a pre-sync queued frame uses receipt time.
                    t = EPOCH_UNIX_S + timestamp / 1e6 if timestamp >= UTC_THRESHOLD_US else EPOCH_UNIX_S + received / 1e6
                    self.ctx.emit(values(child.model_id, words), t, dev=child.id)
            elif frame.type == Type.EVENT and len(frame.payload) == 4:
                sensor, error = struct.unpack("<HH", frame.payload)
                if child := self.kids.get(sensor):
                    self.ctx.online(False, f"Ошибка датчика: {error}", dev=child.id)

    def close(self):
        if self.link:
            try:
                self.link.request(Type.STOP, struct.pack("<H", 0), timeout=0.5)
            except (DriverError, serial.SerialException):
                pass
            finally:
                self.link.close()
                self.link = None


@register
class SCD41(Driver):
    type_id = "scd41"
    title = model = "SCD41"
    model_id = 1
    group = "child"
    icon = "gas"
    settings = [Field("sensor_id", "ID датчика", "number", 1, min=1, max=2)]

    def channels(self):
        return [Channel("co2", "CO₂", unit="ppm", rate=0.2, dp=0),
                Channel("t", "T", unit="°C", rate=0.2), Channel("rh", "RH", unit="%", rate=0.2)]


@register
class SHT41(Driver):
    type_id = "sht41"
    title = model = "SHT41"
    model_id = 2
    group = "child"
    icon = "drop"
    settings = [Field("sensor_id", "ID датчика", "number", 2, min=1, max=2)]

    def channels(self):
        return [Channel("t", "T", unit="°C", rate=1), Channel("rh", "RH", unit="%", rate=1)]
