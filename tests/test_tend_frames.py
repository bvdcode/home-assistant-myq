"""Frame assembly across Tend datagram boundaries."""

import struct

import pytest

from custom_components.myq.tend_frames import TendFrameAssembler


def _rtp(*frames: bytes) -> bytes:
    records = b"".join(struct.pack("<I", len(frame)) + frame for frame in frames)
    payload = b"w1" + struct.pack("<I", len(records) + 4) + bytes(4) + records
    return b"\x80\x60" + struct.pack(">HII", 7, 1000, 123) + payload


def _fragment(number: int, part: int, data: bytes) -> bytes:
    return struct.pack("<II", number, part) + data


@pytest.mark.parametrize("chunk_size", [1, 7, 12, 64])
def test_fragmented_packet_emits_all_records_once_at_the_next_boundary(chunk_size: int) -> None:
    frames: list[bytes] = []
    packets: list[bytes] = []
    assembler = TendFrameAssembler("0123456789abcdef", frames.append, packets.append)
    first = b"\x00\x00\x00\x01\x65\x88\x84"
    second = b"\x00\x00\x00\x01\x41\x01"
    rtp = _rtp(first, second)
    for part, offset in enumerate(range(0, len(rtp), chunk_size)):
        assembler.receive(_fragment(1, part, rtp[offset : offset + chunk_size]))
    assert frames == []
    assert packets == []

    following = _rtp(second)
    assembler.receive(_fragment(2, 0, following))
    assert frames == [first, second]
    assert packets == [rtp]

    assembler.receive(_fragment(3, 0, b"next"))
    assert frames == [first, second, second]
    assert packets == [rtp, following]


@pytest.mark.parametrize("invalid", [b"", bytes(11), b"\x40" + bytes(11)])
def test_invalid_packet_is_dropped_without_corrupting_the_following_frame(invalid: bytes) -> None:
    frames: list[bytes] = []
    packets: list[bytes] = []
    assembler = TendFrameAssembler("0123456789abcdef", frames.append, packets.append)
    assembler.receive(_fragment(1, 0, invalid))
    assembler.receive(b"short")
    rtp = _rtp(b"frame")
    assembler.receive(_fragment(2, 0, rtp))
    assert frames == []
    assert packets == []

    assembler.receive(_fragment(3, 0, b"next"))
    assert frames == [b"frame"]
    assert packets == [rtp]
