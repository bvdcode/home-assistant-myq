from collections.abc import Awaitable, Callable
from typing import Any, Literal

from aiohttp import ClientError
from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .entity import MyQEntity
from .exceptions import MyQApiError, MyQError
from .models import GarageDoor
from .runtime import MyQConfigEntry

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MyQConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    del hass
    coordinator = entry.runtime_data.coordinator
    async_add_entities(MyQGarageDoor(coordinator, door) for door in coordinator.data.values())


class MyQGarageDoor(MyQEntity, CoverEntity):
    _attr_device_class = CoverDeviceClass.GARAGE
    _attr_supported_features = CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE
    _attr_translation_key = "garage_door"

    @property
    def is_closed(self) -> bool | None:
        if self.coordinator.command_motion(self._serial_number) is not None:
            return False
        door = self.door
        if door is None:
            return None
        return door.is_closed

    @property
    def is_opening(self) -> bool:
        motion = self.coordinator.command_motion(self._serial_number)
        if motion is not None:
            return motion == "opening"
        door = self.door
        return door is not None and door.is_opening

    @property
    def is_closing(self) -> bool:
        motion = self.coordinator.command_motion(self._serial_number)
        if motion is not None:
            return motion == "closing"
        door = self.door
        return door is not None and door.is_closing

    async def async_open_cover(self, **kwargs: Any) -> None:
        del kwargs
        await self._async_command(self.coordinator.client.async_open_door, "open")

    async def async_close_cover(self, **kwargs: Any) -> None:
        del kwargs
        await self._async_command(self.coordinator.client.async_close_door, "closed")

    async def _async_command(
        self,
        command: Callable[[GarageDoor], Awaitable[None]],
        target_state: Literal["open", "closed"],
    ) -> None:
        try:
            door = self._required_door()
            await command(door)
        except (ClientError, MyQError) as error:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
            ) from error
        self.coordinator.async_schedule_command_updates(door.serial_number, target_state)

    def _required_door(self) -> GarageDoor:
        door = self.door
        if door is None:
            raise MyQApiError("The garage door is unavailable")
        return door
