"""Explicit actions for a standalone Video Keypad's local recorder."""

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .recording_entity import KeypadRecordingEntity
from .runtime import MyQConfigEntry


async def async_setup_entry(
    hass: HomeAssistant, entry: MyQConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        KeypadRecordingButton(coordinator, camera, key)
        for camera in coordinator.cameras.values()
        if camera.device_model == "vkp-camera"
        for key in ("record", "cancel_recording")
    )


class KeypadRecordingButton(KeypadRecordingEntity, ButtonEntity):
    async def async_press(self) -> None:
        target = er.async_get(self.hass).async_get_entity_id(
            "camera", DOMAIN, f"{self._serial}_camera"
        )
        if target is None:
            raise HomeAssistantError("Keypad camera is unavailable")
        service = (
            "record_keypad"
            if self.translation_key == "keypad_record"
            else "cancel_keypad_recording"
        )
        await self.hass.services.async_call(
            DOMAIN, service, {"entity_id": target}, blocking=True, context=self._context
        )
