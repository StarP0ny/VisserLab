import struct
import zlib

import pytest

from visserlab.gwproto import Frame, Parser, Type, samples, values


@pytest.mark.parametrize("payload", [b"", b"\x00VSLBBLSV", bytes(range(256)) * 4])
def test_fragmented_coalesced_frames(payload):
    first = Frame(Type.DATA, 0xFFFFFFFF, 12345, payload)
    second = Frame(Type.PING, 0, 98765)
    parser, got = Parser(), []
    for byte in b"junkVSL" + first.encode() + second.encode():
        got += parser.feed(bytes([byte]))
    assert got == [first, second]


def test_crc_header_and_length_recovery():
    good = Frame(Type.PING, 42, 100)
    bad = bytearray(good.encode())
    bad[8] ^= 1
    parser = Parser()
    assert parser.feed(bad + good.encode()) == [good]
    assert parser.bad_frames == 1
    invalid_length = bytearray(good.encode()[:20])
    struct.pack_into("<H", invalid_length, 18, 65535)
    assert parser.feed(invalid_length + good.encode()) == [good]
    truncated = Frame(Type.DATA, 1, 1, bytes(1000)).encode()[:20]
    assert parser.feed(truncated + good.encode()) == []
    assert parser.expire() == [good]


def test_crc_known_vector():
    assert zlib.crc32(b"123456789") == 0xCBF43926
    frame = Frame(Type.DATA, 1, 2, b"abc").encode()
    assert struct.unpack_from("<I", frame, 23)[0] == zlib.crc32(frame[4:23])


def test_mixed_sensor_batch():
    payload = struct.pack("<H", 2)
    payload += struct.pack("<HIHHHH", 1, 0, 6, 600, 26000, 30000)
    payload += struct.pack("<HIHHH", 2, 3040, 4, 25000, 31000)
    records = samples(Frame(Type.DATA, 1, 1000000, payload))
    assert records == [(1, 1000000, (600, 26000, 30000)), (2, 1003040, (25000, 31000))]
    assert values(1, records[0][2])["co2"] == 600
    assert values(2, (0, 0))["rh"] == 0
    assert values(2, (65535, 65535))["rh"] == 100
    with pytest.raises(ValueError):
        samples(Frame(Type.DATA, 1, 1, payload[:-1]))
    with pytest.raises(ValueError):
        samples(Frame(Type.DATA, 1, 1, payload + b"\x00"))


def test_driver_registration():
    from visserlab import drivers  # noqa: F401
    from visserlab.core.driver import REGISTRY
    assert REGISTRY["vgw"].group == "gateway"
    assert REGISTRY["scd41"].group == REGISTRY["sht41"].group == "child"


def test_exchange_trace_keeps_exact_wire_and_is_bounded():
    import threading
    from collections import deque
    from visserlab.drivers.vgw import Link
    link = Link.__new__(Link)
    link.trace_lock = threading.Lock()
    link.trace = deque(maxlen=512)
    link.trace_sequence = 0
    link.lost_frames = 3
    link.parser = Parser()
    link.failure = None
    for seq in range(600):
        frame = Frame(Type.PING, seq, 123)
        link._trace("RX", frame)
    snapshot = link.trace_snapshot()
    assert len(snapshot["rows"]) == 512 and snapshot["omitted"] == 88
    assert bytes.fromhex(snapshot["rows"][-1]["hex"]) == frame.encode()
    assert snapshot["rows"][-1]["direction"] == "RX"
    assert snapshot["rows"][-1]["type"] == "PING"
    assert snapshot["lost_frames"] == 3
    assert link.trace_snapshot(after=snapshot["cursor"])["rows"] == []
