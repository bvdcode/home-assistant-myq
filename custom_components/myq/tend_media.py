"""UDP connection setup, peer selection and media routing for Tend video."""

from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import logging
import secrets
import socket
import struct
from collections.abc import Callable
from dataclasses import dataclass

from .tend_frames import TendFrameAssembler
from .tend_protocol import (
    _SDNK_MAGIC,
    TendCamera,
    TendStreamError,
    VideoOffer,
    _media_id,
    _sdnk,
    parse_peer_packet,
    register_packet,
)
from .tend_rtp import RtpReceiver

_LOGGER = logging.getLogger(__name__)
_REPORT_INTERVAL = 2.0
_LAN_NETWORKS = tuple(
    ipaddress.IPv4Network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)


def _camera_lan_ip(value: str) -> str:
    try:
        address = ipaddress.IPv4Address(value)
    except ipaddress.AddressValueError as error:
        raise TendStreamError("Camera has no valid LAN IPv4 address") from error
    if not any(address in network for network in _LAN_NETWORKS):
        raise TendStreamError("Camera address is not RFC1918 LAN IPv4")
    return str(address)


@dataclass(slots=True)
class _Channel:
    transport: asyncio.DatagramTransport
    port: int
    control: bool
    peer: tuple[str, int] | None = None
    connected: bool = False


class _DatagramHandler(asyncio.DatagramProtocol):
    def __init__(self, owner: VideoTransport, control: bool) -> None:
        self.owner = owner
        self.control = control

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        self.owner.on_datagram(self.control, data, addr)

    def error_received(self, exc: Exception) -> None:
        _LOGGER.debug("Tend video UDP error: %s", type(exc).__name__)


class VideoTransport:
    """Own UDP channels, select peers and route media and control packets."""

    def __init__(
        self,
        camera: TendCamera,
        offer: VideoOffer,
        on_frame: Callable[[bytes], None],
        *,
        lan_only: bool = False,
    ) -> None:
        self.camera = camera
        self._lan_only = lan_only
        self._lan_ip = _camera_lan_ip(camera.local_ip) if lan_only else ""
        self.offer = offer
        self.channels: list[_Channel] = []
        self.local_ip = ""
        self._relay_ip = ""
        self._last_media_peer = ""
        self.media_path = "unknown"
        self._camera_ips = {camera.local_ip} if camera.local_ip else set[str]()
        self._connected = asyncio.Event()
        self._report_task: asyncio.Task[None] | None = None
        self._receiver = RtpReceiver(secrets.randbits(32))
        self._frames = TendFrameAssembler(offer.aes_key, on_frame, self._receiver.observe)

    async def _bind(self) -> None:
        loop = asyncio.get_running_loop()
        addresses = await loop.getaddrinfo(
            self.offer.relay_host,
            self.offer.relay_port,
            family=socket.AF_INET,
            type=socket.SOCK_DGRAM,
        )
        relay_ip = str(addresses[0][4][0])
        self._relay_ip = relay_ip
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.setblocking(False)
            await loop.sock_connect(probe, (self._lan_ip if self._lan_only else relay_ip, 9))
            self.local_ip = probe.getsockname()[0]
        finally:
            probe.close()
        if self._lan_only and self.local_ip == self._lan_ip:
            raise TendStreamError("Camera LAN address points to this host")
        # A channel registers with the broker and exchanges media with the camera.
        # Wildcard binding lets the kernel choose a source address for each destination.
        for _ in range(100):
            media = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            control = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                media.bind(("0.0.0.0", 0))
                media_port = media.getsockname()[1]
                if media_port == 65535:
                    media.close()
                    control.close()
                    continue
                control.bind(("0.0.0.0", media_port + 1))
                for sock, is_control in ((media, False), (control, True)):

                    def protocol_factory(control_channel: bool = is_control) -> _DatagramHandler:
                        return _DatagramHandler(self, control_channel)

                    transport, _ = await loop.create_datagram_endpoint(protocol_factory, sock=sock)
                    self.channels.append(_Channel(transport, sock.getsockname()[1], is_control))
                return
            except OSError:
                for channel in self.channels:
                    channel.transport.close()
                self.channels.clear()
                media.close()
                control.close()
        raise TendStreamError("Could not allocate Tend video UDP ports")

    def _send(self, channel: _Channel, data: bytes, peer: tuple[str, int]) -> None:
        channel.transport.sendto(data, peer)

    async def punch(self, wait_seconds: float = 8) -> None:
        """Establish media and control UDP paths to the camera."""
        await self._bind()
        relay = (self._relay_ip, self.offer.relay_port)

        async def drive() -> None:
            sequence = 0
            while not self._connected.is_set():
                for channel in self.channels:
                    if channel.peer is None:
                        self._send(
                            channel,
                            register_packet(
                                self.camera.device_id, self.local_ip, channel.port, channel.control
                            ),
                            relay,
                        )
                    elif not channel.connected:
                        media_id = _media_id(self.camera.device_id)
                        self._send(
                            channel,
                            _sdnk(3, bytes((1, sequence)) + media_id + media_id),
                            channel.peer,
                        )
                        self._send(channel, _sdnk(4, b"\x01"), channel.peer)
                sequence = min(sequence + 1, 2)
                await asyncio.sleep(0.1)

        driver = asyncio.create_task(drive())
        try:
            await asyncio.wait_for(self._connected.wait(), wait_seconds)
        except TimeoutError as error:
            raise TendStreamError("Tend video UDP connection timed out") from error
        finally:
            driver.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await driver
        self._report_task = asyncio.create_task(self._report_loop())

    def on_datagram(self, control: bool, data: bytes, remote: tuple[str, int]) -> None:
        """Dispatch packets after applying the active peer-selection policy."""
        if len(self.channels) < 2:
            return
        channel = self.channels[int(control)]
        setup = data[:4] == _SDNK_MAGIC and len(data) >= 20
        if self._lan_only and setup and data[7] == 2:
            self._select_lan_peer(channel, data, remote)
            return
        if not self._accept_remote(channel, remote):
            return
        if setup:
            self._handle_setup(channel, data, remote)
        elif control:
            self._receiver.receive_control(data)
        elif len(data) >= 8:
            if remote[0] != self._last_media_peer:
                self._last_media_peer = remote[0]
                self.media_path = self._media_path(remote[0])
            self._frames.receive(data)

    def _accept_remote(self, channel: _Channel, remote: tuple[str, int]) -> bool:
        if self._lan_only and remote != channel.peer:
            return False
        return remote[0] == self._relay_ip or remote[0] in self._camera_ips

    def _select_lan_peer(self, channel: _Channel, data: bytes, remote: tuple[str, int]) -> None:
        if (
            remote != (self._relay_ip, self.offer.relay_port)
            or channel.peer is not None
            or len(data) != 110
            or data[:7] != _SDNK_MAGIC + b"\x01\x00\x00"
            or struct.unpack_from(">I", data, 16)[0] != 90
        ):
            return
        channel.peer = next(
            (peer for peer in parse_peer_packet(data) if peer[0] == self._lan_ip), None
        )
        if channel.peer is not None:
            self._ack_peer(channel, remote)

    def _ack_peer(self, channel: _Channel, relay: tuple[str, int]) -> None:
        media_id = _media_id(self.camera.device_id)
        self._send(
            channel,
            _sdnk(100, bytes((1, int(channel.control))) + b"V" + media_id + media_id),
            relay,
        )

    def _select_announced_peer(self, peers: list[tuple[str, int]]) -> tuple[str, int] | None:
        self._camera_ips.update(address for address, _ in peers)
        private = [
            peer
            for peer in peers
            if ipaddress.ip_address(peer[0]).is_private and peer[0] != self.local_ip
        ]
        return (
            next((peer for peer in peers if peer[0] == self.camera.local_ip), None)
            or (private[0] if private else None)
            or (peers[-1] if peers else None)
        )

    def _handle_setup(self, channel: _Channel, data: bytes, remote: tuple[str, int]) -> None:
        match data[7]:
            case 2:
                if remote[0] != self._relay_ip:
                    return
                channel.peer = self._select_announced_peer(parse_peer_packet(data))
                if channel.peer is not None:
                    self._ack_peer(channel, (self._relay_ip, self.offer.relay_port))
            case 3:
                channel.peer = remote
                media_id = _media_id(self.camera.device_id)
                for sequence in range(3):
                    self._send(
                        channel, _sdnk(3, bytes((1, sequence)) + media_id + media_id), remote
                    )
            case 4:
                channel.peer = remote
                self._send(channel, _sdnk(5, data[20:21] or b"\x01"), remote)
            case 5:
                channel.peer = remote
                channel.connected = True
                if all(item.connected for item in self.channels):
                    self._connected.set()

    def _media_path(self, host: str) -> str:
        """Classify the observed media sender using authenticated camera metadata."""
        if host == self._relay_ip:
            return "cloud_relay"
        if host == self.camera.local_ip:
            address = ipaddress.ip_address(host)
            if any(address in network for network in _LAN_NETWORKS):
                return "lan"
        return "p2p"

    async def _report_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(_REPORT_INTERVAL)
                report = self._receiver.report()
                if report is not None and self.channels[1].peer is not None:
                    self._send(self.channels[1], report, self.channels[1].peer)
        except asyncio.CancelledError:
            pass

    def close(self) -> None:
        """Stop receiver reports and release every allocated UDP channel."""
        if self._report_task is not None:
            self._report_task.cancel()
            self._report_task = None
        if len(self.channels) == 2 and self.channels[1].peer is not None:
            bye = self._receiver.goodbye()
            with contextlib.suppress(OSError):
                self._send(self.channels[1], bye, self.channels[1].peer)
                self._send(self.channels[1], bye, self.channels[1].peer)
        for channel in self.channels:
            channel.transport.close()
        self.channels.clear()
