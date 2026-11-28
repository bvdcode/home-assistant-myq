"""RTP reception statistics and RTCP report encoding."""

import struct
from collections.abc import Callable
from time import monotonic

_RTP_SEQUENCE_MODULUS = 1 << 16
_VIDEO_CLOCK_RATE = 90_000


class RtpReceiver:
    """Track packet delivery and sender timing independently of network transport."""

    def __init__(self, local_ssrc: int, clock: Callable[[], float] = monotonic) -> None:
        self._local_ssrc = local_ssrc
        self._clock = clock
        self._source_ssrc: int | None = None
        self._base_seq = 0
        self._max_seq = 0
        self._cycles = 0
        self._received = 0
        self._expected_prior = 0
        self._received_prior = 0
        self._last_transit: float | None = None
        self._jitter = 0.0
        self._last_sr = 0
        self._last_sr_at = 0.0

    def observe(self, rtp: bytes) -> None:
        """Track one complete, validated RTP packet."""
        seq, timestamp, ssrc = struct.unpack_from(">HII", rtp, 2)
        if ssrc != self._source_ssrc:
            self._source_ssrc = ssrc
            self._base_seq = seq
            self._max_seq = seq
            self._cycles = 0
            self._received = 0
            self._expected_prior = 0
            self._received_prior = 0
            self._last_transit = None
            self._jitter = 0
        elif 0 < (seq - self._max_seq) % _RTP_SEQUENCE_MODULUS < _RTP_SEQUENCE_MODULUS // 2:
            if seq < self._max_seq:
                self._cycles += _RTP_SEQUENCE_MODULUS
            self._max_seq = seq
        self._received += 1
        transit = self._clock() * _VIDEO_CLOCK_RATE - timestamp
        if self._last_transit is not None:
            delta = abs(transit - self._last_transit)
            self._jitter += (delta - self._jitter) / 16
        self._last_transit = transit

    def receive_control(self, data: bytes) -> None:
        """Read sender timing from a compound RTCP packet."""
        offset = 0
        while offset + 4 <= len(data):
            size = (struct.unpack_from(">H", data, offset + 2)[0] + 1) * 4
            if data[offset] >> 6 != 2 or size < 4 or offset + size > len(data):
                return
            if data[offset + 1] == 200 and size >= 20:
                msw, lsw = struct.unpack_from(">II", data, offset + 8)
                self._last_sr = ((msw & 0xFFFF) << 16) | (lsw >> 16)
                self._last_sr_at = self._clock()
            offset += size

    def report(self) -> bytes | None:
        """Serialize the reception statistics since the previous report."""
        if self._source_ssrc is None:
            return None
        expected = self._cycles + self._max_seq - self._base_seq + 1
        lost = max(-(1 << 23), min((1 << 23) - 1, expected - self._received))
        expected_interval = expected - self._expected_prior
        lost_interval = expected_interval - (self._received - self._received_prior)
        fraction = (
            min(255, lost_interval * 256 // expected_interval)
            if expected_interval > 0 and lost_interval > 0
            else 0
        )
        self._expected_prior = expected
        self._received_prior = self._received
        report = bytearray(32)
        report[:2] = b"\x81\xc9"
        struct.pack_into(">HII", report, 2, 7, self._local_ssrc, self._source_ssrc)
        report[12] = fraction
        report[13:16] = (lost & 0xFFFFFF).to_bytes(3, "big")
        struct.pack_into(
            ">IIII",
            report,
            16,
            self._cycles + self._max_seq,
            int(self._jitter) & 0xFFFFFFFF,
            self._last_sr,
            min(int((self._clock() - self._last_sr_at) * 65536), 0xFFFFFFFF)
            if self._last_sr_at
            else 0,
        )
        return bytes(report)

    def goodbye(self) -> bytes:
        """Serialize a BYE packet identifying this receiver."""
        return struct.pack(">BBHI", 0x81, 203, 1, self._local_ssrc)
