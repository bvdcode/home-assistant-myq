"""Reassemble Tend media fragments and decode their video records."""

import struct
from collections.abc import Callable

from .tend_protocol import decode_video_payload


class TendFrameAssembler:
    """Own the pending RTP fragments and emit complete H.264 records."""

    def __init__(
        self,
        aes_key: str,
        on_frame: Callable[[bytes], None],
        on_rtp: Callable[[bytes], None],
    ) -> None:
        self._aes_key = aes_key
        self._on_frame = on_frame
        self._on_rtp = on_rtp
        self._frame_number: int | None = None
        self._fragments: list[bytes] = []

    def receive(self, data: bytes) -> None:
        """Accumulate fragments and emit decoded records at the next packet boundary."""
        if len(data) < 8:
            return
        frame_number = struct.unpack_from("<I", data)[0]
        if self._frame_number is None:
            self._frame_number = frame_number
        elif frame_number != self._frame_number:
            self._flush_rtp()
            self._frame_number = frame_number
        self._fragments.append(data[8:])

    def _flush_rtp(self) -> None:
        if not self._fragments:
            return
        rtp = b"".join(self._fragments)
        self._fragments.clear()
        if len(rtp) < 12 or rtp[0] >> 6 != 2:
            return
        self._on_rtp(rtp)
        for record in decode_video_payload(rtp[12:], self._aes_key):
            self._on_frame(record)
