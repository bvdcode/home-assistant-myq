from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .models import GarageDoor
from .opener_settings import LIGHT_DURATIONS, MAX_CLOSE_MINUTES, OpenerSetting
from .runtime import MyQConfigEntry
from .setting_entity import MyQSettingEntity, add_setting_entities
from .settings_coordinator import OpenerSettingsCoordinator

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MyQConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Register supported opener timer settings."""
    add_setting_entities(
        entry,
        async_add_entities,
        (OpenerSetting.TIME_TO_CLOSE, OpenerSetting.LIGHT_TIMER),
        MyQTimer,
    )


class MyQTimer(MyQSettingEntity, NumberEntity):
    """Expose the timer in the units used by the opener settings UI."""

    _attr_device_class = NumberDeviceClass.DURATION
    _attr_mode = NumberMode.BOX

    def __init__(
        self, settings: OpenerSettingsCoordinator, door: GarageDoor, setting: OpenerSetting
    ) -> None:
        super().__init__(settings, door, setting)
        if setting is OpenerSetting.TIME_TO_CLOSE:
            self._attr_native_unit_of_measurement = UnitOfTime.MINUTES
            self._attr_native_min_value = 0
            self._attr_native_max_value = MAX_CLOSE_MINUTES
            self._attr_native_step = 1
        else:
            self._attr_native_unit_of_measurement = UnitOfTime.SECONDS
            self._attr_native_min_value = min(LIGHT_DURATIONS)
            self._attr_native_max_value = max(LIGHT_DURATIONS)
            self._attr_native_step = 60

    @property
    def native_value(self) -> float | None:
        """Return the confirmed duration."""
        return self.setting_value

    async def async_set_native_value(self, value: float) -> None:
        """Apply a whole duration admitted by the opener."""
        if not float(value).is_integer():
            raise ValueError("The opener timer requires a whole number")
        await self.async_write_setting(int(value))
