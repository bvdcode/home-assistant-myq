"""Check video transport routing and control packets."""

import asyncio
import struct
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from custom_components.myq.tend_media import VideoTransport, _Channel
from custom_components.myq.tend_protocol import TendCamera, VideoOffer


@pytest.fixture
def transport() -> VideoTransport:
    return VideoTransport(
        TendCamera("camera", "camera:mac", "0123456789abcdef", "192.168.1.20"),
        VideoOffer("relay.example", 30000, "0123456789abcdef", "LOG-test"),
        lambda _: None,
    )


def test_reported_transport_uses_actual_media_sender(transport: VideoTransport) -> None:
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


async def test_transport_sends_reports_and_goodbye_on_the_control_channel(
    transport: VideoTransport,
) -> None:
    media = MagicMock(spec=asyncio.DatagramTransport)
    control = MagicMock(spec=asyncio.DatagramTransport)
    media_peer = (transport.camera.local_ip, 5000)
    control_peer = (transport.camera.local_ip, 5001)
    transport.channels = [
        _Channel(media, 40000, False, peer=media_peer),
        _Channel(control, 40001, True, peer=control_peer),
    ]
    rtp = b"\x80\x60" + struct.pack(">HII", 7, 1000, 123)
    transport.on_datagram(False, struct.pack("<II", 1, 0) + rtp, media_peer)
    transport.on_datagram(False, struct.pack("<II", 2, 0) + b"next", media_peer)
    with patch(
        "custom_components.myq.tend_media.asyncio.sleep",
        new=AsyncMock(side_effect=[None, asyncio.CancelledError]),
    ) as sleep:
        await transport._report_loop()
    assert sleep.await_args_list == [call(2.0), call(2.0)]
    control.sendto.assert_called_once()
    report, peer = control.sendto.call_args.args
    assert report[:4] == b"\x81\xc9\x00\x07"
    assert struct.unpack_from(">I", report, 8)[0] == 123
    assert peer == control_peer
    media.sendto.assert_not_called()

    transport.close()
    transport.close()

    bye = b"\x81\xcb\x00\x01" + report[4:8]
    assert control.sendto.call_args_list[1:] == [call(bye, control_peer), call(bye, control_peer)]
    media.close.assert_called_once_with()
    control.close.assert_called_once_with()
