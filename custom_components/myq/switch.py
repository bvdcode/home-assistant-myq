from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .opener_settings import OpenerSetting
from .runtime import MyQConfigEntry
from .setting_entity import MyQSettingEntity, add_setting_entities

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MyQConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Register the opener switches supported by myQ."""
    add_setting_entities(
        entry,
        async_add_entities,
        (OpenerSetting.LOCK_MODE, OpenerSetting.MOTION_LIGHT),
        MyQSettingSwitch,
    )


class MyQSettingSwitch(MyQSettingEntity, SwitchEntity):
    """Configure remote lockout or motion-activated lighting."""

    @property
    def is_on(self) -> bool | None:
        """Return the reported switch state."""
        value = self.setting_value
        return value if isinstance(value, bool) else None

    async def async_turn_on(self, **kwargs: object) -> None:
        """Enable the setting."""
        await self.async_write_setting(True)

    async def async_turn_off(self, **kwargs: object) -> None:
        """Disable the setting."""
        await self.async_write_setting(False)
