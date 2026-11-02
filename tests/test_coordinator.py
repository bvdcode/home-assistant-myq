import asyncio
from collections.abc import AsyncGenerator
from dataclasses import replace
from datetime import timedelta
from typing import Literal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import ClientConnectionError
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.myq.const import (
    COMMAND_UPDATE_INITIAL_INTERVAL,
    COMMAND_UPDATE_INTERVAL,
    COMMAND_UPDATE_MIN_DURATION,
    COMMAND_UPDATE_TIMEOUT,
    DEFAULT_UPDATE_INTERVAL,
)
from custom_components.myq.coordinator import MyQDataUpdateCoordinator
from custom_components.myq.exceptions import MyQApiError, MyQAuthenticationError
from custom_components.myq.models import GarageDoor

DOOR = GarageDoor("account-1", "door-1", "Garage", None, "closed", True)


async def test_coordinator_indexes_every_door(hass: HomeAssistant) -> None:
    client = MagicMock()
    client.async_get_garage_doors = AsyncMock(return_value=(DOOR,))
    coordinator = MyQDataUpdateCoordinator(hass, MockConfigEntry(), client)

    assert await coordinator._async_update_data() == {"door-1": DOOR}


async def test_coordinator_requests_reauthentication(hass: HomeAssistant) -> None:
    client = MagicMock()
    client.async_get_garage_doors = AsyncMock(side_effect=MyQAuthenticationError)
    coordinator = MyQDataUpdateCoordinator(hass, MockConfigEntry(), client)

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


async def test_coordinator_translates_network_failure(hass: HomeAssistant) -> None:
    client = MagicMock()
    client.async_get_garage_doors = AsyncMock(side_effect=ClientConnectionError)
    coordinator = MyQDataUpdateCoordinator(hass, MockConfigEntry(), client)

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


@pytest.fixture
async def command_updates(
    hass: HomeAssistant,
) -> AsyncGenerator[tuple[MyQDataUpdateCoordinator, MagicMock]]:
    client = MagicMock()
    client.async_get_garage_doors = AsyncMock(return_value=(DOOR,))
    coordinator = MyQDataUpdateCoordinator(hass, MockConfigEntry(), client)
    coordinator.data = {DOOR.serial_number: DOOR}
    yield coordinator, client
    await coordinator.async_shutdown()


@pytest.mark.parametrize(
    ("initial", "moving", "target"),
    [("closed", "opening", "open"), ("open", "closing", "closed")],
)
async def test_command_polling_waits_for_confirmed_state(
    command_updates: tuple[MyQDataUpdateCoordinator, MagicMock],
    initial: str,
    moving: str,
    target: Literal["open", "closed"],
) -> None:
    coordinator, client = command_updates
    client.async_get_garage_doors.return_value = (replace(DOOR, door_state=initial),)
    with patch("custom_components.myq.coordinator.monotonic", return_value=0) as clock:
        coordinator.async_schedule_command_updates("door-1", target)
        assert coordinator.update_interval == COMMAND_UPDATE_INITIAL_INTERVAL
        client.async_get_garage_doors.assert_not_awaited()

        await coordinator.async_refresh()
        assert coordinator.data["door-1"].door_state == initial

        client.async_get_garage_doors.return_value = (replace(DOOR, door_state=moving),)
        await coordinator.async_refresh()
        assert coordinator.data["door-1"].door_state == moving

        client.async_get_garage_doors.return_value = (replace(DOOR, door_state=target),)
        await coordinator.async_refresh()
        assert coordinator.data["door-1"].door_state == target
        assert coordinator.update_interval != DEFAULT_UPDATE_INTERVAL

        clock.return_value = COMMAND_UPDATE_MIN_DURATION.total_seconds()
        await coordinator.async_refresh()
    assert coordinator.update_interval == DEFAULT_UPDATE_INTERVAL


async def test_command_polling_gradually_increases_intervals(
    command_updates: tuple[MyQDataUpdateCoordinator, MagicMock],
) -> None:
    coordinator, client = command_updates
    coordinator.async_schedule_command_updates("door-1", "open")
    client.async_get_garage_doors.assert_not_awaited()
    for expected in (1, 2, 3, 4, 5, 5, 5):
        assert coordinator.update_interval == timedelta(seconds=expected)
        await coordinator.async_refresh()
    assert coordinator.update_interval == COMMAND_UPDATE_INTERVAL


@pytest.mark.parametrize(
    ("initial", "target", "motion"),
    [
        ("closed", "open", "opening"),
        ("open", "closed", "closing"),
        ("closed", "closed", None),
        ("open", "open", None),
        ("unknown", "open", None),
        ("opening", "closed", None),
    ],
)
async def test_first_unchanged_status_keeps_provisional_motion_once(
    command_updates: tuple[MyQDataUpdateCoordinator, MagicMock],
    initial: str,
    target: Literal["open", "closed"],
    motion: str | None,
) -> None:
    coordinator, client = command_updates
    door = replace(DOOR, door_state=initial)
    coordinator.data = {door.serial_number: door}
    client.async_get_garage_doors.return_value = (door,)
    listener = MagicMock()
    unsubscribe = coordinator.async_add_listener(listener)

    coordinator.async_schedule_command_updates(door.serial_number, target)
    assert coordinator.command_motion(door.serial_number) == motion
    assert coordinator.data[door.serial_number] is door
    client.async_get_garage_doors.assert_not_awaited()
    listener.assert_called_once()

    await coordinator.async_refresh()
    assert coordinator.command_motion(door.serial_number) == motion
    assert coordinator.data[door.serial_number] is door
    assert listener.call_count == 2

    await coordinator.async_refresh()
    assert coordinator.command_motion(door.serial_number) is None
    assert coordinator.data[door.serial_number] is door
    assert listener.call_count == 3
    unsubscribe()


@pytest.mark.parametrize(
    ("initial", "target", "reported"),
    [
        ("closed", "open", "opening"),
        ("closed", "open", "open"),
        ("open", "closed", "closing"),
        ("open", "closed", "closed"),
    ],
)
async def test_first_changed_status_immediately_replaces_provisional_motion(
    command_updates: tuple[MyQDataUpdateCoordinator, MagicMock],
    initial: str,
    target: Literal["open", "closed"],
    reported: str,
) -> None:
    coordinator, client = command_updates
    coordinator.data = {DOOR.serial_number: replace(DOOR, door_state=initial)}
    coordinator.async_schedule_command_updates(DOOR.serial_number, target)
    client.async_get_garage_doors.return_value = (replace(DOOR, door_state=reported),)

    await coordinator.async_refresh()
    assert coordinator.command_motion(DOOR.serial_number) is None
    assert coordinator.data[DOOR.serial_number].door_state == reported


async def test_unchanged_state_stops_fast_polling_at_deadline(
    command_updates: tuple[MyQDataUpdateCoordinator, MagicMock],
) -> None:
    coordinator, _ = command_updates
    with patch("custom_components.myq.coordinator.monotonic", return_value=0) as clock:
        coordinator.async_schedule_command_updates("door-1", "open")
        clock.return_value = COMMAND_UPDATE_TIMEOUT.total_seconds()
        await coordinator.async_refresh()
    assert coordinator.update_interval == DEFAULT_UPDATE_INTERVAL
    assert coordinator.data["door-1"].door_state == "closed"


@pytest.mark.parametrize("doors", [(), (replace(DOOR, online=False),)])
async def test_missing_or_offline_door_stops_fast_polling(
    command_updates: tuple[MyQDataUpdateCoordinator, MagicMock],
    doors: tuple[GarageDoor, ...],
) -> None:
    coordinator, client = command_updates
    coordinator.async_schedule_command_updates("door-1", "open")
    client.async_get_garage_doors.return_value = doors
    await coordinator.async_refresh()
    assert coordinator.update_interval == DEFAULT_UPDATE_INTERVAL


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (ClientConnectionError, UpdateFailed),
        (MyQApiError, UpdateFailed),
        (TimeoutError, UpdateFailed),
        (MyQAuthenticationError, ConfigEntryAuthFailed),
    ],
)
async def test_poll_failure_stops_fast_polling(
    command_updates: tuple[MyQDataUpdateCoordinator, MagicMock],
    error: type[Exception],
    expected: type[Exception],
) -> None:
    coordinator, client = command_updates
    coordinator.async_schedule_command_updates("door-1", "open")
    client.async_get_garage_doors.side_effect = error
    with pytest.raises(expected):
        await coordinator._async_update_data()
    assert coordinator.update_interval == DEFAULT_UPDATE_INTERVAL
    assert coordinator.command_motion("door-1") is None


@pytest.mark.parametrize("previous_window", [COMMAND_UPDATE_MIN_DURATION, COMMAND_UPDATE_TIMEOUT])
async def test_new_command_replaces_previous_target_and_deadline(
    command_updates: tuple[MyQDataUpdateCoordinator, MagicMock],
    previous_window: timedelta,
) -> None:
    coordinator, client = command_updates
    with patch("custom_components.myq.coordinator.monotonic", return_value=0) as clock:
        coordinator.async_schedule_command_updates("door-1", "open")
        for _ in range(4):
            await coordinator.async_refresh()
        assert coordinator.update_interval == COMMAND_UPDATE_INTERVAL
        clock.return_value = previous_window.total_seconds() - 1
        client.async_get_garage_doors.return_value = (replace(DOOR, door_state="opening"),)
        coordinator.async_schedule_command_updates("door-1", "closed")
        assert coordinator.update_interval == COMMAND_UPDATE_INITIAL_INTERVAL
        clock.return_value = previous_window.total_seconds()
        client.async_get_garage_doors.return_value = (replace(DOOR, door_state="open"),)
        await coordinator.async_refresh()
        assert coordinator.update_interval == timedelta(seconds=2)
        client.async_get_garage_doors.return_value = (replace(DOOR, door_state="closing"),)
        await coordinator.async_refresh()
        assert coordinator.data["door-1"].is_closing
        assert coordinator.update_interval == timedelta(seconds=3)
        client.async_get_garage_doors.return_value = (DOOR,)
        await coordinator.async_refresh()
        assert coordinator.update_interval != DEFAULT_UPDATE_INTERVAL
        clock.return_value = (
            previous_window.total_seconds() - 1 + COMMAND_UPDATE_MIN_DURATION.total_seconds()
        )
        await coordinator.async_refresh()
    assert coordinator.update_interval == DEFAULT_UPDATE_INTERVAL


async def test_each_door_keeps_its_own_command_target(
    command_updates: tuple[MyQDataUpdateCoordinator, MagicMock],
) -> None:
    coordinator, client = command_updates
    other = replace(DOOR, serial_number="door-2", door_state="open")
    client.async_get_garage_doors.return_value = (DOOR, other)
    with patch("custom_components.myq.coordinator.monotonic", return_value=0) as clock:
        coordinator.async_schedule_command_updates("door-1", "open")
        coordinator.async_schedule_command_updates("door-2", "closed")
        client.async_get_garage_doors.return_value = (
            replace(DOOR, door_state="open"),
            replace(other, door_state="closing"),
        )
        clock.return_value = COMMAND_UPDATE_MIN_DURATION.total_seconds()
        await coordinator.async_refresh()
        assert coordinator.update_interval == timedelta(seconds=2)
        client.async_get_garage_doors.return_value = (
            replace(DOOR, door_state="open"),
            replace(other, door_state="closed"),
        )
        await coordinator.async_refresh()
    assert coordinator.update_interval == DEFAULT_UPDATE_INTERVAL


@pytest.mark.parametrize("fails", [False, True])
async def test_old_refresh_cannot_complete_new_command(
    command_updates: tuple[MyQDataUpdateCoordinator, MagicMock],
    fails: bool,
) -> None:
    coordinator, client = command_updates
    requested = asyncio.Event()
    release = asyncio.Event()

    async def delayed_read() -> tuple[GarageDoor, ...]:
        requested.set()
        await release.wait()
        if fails:
            raise ClientConnectionError("Old request failed")
        return (replace(DOOR, door_state="open"),)

    with patch("custom_components.myq.coordinator.monotonic", return_value=0) as clock:
        coordinator.async_schedule_command_updates("door-1", "closed")
        client.async_get_garage_doors.side_effect = delayed_read
        old_refresh = asyncio.create_task(coordinator.async_refresh())
        await requested.wait()
        clock.return_value = COMMAND_UPDATE_MIN_DURATION.total_seconds()
        coordinator.async_schedule_command_updates("door-1", "open")
        release.set()
        await old_refresh
        assert coordinator.update_interval == COMMAND_UPDATE_INITIAL_INTERVAL
        assert coordinator.command_motion("door-1") == "opening"

        client.async_get_garage_doors.side_effect = None
        client.async_get_garage_doors.return_value = (replace(DOOR, door_state="opening"),)
        await coordinator.async_refresh()
        assert coordinator.data["door-1"].is_opening
        assert coordinator.update_interval == timedelta(seconds=2)
        assert coordinator.command_motion("door-1") is None

        clock.return_value += COMMAND_UPDATE_MIN_DURATION.total_seconds()
        client.async_get_garage_doors.return_value = (replace(DOOR, door_state="open"),)
        await coordinator.async_refresh()
    assert coordinator.update_interval == DEFAULT_UPDATE_INTERVAL
