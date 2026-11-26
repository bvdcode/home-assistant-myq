from dataclasses import replace
from typing import cast
from unittest.mock import MagicMock, patch

from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.setup import async_setup_component

from custom_components.myq.client import MyQClient
from custom_components.myq.const import DOMAIN
from custom_components.myq.exceptions import (
    MyQApiError,
    MyQRateLimitError,
    MyQUnsupportedDeviceError,
)
from custom_components.myq.models import MyQDevices
from custom_components.myq.opener_settings import OpenerSetting
from custom_components.myq.runtime import MyQRuntimeData

from .test_init import DOOR, _entry


async def test_configuration_entities_discovery_writes_and_readback(hass: HomeAssistant) -> None:
    assert await async_setup_component(hass, "homeassistant", {})
    other = replace(DOOR, account_id="other", serial_number="unsupported")
    values = {
        OpenerSetting.LIGHT_TIMER: 90,
        OpenerSetting.TIME_TO_CLOSE: 0,
        OpenerSetting.MOTION_LIGHT: False,
        OpenerSetting.LOCK_MODE: False,
    }
    client = MagicMock(spec=MyQClient)
    client.async_get_devices.return_value = MyQDevices((DOOR, other))

    def read(door: object, setting: OpenerSetting) -> int | bool:
        if door == other:
            raise MyQUnsupportedDeviceError
        return values[setting]

    client.async_read_opener_setting.side_effect = read
    entry = _entry()
    entry.add_to_hass(hass)
    with patch("custom_components.myq.MyQClient", return_value=client):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done(wait_background_tasks=True)
    runtime = cast(MyQRuntimeData, entry.runtime_data)
    reg = er.async_get(hass)
    for setting in OpenerSetting:
        platform = (
            "switch"
            if setting in (OpenerSetting.LOCK_MODE, OpenerSetting.MOTION_LIGHT)
            else "number"
        )
        entity_id = reg.async_get_entity_id(
            platform, DOMAIN, f"{DOOR.serial_number}_{setting.value}"
        )
        assert entity_id
        registry_entry = reg.async_get(entity_id)
        assert registry_entry and registry_entry.entity_category is EntityCategory.CONFIG
        assert reg.async_get_entity_id(platform, DOMAIN, f"unsupported_{setting.value}") is None
    client.async_read_opener_setting.reset_mock()
    await runtime.coordinator.async_refresh()
    client.async_read_opener_setting.assert_not_awaited()
    await runtime.settings.async_refresh()
    assert all(call.args[0] == DOOR for call in client.async_read_opener_setting.await_args_list)

    timer = reg.async_get_entity_id("number", DOMAIN, f"{DOOR.serial_number}_timetoclose")
    assert timer

    def accept(door: object, setting: OpenerSetting, value: int | bool) -> None:
        assert door == DOOR
        values[setting] = value

    client.async_write_opener_setting.side_effect = accept
    await hass.services.async_call(
        "number", "set_value", {"entity_id": timer, "value": 7}, blocking=True
    )
    client.async_write_opener_setting.assert_awaited_once_with(DOOR, OpenerSetting.TIME_TO_CLOSE, 7)
    state = hass.states.get(timer)
    assert state and float(state.state) == 7
    values[OpenerSetting.TIME_TO_CLOSE] = 9
    await hass.services.async_call(
        "homeassistant", "update_entity", {"entity_id": timer}, blocking=True
    )
    state = hass.states.get(timer)
    assert state and float(state.state) == 9

    motion = reg.async_get_entity_id("switch", DOMAIN, f"{DOOR.serial_number}_worklight_settings")
    assert motion
    await hass.services.async_call("switch", "turn_on", {"entity_id": motion}, blocking=True)
    state = hass.states.get(motion)
    assert state and state.state == "on"

    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_optional_settings_retry_temporary_failures_without_polling_door(
    hass: HomeAssistant,
) -> None:
    client = MagicMock(spec=MyQClient)
    client.async_get_devices.return_value = MyQDevices((DOOR,))
    client.async_read_opener_setting.side_effect = MyQApiError("temporarily unavailable")
    entry = _entry(disable_polling=True)
    entry.add_to_hass(hass)
    with patch("custom_components.myq.MyQClient", return_value=client):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done(wait_background_tasks=True)
    runtime = cast(MyQRuntimeData, entry.runtime_data)
    assert runtime.settings.data == {}
    assert runtime.coordinator.last_update_success

    def recover(door: object, setting: OpenerSetting) -> int | None:
        return 210 if setting is OpenerSetting.LIGHT_TIMER else None

    client.async_read_opener_setting.side_effect = recover
    await runtime.settings.async_refresh()
    await hass.async_block_till_done()
    reg = er.async_get(hass)
    light = reg.async_get_entity_id("number", DOMAIN, f"{DOOR.serial_number}_lighttimer")
    assert light
    state = hass.states.get(light)
    assert state and float(state.state) == 210
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_rate_limited_scan_publishes_partial_values_and_resumes(hass: HomeAssistant) -> None:
    client = MagicMock(spec=MyQClient)
    client.async_get_devices.return_value = MyQDevices((DOOR,))
    client.async_read_opener_setting.side_effect = [
        False,
        5,
        MyQRateLimitError(37),
        150,
        MyQRateLimitError(19),
        True,
    ]
    entry = _entry()
    entry.add_to_hass(hass)
    with patch("custom_components.myq.MyQClient", return_value=client):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done(wait_background_tasks=True)
    settings = cast(MyQRuntimeData, entry.runtime_data).settings
    lock, close, light, motion = OpenerSetting
    assert settings.data == {(DOOR.serial_number, lock): False, (DOOR.serial_number, close): 5}
    assert isinstance(settings.last_exception, UpdateFailed)
    assert settings.last_exception.retry_after == 37

    await settings.async_refresh()
    await hass.async_block_till_done()
    reg = er.async_get(hass)
    assert reg.async_get_entity_id("number", DOMAIN, f"{DOOR.serial_number}_lighttimer")
    assert isinstance(settings.last_exception, UpdateFailed)
    assert settings.last_exception.retry_after == 19
    await settings.async_refresh()
    assert settings.last_update_success
    assert [c.args[1] for c in client.async_read_opener_setting.await_args_list] == [
        lock,
        close,
        light,
        light,
        motion,
        motion,
    ]
    assert settings.data[(DOOR.serial_number, motion)] is True

    client.async_read_opener_setting.side_effect = [True, MyQRateLimitError(42)]
    await settings.async_refresh()
    assert settings.data == {
        (DOOR.serial_number, lock): True,
        (DOOR.serial_number, close): 5,
        (DOOR.serial_number, light): 150,
        (DOOR.serial_number, motion): True,
    }
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_manual_lock_update_restores_setting_after_offline_scan(hass: HomeAssistant) -> None:
    assert await async_setup_component(hass, "homeassistant", {})
    client = MagicMock(spec=MyQClient)
    client.async_get_devices.return_value = MyQDevices((DOOR,))
    client.async_read_opener_setting.side_effect = lambda door, setting: (
        door.in_vacation_mode if setting is OpenerSetting.LOCK_MODE else None
    )
    entry = _entry()
    entry.add_to_hass(hass)
    with patch("custom_components.myq.MyQClient", return_value=client):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done(wait_background_tasks=True)
    runtime = cast(MyQRuntimeData, entry.runtime_data)
    switch = er.async_get(hass).async_get_entity_id(
        "switch", DOMAIN, f"{DOOR.serial_number}_lockmode"
    )
    assert switch
    client.async_get_devices.return_value = MyQDevices((replace(DOOR, online=False),))
    await runtime.coordinator.async_refresh()
    await runtime.settings.async_refresh()
    assert hass.states.is_state(switch, "unavailable")

    online = replace(DOOR, online=True, in_vacation_mode=False)
    client.async_get_devices.return_value = MyQDevices((online,))
    client.async_read_opener_setting.reset_mock()
    await hass.services.async_call(
        "homeassistant", "update_entity", {"entity_id": switch}, blocking=True
    )
    assert hass.states.is_state(switch, "off")
    client.async_read_opener_setting.assert_awaited_once_with(online, OpenerSetting.LOCK_MODE)
    assert await hass.config_entries.async_unload(entry.entry_id)
