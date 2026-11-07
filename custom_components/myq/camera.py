"""Snapshots and live video from attached and standalone MyQ cameras."""

import asyncio
import time
from dataclasses import asdict
from functools import partial

import voluptuous as vol
from aiohttp import ClientError
from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.components.ffmpeg import get_ffmpeg_manager
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.setup import async_setup_component

from .const import DOMAIN
from .coordinator import MyQDataUpdateCoordinator
from .entity import myq_device_info
from .exceptions import MyQApiError, MyQError
from .keypad_recording import record_keypad
from .models import GarageDoor, MyQCamera
from .runtime import MyQConfigEntry
from .tend_protocol import TendCameraTarget, TendStreamError
from .tend_stream import TendLiveStream

SNAPSHOT_FRAME_INTERVAL = 5.0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MyQConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Keep attached cameras on their doors and add standalone camera devices."""
    del hass
    coordinator = entry.runtime_data.coordinator
    entities: list[MyQCameraEntity] = []
    for door in coordinator.data.values():
        if door.camera is not None:
            entities.append(MyQCameraEntity(coordinator, door.camera, door=door))
    entities.extend(MyQCameraEntity(coordinator, camera) for camera in coordinator.cameras.values())
    async_add_entities(entities)
    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        "record_keypad",
        {vol.Optional("duration"): vol.All(vol.Coerce(int), vol.Range(min=5, max=300))},
        "async_record_keypad",
    )
    platform.async_register_entity_service(
        "cancel_keypad_recording", {}, "async_cancel_keypad_recording"
    )


class MyQCameraEntity(CoordinatorEntity[MyQDataUpdateCoordinator], Camera):
    """One camera identified independently of its optional garage-door device."""

    _attr_has_entity_name = True
    _attr_frame_interval = SNAPSHOT_FRAME_INTERVAL
    _attr_translation_key = "camera"

    def __init__(
        self,
        coordinator: MyQDataUpdateCoordinator,
        camera: MyQCamera,
        *,
        door: GarageDoor | None = None,
    ) -> None:
        super().__init__(coordinator)
        Camera.__init__(self)
        self._camera_serial = camera.serial_number
        self._opener_serial: str | None = None
        if door is not None:
            self._opener_serial = door.serial_number
            self._attr_unique_id = f"{door.serial_number}_camera"
            self._attr_device_info = myq_device_info(
                door.serial_number, name=door.name, model=door.device_model
            )
        else:
            self._attr_unique_id = f"{camera.serial_number}_camera"
            self._attr_device_info = myq_device_info(
                camera.serial_number, name=camera.name, model=camera.device_model
            )
        self._record_lock = asyncio.Lock()
        self._record_task: asyncio.Task[object] | None = None
        self._last_record_started: float | None = None
        self._capture_lock = asyncio.Lock()
        self._image: bytes | None = None
        self._captured_at = 0.0
        self._live_stream: TendLiveStream | None = None
        if camera.serial_prefix == "TC":
            self._attr_supported_features = CameraEntityFeature.STREAM
            self.stream_options = {"use_wallclock_as_timestamps": True}

    @property
    def camera(self) -> MyQCamera | None:
        """Return the current camera metadata from discovery."""
        if self._opener_serial is None:
            return self.coordinator.cameras.get(self._camera_serial)
        door = self.coordinator.data.get(self._opener_serial)
        return door.camera if door is not None else None

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
        if not super().available or camera is None or camera.online is False:
            return False
        if self._opener_serial is not None:
            door = self.coordinator.data.get(self._opener_serial)
            return door is not None and door.online is not False
        return True

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

    async def stream_source(self) -> str | None:
        """Provide a local H.264 source for TC cameras."""
        camera = self.camera
        if not self.available or camera is None or camera.serial_prefix != "TC":
            return None
        if self._live_stream is None:
            self._live_stream = TendLiveStream(
                self._async_stream_target, self.coordinator.client.async_access_token
            )
        return await self._live_stream.source_url()

    async def _async_stream_target(self) -> TendCameraTarget:
        if self._opener_serial is not None:
            return TendCameraTarget(opener_serial=self._opener_serial)
        camera = self.camera
        if camera is None:
            raise MyQApiError("Camera is no longer available")
        return TendCameraTarget(
            destination=await self.coordinator.client.async_get_camera_alias(camera)
        )

    async def async_will_remove_from_hass(self) -> None:
        """Close the source before waiting for the stream reader to stop."""
        try:
            try:
                await self.async_cancel_keypad_recording()
            finally:
                if self._live_stream is not None:
                    await self._live_stream.close()
        finally:
            self._live_stream = None
            if self.stream is not None:
                await self.stream.stop()
                self.stream = None
            await super().async_will_remove_from_hass()

    async def async_record_keypad(self, duration: int | None = None) -> None:
        """Record received keypad video with the existing shared camera session."""
        camera = self.camera
        if camera is None or camera.device_model != "vkp-camera" or self._opener_serial is not None:
            raise HomeAssistantError("Select a Video Keypad camera")
        if self._record_lock.locked():
            raise HomeAssistantError("A keypad recording is already active")
        entry = self.coordinator.config_entry
        options = entry.options if entry else {}
        duration = duration if duration is not None else int(options.get("recording_duration", 30))
        if isinstance(duration, bool) or not 5 <= duration <= 300:
            raise HomeAssistantError("Recording duration must be 5 to 300 seconds")
        cooldown = int(options.get("recording_cooldown", 60))
        if (
            self._last_record_started is not None
            and time.monotonic() - self._last_record_started < cooldown
        ):
            raise HomeAssistantError("Keypad recording cooldown is active")
        self._last_record_started = time.monotonic()
        async with self._record_lock:
            self._record_task = asyncio.current_task()
            self._record_status("recording")
            try:
                if await self.stream_source() is None or self._live_stream is None:
                    raise TendStreamError("Keypad live stream is unavailable")
                if not await async_setup_component(self.hass, "ffmpeg", {}):
                    raise TendStreamError("FFmpeg setup failed")
                result = await record_keypad(
                    self._live_stream,
                    duration,
                    self.coordinator.recordings.root,
                    get_ffmpeg_manager(self.hass).binary,
                    enroll=partial(
                        self.coordinator.recordings.async_add, serial=self._camera_serial
                    ),
                )
                self._record_status("completed")
                self.hass.bus.async_fire(
                    "myq_keypad_recording_finished",
                    {"entity_id": self.entity_id, "status": "completed", **asdict(result)},
                )
            except asyncio.CancelledError:
                self._record_status("cancelled")
                self.hass.bus.async_fire(
                    "myq_keypad_recording_finished",
                    {"entity_id": self.entity_id, "status": "cancelled"},
                )
                raise
            except Exception as error:
                self._record_status("failed")
                self.hass.bus.async_fire(
                    "myq_keypad_recording_finished",
                    {
                        "entity_id": self.entity_id,
                        "status": "failed",
                        "error": type(error).__name__,
                    },
                )
                raise HomeAssistantError("Keypad recording failed") from error
            finally:
                self._record_task = None

    async def async_cancel_keypad_recording(self) -> None:
        """Cancel the recording consumer, preserving other live viewers."""
        task = self._record_task
        if task is not None and task is not asyncio.current_task():
            if not task.cancelling():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    def _record_status(self, status: str) -> None:
        self.coordinator.recordings.status[self._camera_serial] = status
        self.coordinator.async_update_listeners()
