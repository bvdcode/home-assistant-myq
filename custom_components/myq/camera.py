"""Snapshots from cameras attached to MyQ garage doors."""

import asyncio
import time

from aiohttp import ClientError
from homeassistant.components.camera import Camera
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .coordinator import MyQDataUpdateCoordinator
from .entity import MyQEntity
from .exceptions import MyQError
from .models import GarageDoor, MyQCamera
from .runtime import MyQConfigEntry

SNAPSHOT_FRAME_INTERVAL = 5.0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MyQConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add cameras to their garage door devices."""
    del hass
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        MyQGarageCamera(coordinator, door)
        for door in coordinator.data.values()
        if door.camera is not None
    )


class MyQGarageCamera(MyQEntity, Camera):
    """An attached camera using the account's existing authorization."""

    _attr_frame_interval = SNAPSHOT_FRAME_INTERVAL
    _attr_translation_key = "camera"

    def __init__(self, coordinator: MyQDataUpdateCoordinator, door: GarageDoor) -> None:
        super().__init__(coordinator, door)
        Camera.__init__(self)
        self._attr_unique_id = f"{door.serial_number}_camera"
        self._capture_lock = asyncio.Lock()
        self._image: bytes | None = None
        self._captured_at = 0.0

    @property
    def camera(self) -> MyQCamera | None:
        """Return the current camera metadata from discovery."""
        return self.door.camera if self.door is not None else None

    @property
    def model(self) -> str | None:
        return self.camera.device_model if self.camera is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, str] | None:
        camera = self.camera
        if camera is None or camera.serial_prefix is None:
            return None
        return {"camera_serial_prefix": camera.serial_prefix}

    @property
    def available(self) -> bool:
        camera = self.camera
        return super().available and camera is not None and camera.online is not False

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Capture one JPEG, sharing the result with concurrent callers."""
        del width, height
        camera = self.camera
        if camera is None:
            return None
        requested_at = time.monotonic()
        async with self._capture_lock:
            if self._image is not None and self._captured_at > requested_at:
                return self._image
            try:
                self._image = await self.coordinator.client.async_get_camera_image(camera)
            except (ClientError, MyQError, TimeoutError) as error:
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key="camera_image_failed"
                ) from error
            self._captured_at = time.monotonic()
            return self._image
