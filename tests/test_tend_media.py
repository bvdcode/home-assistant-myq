"""Check RTP sequence tracking and receiver reports."""

import struct

import pytest

from custom_components.myq.tend_media import VideoTransport
from custom_components.myq.tend_protocol import TendCamera, VideoOffer


@pytest.fixture
def transport() -> VideoTransport:
    return VideoTransport(
        TendCamera("camera", "camera:mac", "0123456789abcdef", "192.168.1.20"),
        VideoOffer("relay.example", 30000, "0123456789abcdef", "LOG-test"),
        lambda _: None,
    )


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
    transport: VideoTransport,
    sequences: tuple[int, ...],
    extended_max: int,
    lost: int,
    fraction: int,
) -> None:
    for sequence in sequences:
        transport._observe_rtp(_rtp(sequence))
    report = transport._receiver_report()
    assert report is not None
    assert struct.unpack_from(">I", report, 16)[0] == extended_max
    assert int.from_bytes(report[13:16], "big", signed=True) == lost
    assert report[12] == fraction


def test_receiver_report_recovers_after_late_packet_between_reports(
    transport: VideoTransport,
) -> None:
    for sequence in (65534, 0):
        transport._observe_rtp(_rtp(sequence))
    first = transport._receiver_report()
    assert first is not None
    assert int.from_bytes(first[13:16], "big", signed=True) == 1

    for sequence in (65535, 1):
        transport._observe_rtp(_rtp(sequence))
    second = transport._receiver_report()
    assert second is not None
    assert struct.unpack_from(">I", second, 16)[0] == 65537
    assert int.from_bytes(second[13:16], "big", signed=True) == 0
    assert second[12] == 0


def test_receiver_report_resets_for_new_source(transport: VideoTransport) -> None:
    for sequence in (65534, 0, 65535, 1):
        transport._observe_rtp(_rtp(sequence))
    assert transport._receiver_report() is not None

    for sequence in (50, 51):
        transport._observe_rtp(_rtp(sequence, ssrc=456))
    report = transport._receiver_report()
    assert report is not None
    assert struct.unpack_from(">I", report, 8)[0] == 456
    assert struct.unpack_from(">I", report, 16)[0] == 51
    assert int.from_bytes(report[13:16], "big", signed=True) == 0
    assert report[12] == 0


def test_receiver_report_counts_each_full_sequence_cycle_once(
    transport: VideoTransport,
) -> None:
    for sequence in range(65534, 131075):
        transport._observe_rtp(_rtp(sequence % 65536))
        if sequence in (65536, 131072):
            transport._observe_rtp(_rtp(65535))
    report = transport._receiver_report()
    assert report is not None
    assert struct.unpack_from(">I", report, 16)[0] == 131074
    assert int.from_bytes(report[13:16], "big", signed=True) == -2
    assert report[12] == 0


def test_reported_transport_uses_actual_media_sender(transport: VideoTransport) -> None:
    from unittest.mock import MagicMock

    transport._relay_ip = "203.0.113.8"
    transport.channels = [MagicMock(), MagicMock()]
    assert transport.media_path == "unknown"
    transport.on_datagram(False, bytes(8), ("198.51.100.9", 5001))
    assert transport.media_path == "unknown"
    transport.on_datagram(False, bytes(8), (transport.camera.local_ip, 5001))
    assert transport.media_path == "lan"
    transport.on_datagram(False, bytes(8), (transport._relay_ip, 5001))
    assert transport.media_path == "cloud_relay"
    transport._camera_ips.add("198.51.100.9")
    transport.on_datagram(False, bytes(8), ("198.51.100.9", 5001))
    assert transport.media_path == "p2p"
