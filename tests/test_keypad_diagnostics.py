"""Power cache, stale data and explicit refresh without background camera calls."""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.myq.coordinator import MyQDataUpdateCoordinator
from custom_components.myq.keypad_sensor import KEYPAD_SENSORS, MyQKeypadSensor
from custom_components.myq.keypad_state import KeypadPower, KeypadState
from custom_components.myq.models import MyQCamera

KEYPAD = MyQCamera("VK-0001-12345678", True, "vkp-camera")


@pytest.mark.parametrize("battery", [True, -1, 101, float("nan"), float("inf"), 10**300, "50"])
def test_bad_battery_values_are_unknown(battery: object) -> None:
    power = KeypadPower.from_device({"status": {"pwr": {"battLv": battery, "sleepMode": {}}}})
    assert power.battery_percent is None
    assert power.sleep_mode is None


def test_restore_preserves_sample_age_and_expires_without_refresh() -> None:
    with patch("custom_components.myq.keypad_state.time.time", return_value=100000):
        power = KeypadPower.from_storage(
            {"sampled_at": 100000 - 43201, "battery_percent": 65, "sleep_mode": "LPDS"}
        )
        assert power is not None and power.battery_percent == 65 and not power.fresh
        assert KeypadPower.from_storage({"sampled_at": 10**300}) is None


async def test_all_sensor_reads_and_explicit_updates_use_only_local_state() -> None:
    state = KeypadState(power=KeypadPower(time.time(), 65, "LPDS"))
    coordinator = MagicMock(last_update_success=True)
    coordinator.keypads = (KEYPAD,)
    coordinator.keypad_state.return_value = state
    coordinator.async_request_refresh = AsyncMock()
    coordinator.client.async_get_keypad_power = AsyncMock()
    coordinator.client.async_access_token = AsyncMock()
    for key in KEYPAD_SENSORS:
        sensor = MyQKeypadSensor(coordinator, KEYPAD, key)
        assert sensor.available
        _ = sensor.native_value
        await sensor.async_update()
    coordinator.async_request_refresh.assert_not_awaited()
    coordinator.client.async_get_keypad_power.assert_not_awaited()
    coordinator.client.async_access_token.assert_not_awaited()
    state.power = KeypadPower(time.time() - 43201, 65, "LPDS")
    assert not MyQKeypadSensor(coordinator, KEYPAD, "battery").available
    assert MyQKeypadSensor(coordinator, KEYPAD, "power_sample_time").available


async def test_explicit_power_requests_coalesce_and_persist_cache(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain="myq", data={})
    entry.add_to_hass(hass)
    client = MagicMock(keypads=(KEYPAD,))
    client.async_get_keypad_power = AsyncMock(return_value=KeypadPower(time.time(), 71, "LPDS"))
    coordinator = MyQDataUpdateCoordinator(hass, entry, client)
    coordinator.cameras = {KEYPAD.serial_number: KEYPAD}
    coordinator._power_store = MagicMock(
        async_load=AsyncMock(return_value={KEYPAD.serial_number: {"untouched": 1}}),
        async_save=AsyncMock(),
    )
    await coordinator.async_load_keypad_state()
    await asyncio.gather(
        *(coordinator.async_refresh_keypad_power(KEYPAD.serial_number) for _ in range(3))
    )
    client.async_get_keypad_power.assert_awaited_once_with(KEYPAD)
    saved = coordinator._power_store.async_save.await_args.args[0]
    assert saved[KEYPAD.serial_number]["untouched"] == 1
    client.async_get_keypad_power.reset_mock()
    restored = MyQDataUpdateCoordinator(hass, entry, client)
    restored.cameras = {KEYPAD.serial_number: KEYPAD}
    restored._power_store = MagicMock(async_load=AsyncMock(return_value=saved))
    await restored.async_load_keypad_state()
    assert (
        restored.keypad_state(KEYPAD.serial_number).power
        == coordinator.keypad_state(KEYPAD.serial_number).power
    )
    client.async_get_keypad_power.assert_not_awaited()
    await restored.async_shutdown()
    await coordinator.async_shutdown()


async def test_explicit_power_read_is_one_get_with_no_wake() -> None:
    from typing import cast

    from aiohttp import ClientSession

    from custom_components.myq.client import MyQClient
    from custom_components.myq.oauth import MyQAuth

    from .http import FakeResponse, FakeSession

    session = FakeSession(
        request_responses=[
            FakeResponse(
                "", body=b'{"id":"12345678","status":{"pwr":{"battLv":71,"sleepMode":"LPDS"}}}'
            )
        ]
    )
    auth = MagicMock(spec=MyQAuth)
    auth.async_access_token = AsyncMock(return_value="synthetic-access")
    power = await MyQClient(cast(ClientSession, session), auth).async_get_keypad_power(KEYPAD)
    assert power.battery_percent == 71
    assert power.sleep_mode == "LPDS"
    assert len(session.calls) == 1
    assert session.calls[0].method == "GET"
    assert "/do/wakeup" not in session.calls[0].url
    assert session.calls[0].kwargs["allow_redirects"] is False
    assert {"BrandId", "App-Version", "User-Agent", "partnerId"} <= session.calls[0].kwargs[
        "headers"
    ].keys()


async def test_power_rejects_another_camera_report() -> None:
    from typing import cast

    from aiohttp import ClientSession

    from custom_components.myq.client import MyQClient
    from custom_components.myq.exceptions import MyQApiError
    from custom_components.myq.oauth import MyQAuth

    from .http import FakeResponse, FakeSession

    session = FakeSession(request_responses=[FakeResponse("", body=b'{"id":"999"}')])
    auth = MagicMock(spec=MyQAuth)
    auth.async_access_token = AsyncMock(return_value="synthetic-access")
    with pytest.raises(MyQApiError, match="different camera"):
        await MyQClient(cast(ClientSession, session), auth).async_get_keypad_power(KEYPAD)
    assert len(session.calls) == 1


@pytest.mark.parametrize(
    ("status", "body", "message"),
    [(302, b"", "302"), (200, b"x" * 1_024_001, "size limit")],
    ids=["redirect", "oversized"],
)
async def test_explicit_power_request_rejects_redirect_or_oversized_body(
    status: int, body: bytes, message: str
) -> None:
    from typing import cast

    from aiohttp import ClientSession

    from custom_components.myq.client import MyQClient
    from custom_components.myq.exceptions import MyQApiError
    from custom_components.myq.oauth import MyQAuth

    from .http import FakeResponse, FakeSession

    auth = MagicMock(spec=MyQAuth)
    auth.async_access_token = AsyncMock(return_value="synthetic")
    session = FakeSession(request_responses=[FakeResponse("", status=status, body=body)])
    with pytest.raises(MyQApiError, match=message):
        await MyQClient(cast(ClientSession, session), auth).async_get_keypad_power(KEYPAD)
    assert len(session.calls) == 1
