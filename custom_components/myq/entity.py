from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import MyQDataUpdateCoordinator
from .models import GarageDoor


class MyQEntity(CoordinatorEntity[MyQDataUpdateCoordinator]):
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: MyQDataUpdateCoordinator,
        door: GarageDoor,
    ) -> None:
        super().__init__(coordinator)
        self._serial_number = door.serial_number
        self._attr_unique_id = door.serial_number
        self._attr_device_info = myq_device_info(
            door.serial_number, name=door.name, model=door.device_model
        )

    @property
    def door(self) -> GarageDoor | None:
        return self.coordinator.data.get(self._serial_number)

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        door = self.door
        return door is not None and door.online is not False


def myq_device_info(serial_number: str, *, name: str | None, model: str | None) -> DeviceInfo:
    """Describe a MyQ device consistently across entity platforms."""
    return DeviceInfo(
        identifiers={(DOMAIN, serial_number)},
        manufacturer=MANUFACTURER,
        model=model,
        name=name,
        serial_number=serial_number,
    )
