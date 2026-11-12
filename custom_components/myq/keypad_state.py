"""Local-only keypad diagnostics; reading these values never performs I/O."""

from __future__ import annotations

import math
import time
from collections.abc import Mapping
from dataclasses import asdict, dataclass

POWER_MAX_AGE = 12 * 60 * 60


@dataclass(frozen=True, slots=True)
class KeypadPower:
    sampled_at: float
    battery_percent: float | None
    sleep_mode: str | None

    @classmethod
    def from_device(cls, device: Mapping[str, object]) -> KeypadPower:
        status = device.get("status")
        power = status.get("pwr") if isinstance(status, dict) else None
        if not isinstance(power, dict):
            raise ValueError("Keypad response contains no power report")
        battery = power.get("battLv")
        level = (
            float(battery)
            if isinstance(battery, int | float)
            and not isinstance(battery, bool)
            and 0 <= battery <= 100
            and math.isfinite(battery)
            else None
        )
        mode = power.get("sleepMode")
        return cls(
            time.time(),
            level,
            mode if isinstance(mode, str) and mode in {"FP", "LPDS"} else None,
        )

    @classmethod
    def from_storage(cls, data: Mapping[str, object]) -> KeypadPower | None:
        sampled = data.get("sampled_at")
        if (
            not isinstance(sampled, int | float)
            or isinstance(sampled, bool)
            or sampled <= 0
            or sampled > time.time() + 60
            or not math.isfinite(sampled)
        ):
            return None
        value = cls.from_device(
            {
                "status": {
                    "pwr": {
                        "battLv": data.get("battery_percent"),
                        "sleepMode": data.get("sleep_mode"),
                    }
                }
            }
        )
        return cls(float(sampled), value.battery_percent, value.sleep_mode)

    @property
    def fresh(self) -> bool:
        return 0 <= time.time() - self.sampled_at < POWER_MAX_AGE

    def as_dict(self) -> dict[str, float | str | None]:
        return asdict(self)


@dataclass(slots=True)
class KeypadState:
    """Shared by the camera, diagnostic entities and explicit user actions."""

    power: KeypadPower | None = None
    phase: str = "idle"
    transport: str = "idle"
    last_transport: str | None = None
    active_consumers: int = 0
    session_active: bool = False
    session_errors: int = 0
    credential_renewals: int = 0
    first_frame_seconds: float | None = None
    last_error: str | None = None
    last_failure: str | None = None
    failure_at: float | None = None

    def stream_event(self, event: str, value: str | float | int | None) -> None:
        if event == "start":
            self.phase = "connecting"
            self.transport = "unknown"
            self.session_active = False
            self.last_error = None
            self.first_frame_seconds = None
        elif event == "first_frame" and isinstance(value, float):
            self.first_frame_seconds = value
            self.phase = "streaming"
            self.session_active = True
        elif event == "transport" and isinstance(value, str):
            self.transport = self.last_transport = value
        elif event == "consumers" and isinstance(value, int):
            self.active_consumers = value
        elif event == "error" and isinstance(value, str) and self.last_error is None:
            self.session_active = False
            self.phase = "error"
            self.transport = "idle"
            self.last_failure = self.last_error = value
            self.failure_at = time.time()
            self.session_errors += 1
        elif event == "end":
            self.transport = "idle"
            self.session_active = False
            if self.last_error is None:
                self.phase = "idle"
