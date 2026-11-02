"""TLS signaling and camera offers for Tend TC cameras."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
import struct
from collections.abc import Callable
from uuid import uuid4

from homeassistant.util.ssl import client_context

from .const import TEND_PARTNER_ID
from .tend_protocol import (
    _CXS_HEADER,
    _MAX_CXS_PACKET,
    CxsPacket,
    TendCamera,
    TendStreamError,
    VideoOffer,
    encode_cxs_packet,
    load_properties,
    store_properties,
)

_LOGGER = logging.getLogger(__name__)
_LOGIN_HOST = "server.tend-us.tendplatform.com"
_LOGIN_PORT = 5104
_COMMAND_TIMEOUT = 5


class CxsConnection:
    """TLS signaling connection to the Tend camera broker."""

    def __init__(self, on_lost: Callable[[CxsConnection], None] | None = None) -> None:
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._options = bytes(16)
        self.properties: dict[str, str] = {}
        self._keepalive_task: asyncio.Task[None] | None = None
        self._read_task: asyncio.Task[None] | None = None
        self._replies: list[tuple[bytes, asyncio.Future[CxsPacket]]] = []
        self._on_lost = on_lost
        self._lost = False

    async def _connect(self, host: str) -> None:
        self.close_transport()
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(
                    host, _LOGIN_PORT, ssl=client_context(), server_hostname=_LOGIN_HOST
                ),
                10,
            )
        except (OSError, TimeoutError) as error:
            raise TendStreamError("Tend signaling connection failed") from error

    async def _send(self, packet: CxsPacket) -> None:
        if self._writer is None or self._lost:
            raise TendStreamError("Tend signaling is disconnected")
        self._writer.write(encode_cxs_packet(packet))
        async with asyncio.timeout(_COMMAND_TIMEOUT):
            await self._writer.drain()

    async def _next(self, wait_seconds: float | None = 10) -> tuple[CxsPacket, bytes]:
        reader = self._reader
        if reader is None:
            raise TendStreamError("Tend signaling is disconnected")
        try:
            async with asyncio.timeout(wait_seconds):
                header = await reader.readexactly(_CXS_HEADER)
                if header[0] != 0x41:
                    raise TendStreamError("Invalid Tend signaling packet")
                header_length, options_length = struct.unpack_from("<HH", header, 2)
                body_length = struct.unpack_from("<I", header, 7)[0]
                total = header_length + body_length
                if header_length < _CXS_HEADER + options_length or total > _MAX_CXS_PACKET:
                    raise TendStreamError("Invalid Tend signaling packet size")
                rest = await reader.readexactly(total - _CXS_HEADER)
        except (TimeoutError, asyncio.IncompleteReadError) as error:
            raise TendStreamError("Tend signaling timed out or closed") from error
        options = rest[:options_length]
        source = rest[options_length : header_length - _CXS_HEADER]
        body = rest[header_length - _CXS_HEADER :]
        return CxsPacket(
            struct.unpack_from("<H", header, 13)[0],
            body,
            options,
            source,
            struct.unpack_from("<H", header, 15)[0],
        ), body

    async def login(self, access_token: str) -> dict[str, str]:
        """Follow the front door redirect and authenticate with a broker."""
        source = store_properties(
            {
                "partner-id": TEND_PARTNER_ID,
                "CX_UNAME": "",
                "client_type": "Python myqcam",
                "sdk_version": "2.1.0.56",
                "CX_PASSWD": f"myQ.accessToken:{access_token}",
                "current_version": "5.243.1.73243",
                "os_name": "Python",
                "app-id": "com.chamberlain.android.liftmaster.myq",
                "os_version": "device-free",
            }
        )
        mode = store_properties({"CX_UNAME": "", "mode": "0"})
        login = CxsPacket(519, mode + mode, source=source)
        await self._connect(_LOGIN_HOST)
        await self._send(login)
        _, redirect_body = await self._next(5)
        redirect = load_properties(redirect_body)
        host = redirect.get("redirectHost")
        if host is None:
            host = next(
                (value.rsplit(":", 1)[0] for key, value in redirect.items() if key.isdecimal()),
                None,
            )
        if not host:
            raise TendStreamError("Tend did not return a camera broker")
        await self._connect(host)
        await asyncio.sleep(0.25)
        await self._send(login)
        for _ in range(5):
            response, body = await self._next(5)
            properties = load_properties(body)
            if "sid" in properties or "session-id" in properties:
                self._options = response.options
                self.properties = properties
                self._keepalive_task = asyncio.create_task(self._keepalive())
                self._read_task = asyncio.create_task(self._read_loop())
                return properties
        raise TendStreamError("Tend broker did not return a session")

    async def _keepalive(self) -> None:
        try:
            while True:
                await asyncio.sleep(20)
                await self._send(CxsPacket(526, options=self._options))
        except asyncio.CancelledError:
            pass
        except OSError, TendStreamError:
            _LOGGER.debug("Tend camera signaling keepalive ended")

    async def _read_loop(self) -> None:
        """Own the socket after login so broker traffic never piles up unread."""
        try:
            while True:
                packet, _ = await self._next(None)
                for prefix, reply in self._replies:
                    if not reply.done() and packet.body.startswith(prefix):
                        reply.set_result(packet)
                        break
        except OSError, TendStreamError:
            _LOGGER.debug("Tend camera signaling closed")
        finally:
            self._lost = True
            for _, reply in self._replies:
                if not reply.done():
                    reply.set_exception(TendStreamError("Tend signaling closed"))
            if self._on_lost is not None:
                self._on_lost(self)

    async def command(self, command: str, destination: str, correlation: str | None = None) -> str:
        """Send a command to a camera through the broker."""
        correlation = correlation or "LOG-" + uuid4().hex
        await self._send(
            CxsPacket(
                411,
                command.encode(),
                options=self._options,
                source=store_properties({"CorrelationID": correlation, "CX_DSTID": destination}),
            )
        )
        return correlation

    async def request(
        self, command: str, destination: str, reply_prefix: bytes, wait_seconds: float = 15
    ) -> tuple[str, CxsPacket]:
        """Send a camera command and wait for the reply that starts with reply_prefix."""
        reply: asyncio.Future[CxsPacket] = asyncio.get_running_loop().create_future()
        entry = (reply_prefix, reply)
        # Register before sending, so a fast reply cannot slip past the read loop.
        self._replies.append(entry)
        try:
            correlation = await self.command(command, destination)
            async with asyncio.timeout(wait_seconds):
                return correlation, await reply
        except TimeoutError as error:
            raise TendStreamError("Tend camera did not reply in time") from error
        finally:
            self._replies.remove(entry)

    async def aclose(self) -> None:
        """Close the socket and wait for background tasks to finish."""
        tasks = [task for task in (self._keepalive_task, self._read_task) if task is not None]
        writer = self._writer
        self.close()
        try:
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            if writer is not None:
                with contextlib.suppress(OSError, TimeoutError):
                    async with asyncio.timeout(1):
                        await writer.wait_closed()
        finally:
            if writer is not None:
                writer.transport.abort()

    def close_transport(self) -> None:
        if self._writer is not None:
            self._writer.close()
        self._writer = None
        self._reader = None

    def close(self) -> None:
        self._on_lost = None
        for task in (self._keepalive_task, self._read_task):
            if task is not None:
                task.cancel()
        self._keepalive_task = None
        self._read_task = None
        self.close_transport()


async def request_video(connection: CxsConnection, camera: TendCamera) -> VideoOffer:
    """Ask the camera for a Tend video session."""
    correlation, response = await connection.request(
        f"require-video-send|{camera.device_id}|9|",
        camera.destination,
        b"accept-video-receive|",
    )
    match = re.search(rb"rtp://([^:/]+):(\d+)", response.source)
    if match is None:
        raise TendStreamError("Tend video offer has no relay endpoint")
    return VideoOffer(match[1].decode(), int(match[2]), camera.aes_key, correlation)
