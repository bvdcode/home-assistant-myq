from enum import StrEnum

from .exceptions import MyQApiError


class OpenerSetting(StrEnum):
    """Account-scoped myQ opener settings and their wire values."""

    LOCK_MODE = "lockmode"
    TIME_TO_CLOSE = "timetoclose"
    LIGHT_TIMER = "lighttimer"
    MOTION_LIGHT = "worklight_settings"

    def read(self, payload: dict[str, object]) -> int | bool | None:
        """Decode an advertised setting without substituting a default value."""
        match self:
            case OpenerSetting.LIGHT_TIMER:
                value = payload.get("light_timer_setting")
                if type(value) is int and value in LIGHT_DURATIONS:
                    return value
            case OpenerSetting.TIME_TO_CLOSE:
                value = payload.get("time_to_close_setting")
                if type(value) is int and 0 <= value <= MAX_CLOSE_MINUTES * 60 and value % 60 == 0:
                    return value // 60
            case OpenerSetting.MOTION_LIGHT:
                flags = [payload.get(key) for key in ("enable_pir_control", "enable_motion_wl")]
                if all(flag is None or isinstance(flag, bool) for flag in flags):
                    if any(isinstance(flag, bool) for flag in flags):
                        return any(flags)
                    return None
            case OpenerSetting.LOCK_MODE:
                raise ValueError("Lock mode is reported in opener discovery")
        raise MyQApiError(f"Invalid myQ setting: {self.value}")

    def payload(self, value: int | bool) -> dict[str, object]:
        """Validate and convert the Home Assistant value to the device setting."""
        match self:
            case OpenerSetting.LOCK_MODE if isinstance(value, bool):
                return {"enable_lock_mode": value}
            case OpenerSetting.MOTION_LIGHT if isinstance(value, bool):
                return {"enable_pir_control": value, "enable_motion_wl": value}
            case OpenerSetting.LIGHT_TIMER if type(value) is int and value in LIGHT_DURATIONS:
                return {"light_timer_setting": value}
            case OpenerSetting.TIME_TO_CLOSE if (
                type(value) is int and 0 <= value <= MAX_CLOSE_MINUTES
            ):
                return {"time_to_close_setting": value * 60}
        raise ValueError(f"Invalid value for {self.value}")


MAX_CLOSE_MINUTES = 99
LIGHT_DURATIONS = (90, 150, 210, 270)
REMOTE_TYPES = frozenset({"OokTx", "S3Transmitter", "FhssTx"})
