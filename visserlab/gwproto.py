"""SensorsMotherboard binary protocol v1; independent of the serial transport."""
from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from enum import IntEnum

MAGIC_START, MAGIC_END = b"VSLB", b"BLSV"
HEADER = struct.Struct("<4sIQHH")
MAX_PAYLOAD = 1024
EPOCH_UNIX_S = 946684800
UTC_THRESHOLD_US = 631152000000000  # 2020-01-01 relative to 2000


class Type(IntEnum):
    HELLO_REQ = 0x0001
    HELLO = 0x0002
    ENUM_REQ = 0x0010
    ENUM = 0x0011
    GET_CONFIG = 0x0020
    SET_CONFIG = 0x0021
    CONFIG = 0x0022
    START = 0x0030
    STOP = 0x0031
    DATA = 0x0040
    STATUS = 0x0041
    EVENT = 0x0042
    TIME_SYNC_REQ = 0x0050
    TIME_SYNC_RESP = 0x0051
    TIME_SYNC_SET = 0x0052
    LOG_INFO_REQ = 0x0060
    LOG_INFO = 0x0061
    LOG_READ = 0x0062
    LOG_DATA = 0x0063
    LOG_ACK = 0x0064
    RESULT = 0x0070
    PING = 0x0080
    PONG = 0x0081


@dataclass(frozen=True)
class Frame:
    type: int
    sequence: int
    time: int
    payload: bytes = b""

    def encode(self) -> bytes:
        if len(self.payload) > MAX_PAYLOAD:
            raise ValueError("payload exceeds 1024 bytes")
        head = HEADER.pack(MAGIC_START, self.sequence, self.time, self.type, len(self.payload))
        body = head[4:] + self.payload
        return MAGIC_START + body + struct.pack("<I", zlib.crc32(body)) + MAGIC_END


class Parser:
    def __init__(self):
        self.buffer = bytearray()
        self.bad_frames = 0

    def feed(self, data: bytes) -> list[Frame]:
        self.buffer.extend(data)
        frames = []
        while True:
            start = self.buffer.find(MAGIC_START)
            if start < 0:
                # Keep a partial start signature between serial reads.
                self.buffer[:] = self.buffer[-3:]
                break
            if start:
                del self.buffer[:start]
            if len(self.buffer) < HEADER.size:
                break
            _, seq, timestamp, kind, length = HEADER.unpack_from(self.buffer)
            if length > MAX_PAYLOAD:
                self.bad_frames += 1
                del self.buffer[0]
                continue
            size = length + 28
            if len(self.buffer) < size:
                break
            crc = struct.unpack_from("<I", self.buffer, 20 + length)[0]
            if self.buffer[24 + length:size] != MAGIC_END or crc != zlib.crc32(self.buffer[4:20 + length]):
                self.bad_frames += 1
                del self.buffer[0]
                continue
            frames.append(Frame(kind, seq, timestamp, bytes(self.buffer[20:20 + length])))
            del self.buffer[:size]
        return frames

    def expire(self) -> list[Frame]:
        """Recover later frames trapped behind a truncated candidate header."""
        if not self.buffer:
            return []
        self.bad_frames += 1
        del self.buffer[0]
        frames = self.feed(b"")
        self.buffer.clear()
        return frames


def samples(frame: Frame):
    """Return (sensor ID, timestamp, raw words), rejecting a malformed whole batch."""
    data = frame.payload
    if len(data) < 2:
        raise ValueError("missing DATA record count")
    count, = struct.unpack_from("<H", data)
    offset, records = 2, []
    for _ in range(count):
        if offset + 8 > len(data):
            raise ValueError("truncated DATA record header")
        sensor, delta, length = struct.unpack_from("<HIH", data, offset)
        offset += 8
        if length % 2 or offset + length > len(data):
            raise ValueError("invalid DATA record length")
        words = struct.unpack_from("<" + "H" * (length // 2), data, offset)
        records.append((sensor, frame.time + delta, words))
        offset += length
    if offset != len(data):
        raise ValueError("trailing DATA bytes")
    return records


def values(model: int, words: tuple[int, ...]) -> dict:
    if model == 1 and len(words) == 3:
        co2, temperature, humidity = words
        return {"co2": co2, "t": -45 + 175 * temperature / 65535, "rh": 100 * humidity / 65535}
    if model == 2 and len(words) == 2:
        temperature, humidity = words
        return {"t": -45 + 175 * temperature / 65535, "rh": max(0, min(100, -6 + 125 * humidity / 65535))}
    raise ValueError(f"unsupported model or measurement length: {model}/{len(words)}")
