"""Keypad diagnostics read only local cache; entity updates never wake or poll it."""

from datetime import UTC, datetime

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTime
from homeassistant.helpers.typing import StateType

from .coordinator import MyQDataUpdateCoordinator
from .keypad_entity import MyQKeypadEntity
from .models import MyQCamera

KEYPAD_SENSORS = (
    "battery",
    "power_state",
    "transport",
    "power_sample_time",
    "session_state",
    "session_errors",
    "startup_time",
    "active_consumers",
    "credential_renewals",
)


ENUM_OPTIONS = {
    "power_state": ["fp", "lpds"],
    "session_state": ["idle", "connecting", "streaming", "error"],
    "transport": ["idle", "lan", "p2p", "cloud_relay"],
}


class MyQKeypadSensor(MyQKeypadEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: MyQDataUpdateCoordinator, keypad: MyQCamera, key: str) -> None:
        super().__init__(coordinator, keypad, key)
        self.key = key
        if key == "battery":
            self._attr_device_class = SensorDeviceClass.BATTERY
            self._attr_native_unit_of_measurement = PERCENTAGE
            self._attr_state_class = SensorStateClass.MEASUREMENT
        elif key == "power_sample_time":
            self._attr_device_class = SensorDeviceClass.TIMESTAMP
        elif key in ENUM_OPTIONS:
            self._attr_device_class = SensorDeviceClass.ENUM
            self._attr_options = ENUM_OPTIONS[key]
        elif key == "startup_time":
            self._attr_device_class = SensorDeviceClass.DURATION
            self._attr_native_unit_of_measurement = UnitOfTime.SECONDS

    @property
    def available(self) -> bool:
        if self.key in {"battery", "power_state"}:
            power = self.keypad_state.power
            return super().available and power is not None and power.fresh
        return super().available

    @property
    def native_value(self) -> StateType | datetime:
        state = self.keypad_state
        power = state.power
        match self.key:
            case "battery":
                return power.battery_percent if power else None
            case "power_state":
                return power.sleep_mode.lower() if power and power.sleep_mode else None
            case "power_sample_time":
                return datetime.fromtimestamp(power.sampled_at, UTC) if power else None
            case "transport":
                return None if state.transport == "unknown" else state.transport
            case "session_state":
                return state.phase
            case "session_errors":
                return state.session_errors
            case "startup_time":
                return state.first_frame_seconds
            case "active_consumers":
                return state.active_consumers
            case "credential_renewals":
                return state.credential_renewals
        return None

    @property
    def extra_state_attributes(self) -> dict[str, str | float | None] | None:
        if self.key == "transport":
            return {"last_transport": self.keypad_state.last_transport}
        if self.key == "session_errors":
            state = self.keypad_state
            return {"last_failure": state.last_failure, "failure_at": state.failure_at}
        return None
