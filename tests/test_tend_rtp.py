"""Check RTP sequence tracking and receiver reports."""

import struct
from unittest.mock import MagicMock

import pytest

from custom_components.myq.tend_rtp import RtpReceiver


@pytest.fixture
def receiver() -> RtpReceiver:
    return RtpReceiver(local_ssrc=789)


def _rtp(sequence: int, ssrc: int = 123) -> bytes:
    return b"\x80\x60" + struct.pack(">HII", sequence, 1000, ssrc)


@pytest.mark.parametrize(
    ("sequences", "extended_max", "lost", "fraction"),
    [
        ((100, 101, 102), 102, 0, 0),
        ((100, 102, 101, 103), 103, 0, 0),
        ((100, 101, 101, 102), 102, -1, 0),
        ((65534, 65535, 0, 1), 65537, 0, 0),
        ((65534, 0, 65535, 1), 65537, 0, 0),
        ((65534, 65535, 0, 65535, 1), 65537, -1, 0),
        ((65534, 0, 1), 65537, 1, 64),
    ],
)
def test_receiver_report_tracks_reordered_and_duplicate_packets(
    receiver: RtpReceiver,
    sequences: tuple[int, ...],
    extended_max: int,
    lost: int,
    fraction: int,
) -> None:
    for sequence in sequences:
        receiver.observe(_rtp(sequence))
    report = receiver.report()
    assert report is not None
    assert struct.unpack_from(">I", report, 16)[0] == extended_max
    assert int.from_bytes(report[13:16], "big", signed=True) == lost
    assert report[12] == fraction


def test_receiver_report_recovers_after_late_packet_between_reports(
    receiver: RtpReceiver,
) -> None:
    for sequence in (65534, 0):
        receiver.observe(_rtp(sequence))
    first = receiver.report()
    assert first is not None
    assert int.from_bytes(first[13:16], "big", signed=True) == 1

    for sequence in (65535, 1):
        receiver.observe(_rtp(sequence))
    second = receiver.report()
    assert second is not None
    assert struct.unpack_from(">I", second, 16)[0] == 65537
    assert int.from_bytes(second[13:16], "big", signed=True) == 0
    assert second[12] == 0


def test_receiver_report_resets_for_new_source(receiver: RtpReceiver) -> None:
    for sequence in (65534, 0, 65535, 1):
        receiver.observe(_rtp(sequence))
    assert receiver.report() is not None

    for sequence in (50, 51):
        receiver.observe(_rtp(sequence, ssrc=456))
    report = receiver.report()
    assert report is not None
    assert struct.unpack_from(">I", report, 8)[0] == 456
    assert struct.unpack_from(">I", report, 16)[0] == 51
    assert int.from_bytes(report[13:16], "big", signed=True) == 0
    assert report[12] == 0


def test_receiver_report_counts_each_full_sequence_cycle_once(
    receiver: RtpReceiver,
) -> None:
    for sequence in range(65534, 131075):
        receiver.observe(_rtp(sequence % 65536))
        if sequence in (65536, 131072):
            receiver.observe(_rtp(65535))
    report = receiver.report()
    assert report is not None
    assert struct.unpack_from(">I", report, 16)[0] == 131074
    assert int.from_bytes(report[13:16], "big", signed=True) == -2
    assert report[12] == 0


def test_receiver_report_encodes_jitter_and_sender_report_timing() -> None:
    clock = MagicMock(side_effect=[2.0, 3.0, 3.0, 4.5])
    receiver = RtpReceiver(local_ssrc=789, clock=clock)
    receiver.observe(_rtp(10))
    receiver.observe(_rtp(11))
    sender_report = struct.pack(">BBHIIIIII", 0x80, 200, 6, 123, 0x12345678, 0x9ABCDEF0, 1000, 2, 0)
    receiver.receive_control(b"\x80\xca\x00\x01" + bytes(4) + sender_report)

    assert receiver.report() == (
        b"\x81\xc9"
        + struct.pack(">HII", 7, 789, 123)
        + bytes(4)
        + struct.pack(">IIII", 11, 5625, 0x56789ABC, 98304)
    )


@pytest.mark.parametrize(
    "packet",
    [b"", b"\x80\xc8", b"\x80\xc8\x00\x06" + bytes(16), b"\x40\xc8\x00\x06" + bytes(24)],
)
def test_invalid_sender_report_does_not_supply_timing(packet: bytes) -> None:
    receiver = RtpReceiver(local_ssrc=789)
    receiver.observe(_rtp(10))
    receiver.receive_control(packet)
    report = receiver.report()
    assert report is not None
    assert report[24:] == bytes(8)


def test_report_requires_media_and_bye_uses_the_receiver_identity(receiver: RtpReceiver) -> None:
    assert receiver.report() is None
    assert receiver.goodbye() == struct.pack(">BBHI", 0x81, 203, 1, 789)
