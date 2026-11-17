import asyncio
from dataclasses import replace
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import ClientConnectionError
from homeassistant.components.camera import CameraEntityFeature, async_get_image
from homeassistant.components.camera.const import StreamType
from homeassistant.components.camera.helper import get_camera_from_entity_id
from homeassistant.components.camera.prefs import DynamicStreamSettings
from homeassistant.components.camera.webrtc import (
    CameraWebRTCProvider,
    async_register_webrtc_provider,
)
from homeassistant.components.stream import Stream
from homeassistant.components.stream.core import STREAM_SETTINGS_NON_LL_HLS
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.myq.camera import SNAPSHOT_FRAME_INTERVAL, MyQCameraEntity
from custom_components.myq.const import (
    CONF_EMAIL,
    CONF_MFA_METHOD,
    CONF_TOKENS,
    DOMAIN,
    MFA_METHOD_EMAIL,
)
from custom_components.myq.exceptions import MyQApiError, MyQAuthenticationError
from custom_components.myq.models import GarageDoor, MyQCamera, MyQDevices
from custom_components.myq.runtime import MyQRuntimeData

EMAIL = "driver@example.com"
IMAGE = b"\xff\xd8\xff\xe0jpeg"
DOOR = GarageDoor(
    "account-1",
    "door-1",
    "Main garage",
    "Wi-Fi GDO",
    "closed",
    True,
    camera=MyQCamera("TC-0005-10000001", True, "Integrated camera"),
)


async def test_camera_returns_snapshot_for_attached_camera() -> None:
    entity, coordinator = _entity(DOOR)

    assert await entity.async_camera_image(640, 360) == IMAGE

    coordinator.client.async_get_camera_image.assert_awaited_once_with(DOOR.camera)
    assert entity.unique_id == "door-1_camera"
    assert entity.extra_state_attributes == {"camera_serial_prefix": "TC"}
    assert entity.model == "Integrated camera"
    assert entity.supported_features == CameraEntityFeature.STREAM


async def test_live_stream_is_available_only_for_tc_camera() -> None:
    tc_entity, coordinator = _entity(DOOR)
    with patch("custom_components.myq.camera.TendLiveStream") as stream_class:
        stream_class.return_value.source_url = AsyncMock(
            return_value="http://127.0.0.1:1234/test.h264"
        )
        assert await tc_entity.stream_source() == "http://127.0.0.1:1234/test.h264"
        stream_class.assert_called_once_with(
            tc_entity._async_stream_target,
            coordinator.client.async_access_token,
            lan_only=False,
            fallback_target_supplier=tc_entity._async_camera_target,
        )
        assert (await tc_entity._async_stream_target()).opener_serial == "door-1"
        coordinator.client.async_get_camera_alias.assert_not_called()

    other = replace(DOOR, camera=MyQCamera("GW-0005-10000001", True))
    other_entity, _ = _entity(other)
    assert other_entity.supported_features == 0
    assert await other_entity.stream_source() is None


async def test_live_stream_starts_fresh_after_entity_is_re_added() -> None:
    entity, _ = _entity(DOOR)
    with patch("custom_components.myq.camera.TendLiveStream") as stream_class:
        live = stream_class.return_value
        live.source_url = AsyncMock(return_value="http://127.0.0.1:1234/test.h264")
        live.close = AsyncMock()
        assert await entity.stream_source() == "http://127.0.0.1:1234/test.h264"
        ha_stream = MagicMock(stop=AsyncMock())

        # Home Assistant removes and re-adds the same entity object when its entity_id changes.
        with patch.object(entity, "stream", ha_stream):
            await entity.async_will_remove_from_hass()
            assert entity.stream is None
        ha_stream.stop.assert_awaited_once()
        live.close.assert_awaited_once()

        assert await entity.stream_source() == "http://127.0.0.1:1234/test.h264"
    assert stream_class.call_count == 2


async def test_removing_preloaded_stream_stops_worker_without_changing_preferences(
    hass: HomeAssistant,
) -> None:
    entity, _ = _entity(DOOR)
    settings = DynamicStreamSettings(preload_stream=True)
    stream = Stream(
        hass,
        "http://127.0.0.1:1234/test.h264",
        {},
        STREAM_SETTINGS_NON_LL_HLS,
        settings,
    )
    with patch.object(stream, "_run_worker", stream._thread_quit.wait):
        await stream.start()
    worker = stream._thread
    assert worker is not None and worker.is_alive()
    entity.stream = stream

    try:
        await entity.async_will_remove_from_hass()

        assert not worker.is_alive()
        assert settings.preload_stream is True
    finally:
        stream._thread_quit.set()
        await hass.async_add_executor_job(worker.join, 1)


async def test_concurrent_snapshot_requests_share_one_capture() -> None:
    entity, coordinator = _entity(DOOR)
    release = asyncio.Event()

    async def capture(camera: MyQCamera) -> bytes:
        await release.wait()
        return IMAGE

    coordinator.client.async_get_camera_image = AsyncMock(side_effect=capture)
    first = asyncio.create_task(entity.async_camera_image())
    second = asyncio.create_task(entity.async_camera_image())
    await asyncio.sleep(0)
    release.set()

    assert [await first, await second] == [IMAGE, IMAGE]
    coordinator.client.async_get_camera_image.assert_awaited_once()
    assert await entity.async_camera_image() == IMAGE
    coordinator.client.async_get_camera_image.assert_awaited_once()


async def test_snapshot_viewers_share_one_capture_per_frame_interval() -> None:
    entity, coordinator = _entity(DOOR)
    with patch("custom_components.myq.camera.time.monotonic", return_value=100) as clock:
        assert await entity.async_camera_image() == IMAGE
        clock.return_value = 100 + SNAPSHOT_FRAME_INTERVAL - 0.1
        assert await entity.async_camera_image() == IMAGE
        coordinator.client.async_get_camera_image.assert_awaited_once()

        clock.return_value = 100 + SNAPSHOT_FRAME_INTERVAL
        coordinator.client.async_get_camera_image.return_value = IMAGE + b"new"
        assert await entity.async_camera_image() == IMAGE + b"new"
        assert coordinator.client.async_get_camera_image.await_count == 2


async def test_expired_snapshot_does_not_hide_a_capture_failure() -> None:
    entity, coordinator = _entity(DOOR)
    with patch("custom_components.myq.camera.time.monotonic", return_value=100) as clock:
        assert await entity.async_camera_image() == IMAGE
        clock.return_value = 100 + SNAPSHOT_FRAME_INTERVAL
        coordinator.client.async_get_camera_image.side_effect = MyQApiError("Snapshot unavailable")
        with pytest.raises(HomeAssistantError):
            await entity.async_camera_image()

        coordinator.client.async_get_camera_image.side_effect = None
        coordinator.client.async_get_camera_image.return_value = IMAGE + b"recovered"
        assert await entity.async_camera_image() == IMAGE + b"recovered"
        assert coordinator.client.async_get_camera_image.await_count == 3


@pytest.mark.parametrize("error_type", [MyQApiError, MyQAuthenticationError, ClientConnectionError])
async def test_camera_translates_snapshot_failure(
    error_type: type[MyQApiError | MyQAuthenticationError | ClientConnectionError],
) -> None:
    entity, coordinator = _entity(DOOR)
    error = error_type("Snapshot rejected")
    coordinator.client.async_get_camera_image.side_effect = error

    with pytest.raises(HomeAssistantError) as raised:
        await entity.async_camera_image()

    assert raised.value.__cause__ is error
    assert raised.value.translation_domain == DOMAIN
    assert raised.value.translation_key == "camera_image_failed"


@pytest.mark.parametrize(
    ("door_online", "camera_online", "available"),
    [
        (True, True, True),
        (True, None, True),
        (True, False, False),
        (False, True, False),
    ],
)
def test_camera_availability_follows_door_and_camera(
    door_online: bool,
    camera_online: bool | None,
    available: bool,
) -> None:
    door = replace(DOOR, online=door_online, camera=MyQCamera("TC-0005-10000001", camera_online))
    entity, _ = _entity(door)

    assert entity.available is available


async def test_missing_door_or_camera_has_no_snapshot() -> None:
    entity, coordinator = _entity(DOOR)

    for data in ({}, {"door-1": replace(DOOR, camera=None)}):
        coordinator.data = data
        assert entity.available is False
        assert await entity.async_camera_image() is None

    coordinator.client.async_get_camera_image.assert_not_awaited()


async def test_setup_adds_camera_only_for_doors_with_cameras(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=EMAIL,
        title=EMAIL,
        data={
            CONF_EMAIL: EMAIL,
            CONF_MFA_METHOD: MFA_METHOD_EMAIL,
            CONF_TOKENS: {
                "access_token": "access",
                "refresh_token": "refresh",
                "expires_at": 9876543210.0,
            },
        },
    )
    entry.add_to_hass(hass)
    other_door = replace(DOOR, serial_number="door-2", name="Side garage", camera=None)
    client = MagicMock()
    client.async_get_devices = AsyncMock(return_value=MyQDevices((DOOR, other_door)))
    client.async_get_camera_image = AsyncMock(return_value=IMAGE)

    with patch("custom_components.myq.MyQClient", return_value=client):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    registry = er.async_get(hass)
    camera_id = registry.async_get_entity_id("camera", DOMAIN, "door-1_camera")
    assert camera_id is not None
    assert registry.async_get_entity_id("camera", DOMAIN, "door-2_camera") is None
    camera_entry = registry.async_get(camera_id)
    assert camera_entry is not None
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, "door-1")})
    assert device is not None
    assert camera_entry.device_id == device.id
    state = hass.states.get(camera_id)
    assert state is not None
    assert state.state == "idle"
    assert state.attributes["friendly_name"] == "Main garage Camera"
    assert state.attributes["camera_serial_prefix"] == "TC"
    assert state.attributes["model_name"] == "Integrated camera"

    image = await async_get_image(hass, camera_id)

    assert image.content == IMAGE
    assert image.content_type == "image/jpeg"
    client.async_get_camera_image.assert_awaited_once_with(DOOR.camera)

    runtime = cast(MyQRuntimeData, entry.runtime_data)
    client.async_get_devices.return_value = MyQDevices(
        (
            replace(DOOR, camera=MyQCamera("TC-0005-10000001", False)),
            other_door,
        )
    )
    await runtime.coordinator.async_refresh()
    await hass.async_block_till_done()

    state = hass.states.get(camera_id)
    assert state is not None
    assert state.state == STATE_UNAVAILABLE

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.parametrize(("camera_online", "opener_online"), [(False, True), (True, False)])
async def test_webrtc_is_restored_when_camera_becomes_available(
    hass: HomeAssistant,
    camera_online: bool,
    opener_online: bool,
) -> None:
    assert await async_setup_component(hass, "camera", {})
    provider = MagicMock(spec=CameraWebRTCProvider)
    provider.async_is_supported.return_value = True
    async_register_webrtc_provider(hass, provider)
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=EMAIL,
        title=EMAIL,
        data={
            CONF_EMAIL: EMAIL,
            CONF_MFA_METHOD: MFA_METHOD_EMAIL,
            CONF_TOKENS: {
                "access_token": "access",
                "refresh_token": "refresh",
                "expires_at": 9876543210.0,
            },
        },
    )
    entry.add_to_hass(hass)
    assert DOOR.camera is not None
    offline_door = replace(
        DOOR, online=opener_online, camera=replace(DOOR.camera, online=camera_online)
    )
    client = MagicMock()
    client.async_get_devices = AsyncMock(return_value=MyQDevices((offline_door,)))

    with (
        patch("custom_components.myq.MyQClient", return_value=client),
        patch("custom_components.myq.camera.TendLiveStream") as stream_class,
    ):
        live = stream_class.return_value
        live.source_url = AsyncMock(return_value="http://127.0.0.1:1234/test.h264")
        live.close = AsyncMock()
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        try:
            camera_id = er.async_get(hass).async_get_entity_id("camera", DOMAIN, "door-1_camera")
            assert camera_id is not None
            camera = get_camera_from_entity_id(hass, camera_id)
            assert hass.states.is_state(camera_id, STATE_UNAVAILABLE)
            assert camera.camera_capabilities.frontend_stream_types == {StreamType.HLS}
            provider.async_is_supported.assert_not_called()

            runtime = cast(MyQRuntimeData, entry.runtime_data)

            def source_url() -> str:
                runtime.coordinator.async_keypad_changed()
                return "http://127.0.0.1:1234/test.h264"

            live.source_url.side_effect = source_url
            client.async_get_devices.return_value = MyQDevices((DOOR,))
            await runtime.coordinator.async_refresh()
            await hass.async_block_till_done()

            assert hass.states.is_state(camera_id, "idle")
            assert camera.camera_capabilities.frontend_stream_types == {
                StreamType.HLS,
                StreamType.WEB_RTC,
            }
            provider.async_is_supported.assert_called_once_with("http://127.0.0.1:1234/test.h264")

            await runtime.coordinator.async_refresh()
            await hass.async_block_till_done()
            provider.async_is_supported.assert_called_once()
        finally:
            assert await hass.config_entries.async_unload(entry.entry_id)
            await hass.async_block_till_done()


def _entity(door: GarageDoor) -> tuple[MyQCameraEntity, MagicMock]:
    coordinator = MagicMock()
    coordinator.config_entry = None
    coordinator.data = {door.serial_number: door}
    coordinator.client.async_get_camera_image = AsyncMock(return_value=IMAGE)
    assert door.camera is not None
    return MyQCameraEntity(coordinator, door.camera, door=door), coordinator


async def test_camera_passes_lan_only_option_to_shared_stream() -> None:
    entity, coordinator = _entity(DOOR)
    coordinator.config_entry = MockConfigEntry(domain=DOMAIN, options={"camera_lan_only": True})
    with patch("custom_components.myq.camera.TendLiveStream") as factory:
        factory.return_value.source_url = AsyncMock(return_value="http://127.0.0.1/video")
        await entity.stream_source()
        factory.assert_called_once_with(
            entity._async_stream_target,
            coordinator.client.async_access_token,
            lan_only=True,
            fallback_target_supplier=entity._async_camera_target,
        )


async def test_camera_alias_lookup_has_a_short_deadline() -> None:
    entity, coordinator = _entity(DOOR)
    cancelled = asyncio.Event()

    async def slow_alias(camera: MyQCamera) -> str:
        try:
            await asyncio.Event().wait()
            return "account:mac1"
        finally:
            cancelled.set()

    coordinator.client.async_get_camera_alias = AsyncMock(side_effect=slow_alias)
    with (
        patch("custom_components.myq.camera._CAMERA_ALIAS_TIMEOUT", 0.01),
        pytest.raises(TimeoutError),
    ):
        await asyncio.wait_for(entity._async_camera_target(), 1)
    assert cancelled.is_set()
    coordinator.client.async_get_camera_alias.assert_awaited_once_with(DOOR.camera)
