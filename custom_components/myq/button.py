"""Explicit keypad controls; no background camera status polling."""

from aiohttp import ClientError
from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .exceptions import MyQError
from .keypad_entity import MyQKeypadEntity
from .runtime import MyQConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MyQConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    del hass
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        MyQKeypadButton(coordinator, keypad, "refresh_power") for keypad in coordinator.keypads
    )


class MyQKeypadButton(MyQKeypadEntity, ButtonEntity):
    async def async_press(self) -> None:
        try:
            await self.coordinator.async_refresh_keypad_power(self._serial)
        except (MyQError, ClientError, TimeoutError) as error:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="keypad_power_refresh_failed"
            ) from error
