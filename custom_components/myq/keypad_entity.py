"""Shared identity for standalone keypad controls and local diagnostic entities."""

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import MyQDataUpdateCoordinator
from .entity import myq_device_info
from .keypad_state import KeypadState
from .models import MyQCamera


class MyQKeypadEntity(CoordinatorEntity[MyQDataUpdateCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: MyQDataUpdateCoordinator, keypad: MyQCamera, key: str) -> None:
        super().__init__(coordinator)
        self._serial = keypad.serial_number
        self._attr_unique_id = f"{self._serial}_keypad_{key}"
        self._attr_translation_key = f"keypad_{key}"
        self._attr_device_info = myq_device_info(
            keypad.serial_number, name=keypad.name, model=keypad.device_model
        )

    @property
    def keypad_state(self) -> KeypadState:
        return self.coordinator.keypad_state(self._serial)

    @property
    def available(self) -> bool:
        return super().available and any(
            k.serial_number == self._serial for k in self.coordinator.keypads
        )

    async def async_update(self) -> None:
        """Explicit entity updates still read cache; use the refresh-power action for I/O."""
