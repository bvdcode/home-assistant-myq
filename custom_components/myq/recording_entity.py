"""Identity shared by a standalone keypad's recording entities."""

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import MyQDataUpdateCoordinator
from .entity import myq_device_info
from .models import MyQCamera


class KeypadRecordingEntity(CoordinatorEntity[MyQDataUpdateCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: MyQDataUpdateCoordinator, camera: MyQCamera, key: str) -> None:
        super().__init__(coordinator)
        self._serial = camera.serial_number
        self._attr_translation_key = f"keypad_{key}"
        self._attr_unique_id = f"{self._serial}_keypad_{key}"
        self._attr_device_info = myq_device_info(
            self._serial, name=camera.name, model=camera.device_model
        )

    @property
    def available(self) -> bool:
        camera = self.coordinator.cameras.get(self._serial)
        return super().available and camera is not None and camera.device_model == "vkp-camera"
