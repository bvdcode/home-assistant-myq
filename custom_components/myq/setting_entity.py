from collections.abc import Callable

from aiohttp import ClientError
from homeassistant.const import EntityCategory
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .entity import MyQEntity
from .exceptions import MyQError
from .models import GarageDoor
from .opener_settings import OpenerSetting
from .runtime import MyQConfigEntry
from .settings_coordinator import OpenerSettingsCoordinator, SettingKey


class MyQSettingEntity(MyQEntity):
    """Attach a confirmed setting to its opener and track configuration updates."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self, settings: OpenerSettingsCoordinator, door: GarageDoor, setting: OpenerSetting
    ) -> None:
        super().__init__(settings.doors, door)
        self._settings = settings
        self.setting = setting
        self._attr_unique_id = f"{door.serial_number}_{setting.value}"
        self._attr_translation_key = setting.value

    async def async_added_to_hass(self) -> None:
        """Listen to device availability and configuration readback."""
        await super().async_added_to_hass()
        self.async_on_remove(self._settings.async_add_listener(self.async_write_ha_state))

    @property
    def setting_value(self) -> int | bool | None:
        """Read remote lock mode from regular discovery and other settings from their endpoints."""
        value = self._settings.data.get((self._serial_number, self.setting))
        if self.setting is OpenerSetting.LOCK_MODE and value is not None:
            return self.door.in_vacation_mode if self.door is not None else None
        return value

    @property
    def available(self) -> bool:
        """Require a reachable opener and a supported setting."""
        return super().available and self.setting_value is not None

    async def async_update(self) -> None:
        """Refresh this setting on an explicit entity update."""
        if (door := self.door) is not None:
            await self._settings.async_readback(door, self.setting)

    async def async_write_setting(self, value: int | bool) -> None:
        """Send the device setting and report a service error if it failed."""
        door = self.door
        if door is None or not self.available:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="command_failed")
        try:
            await self._settings.async_write(door, self.setting, value)
        except (MyQError, ClientError, ValueError, TimeoutError) as error:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="command_failed"
            ) from error


@callback
def add_setting_entities(
    entry: MyQConfigEntry,
    add: AddConfigEntryEntitiesCallback,
    supported: tuple[OpenerSetting, ...],
    entity_type: Callable[[OpenerSettingsCoordinator, GarageDoor, OpenerSetting], MyQSettingEntity],
) -> None:
    """Register each setting once when its value is first reported."""
    settings = entry.runtime_data.settings
    registered: set[SettingKey] = set()

    @callback
    def discover() -> None:
        entities = []
        for serial, setting in settings.data.keys() - registered:
            door = settings.doors.data.get(serial)
            if setting in supported and door is not None:
                entities.append(entity_type(settings, door, setting))
                registered.add((serial, setting))
        if entities:
            add(entities)

    entry.async_on_unload(settings.async_add_listener(discover))
    discover()
