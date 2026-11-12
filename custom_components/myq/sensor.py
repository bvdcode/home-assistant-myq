from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import MyQDataUpdateCoordinator
from .entity import MyQEntity, myq_device_info
from .models import GarageDoor, MyQCamera
from .runtime import MyQConfigEntry

type ValueFn = Callable[[GarageDoor], StateType]
type ExistsFn = Callable[[GarageDoor], bool]


@dataclass(frozen=True, kw_only=True)
class MyQSensorEntityDescription(SensorEntityDescription):
    value_fn: ValueFn
    exists_fn: ExistsFn


SENSOR_DESCRIPTIONS: tuple[MyQSensorEntityDescription, ...] = (
    MyQSensorEntityDescription(
        key="battery_backup_state",
        translation_key="battery_backup_state",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda door: door.battery_backup_state,
        exists_fn=lambda door: door.battery_backup_state not in {None, "none"},
    ),
    MyQSensorEntityDescription(
        key="absolute_cycle_count",
        translation_key="absolute_cycle_count",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement="cycles",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda door: door.absolute_cycle_count,
        exists_fn=lambda door: door.absolute_cycle_count is not None,
    ),
    MyQSensorEntityDescription(
        key="service_cycle_count",
        translation_key="service_cycle_count",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement="cycles",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda door: door.service_cycle_count,
        exists_fn=lambda door: door.service_cycle_count is not None,
    ),
    MyQSensorEntityDescription(
        key="last_activation_source",
        translation_key="last_activation_source",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda door: door.last_device_activation_source,
        exists_fn=lambda door: door.last_device_activation_source is not None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MyQConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    del hass
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        KeypadSnapshotTime(coordinator, camera)
        for camera in coordinator.cameras.values()
        if camera.is_video_keypad
    )
    async_add_entities(
        MyQSensor(coordinator, door, description)
        for door in coordinator.data.values()
        for description in SENSOR_DESCRIPTIONS
        if description.exists_fn(door)
    )


class MyQSensor(MyQEntity, SensorEntity):
    entity_description: MyQSensorEntityDescription

    def __init__(
        self,
        coordinator: MyQDataUpdateCoordinator,
        door: GarageDoor,
        description: MyQSensorEntityDescription,
    ) -> None:
        super().__init__(coordinator, door)
        self.entity_description = description
        self._attr_unique_id = f"{door.serial_number}_{description.key}"

    @property
    def native_value(self) -> StateType:
        door = self.door
        if door is None:
            return None
        return self.entity_description.value_fn(door)


class KeypadSnapshotTime(CoordinatorEntity[MyQDataUpdateCoordinator], SensorEntity):
    """Time of the last locally cached Video Keypad preview."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_translation_key = "keypad_snapshot_time"

    def __init__(self, coordinator: MyQDataUpdateCoordinator, camera: MyQCamera) -> None:
        super().__init__(coordinator)
        self._serial = camera.serial_number
        self._attr_unique_id = f"{self._serial}_keypad_snapshot_time"
        self._attr_device_info = myq_device_info(
            self._serial, name=camera.name, model=camera.device_model
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, self.coordinator.snapshot_signal(self._serial), self.async_write_ha_state
            )
        )

    async def async_update(self) -> None:
        """The preview time is already cached."""

    @property
    def native_value(self) -> datetime | None:
        return self.coordinator.keypad_snapshot_times.get(self._serial)

    @property
    def available(self) -> bool:
        return super().available and self._serial in self.coordinator.cameras
