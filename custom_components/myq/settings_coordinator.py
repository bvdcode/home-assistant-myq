"""Low-frequency discovery and updates for optional opener settings."""

import asyncio
import logging
from collections.abc import Callable
from datetime import timedelta
from time import monotonic

from aiohttp import ClientError
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN
from .coordinator import MyQDataUpdateCoordinator
from .exceptions import (
    MyQApiError,
    MyQAuthenticationError,
    MyQError,
    MyQRateLimitError,
    MyQUnsupportedDeviceError,
)
from .models import GarageDoor
from .opener_settings import OpenerSetting
from .runtime import MyQConfigEntry

_LOGGER = logging.getLogger(__name__)
_SCAN_INTERVAL = timedelta(hours=12)
_READBACK_DELAYS = (2, 5)

type SettingKey = tuple[str, OpenerSetting]
type SettingsData = dict[SettingKey, int | bool]


class OpenerSettingsCoordinator(DataUpdateCoordinator[SettingsData]):
    """Read settings independently of door motion and ordinary discovery polling."""

    def __init__(
        self, hass: HomeAssistant, entry: MyQConfigEntry, doors: MyQDataUpdateCoordinator
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}_settings",
            config_entry=entry,
            update_interval=_SCAN_INTERVAL,
        )
        self.doors = doors
        self.data = {}
        self._unsupported: set[SettingKey] = set()
        self._remaining: list[SettingKey] = []
        self._deferred: set[SettingKey] = set()
        self._next_full_scan = 0.0
        self._unsub_doors: Callable[[], None] | None = None
        self._lock = asyncio.Lock()

    @callback
    def _check_returned_doors(self) -> None:
        entry = self.config_entry
        if (
            entry is None
            or entry.pref_disable_polling
            or not self.doors.last_update_success
            or not self.last_update_success
            or self._remaining
            or self._lock.locked()
        ):
            return
        self._remaining = sorted(
            key
            for key in self._deferred
            if (door := self.doors.data.get(key[0])) is not None and door.online is not False
        )
        if self._remaining:
            entry.async_create_background_task(
                self.hass, self.async_request_refresh(), "myq missed opener settings"
            )

    async def async_shutdown(self) -> None:
        """Stop watching door availability when the entry unloads."""
        if self._unsub_doors is not None:
            self._unsub_doors()
            self._unsub_doors = None
        await super().async_shutdown()

    def _pending_settings(self) -> list[SettingKey]:
        doors = self.doors.data
        pending = self._remaining
        if not pending:
            self._next_full_scan = monotonic() + _SCAN_INTERVAL.total_seconds()
            self._deferred.clear()
            pending = [(serial, setting) for serial in doors for setting in OpenerSetting]

        ready = []
        for key in pending:
            self._deferred.discard(key)
            door = doors.get(key[0])
            if door is None or key in self._unsupported:
                continue
            if door.online is False:
                self._deferred.add(key)
            else:
                ready.append(key)

        if self._deferred and self._unsub_doors is None:
            self._unsub_doors = self.doors.async_add_listener(self._check_returned_doors)
        elif not self._deferred and self._unsub_doors is not None:
            self._unsub_doors()
            self._unsub_doors = None
        return ready

    async def _async_update_data(self) -> SettingsData:
        async with self._lock:
            doors = self.doors.data
            values = {key: value for key, value in self.data.items() if key[0] in doors}
            pending = self._pending_settings()
            for index, key in enumerate(pending):
                serial, setting = key
                try:
                    value = await self.doors.client.async_read_opener_setting(
                        doors[serial], setting
                    )
                except MyQAuthenticationError as error:
                    raise ConfigEntryAuthFailed(
                        translation_domain=DOMAIN, translation_key="invalid_auth"
                    ) from error
                except MyQRateLimitError as error:
                    self._remaining = pending[index:]
                    changed = values != self.data
                    self.data = values
                    # Home Assistant skips listener updates on consecutive refresh failures.
                    if changed and not self.last_update_success:
                        self.async_update_listeners()
                    raise UpdateFailed(
                        translation_domain=DOMAIN,
                        translation_key="update_failed",
                        retry_after=error.retry_after,
                    ) from error
                except MyQUnsupportedDeviceError:
                    self._unsupported.add(key)
                    value = None
                except (ClientError, MyQError, TimeoutError) as error:
                    _LOGGER.debug("Could not read %s: %s", setting.value, error)
                    value = None
                if value is None:
                    values.pop(key, None)
                else:
                    values[key] = value
            self._remaining = []
            self.update_interval = timedelta(seconds=max(1, self._next_full_scan - monotonic()))
            return values

    async def async_write(
        self, door: GarageDoor, setting: OpenerSetting, value: int | bool
    ) -> None:
        """Serialize device writes with reads and publish the confirmed setting."""
        key = (door.serial_number, setting)
        async with self._lock:
            if key not in self.data:
                raise MyQApiError("Opener setting unavailable")
            await self.doors.client.async_write_opener_setting(door, setting, value)
            reported = await self._async_readback(door, setting)
            if setting is OpenerSetting.LOCK_MODE:
                return
            for delay in _READBACK_DELAYS:
                if reported == value or reported is None:
                    break
                await asyncio.sleep(delay)
                reported = await self._async_readback(door, setting)
            if reported != value:
                raise MyQApiError(f"Opener did not confirm {setting.value}")

    async def async_readback(self, door: GarageDoor, setting: OpenerSetting) -> None:
        """Refresh one configuration value when requested by Home Assistant."""
        async with self._lock:
            await self._async_readback(door, setting)

    async def _async_readback(self, door: GarageDoor, setting: OpenerSetting) -> int | bool | None:
        key = (door.serial_number, setting)
        if setting is OpenerSetting.LOCK_MODE:
            await self.doors.async_request_refresh()
            if key in self.data or not self.doors.last_update_success:
                return None
            refreshed = self.doors.data.get(door.serial_number)
            if refreshed is None or refreshed.online is False:
                return None
            door = refreshed
        try:
            value = await self.doors.client.async_read_opener_setting(door, setting)
        except ClientError, MyQError, TimeoutError:
            self.data.pop(key, None)
            self.async_update_listeners()
            raise
        if value is None:
            self.data.pop(key, None)
        else:
            self.data[key] = value
        self.async_update_listeners()
        return value
