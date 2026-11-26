"""Low-frequency discovery and updates for optional opener settings."""

import asyncio
import logging
from datetime import timedelta

from aiohttp import ClientError
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN
from .coordinator import MyQDataUpdateCoordinator
from .exceptions import MyQApiError, MyQError, MyQRateLimitError, MyQUnsupportedDeviceError
from .models import GarageDoor
from .opener_settings import OpenerSetting
from .runtime import MyQConfigEntry

_LOGGER = logging.getLogger(__name__)

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
            update_interval=timedelta(hours=12),
        )
        self.doors = doors
        self.data = {}
        self._unsupported: set[SettingKey] = set()
        self._remaining: list[SettingKey] = []
        self._lock = asyncio.Lock()

    async def _async_update_data(self) -> SettingsData:
        async with self._lock:
            online = {s: door for s, door in self.doors.data.items() if door.online is not False}
            values = {key: value for key, value in self.data.items() if key[0] in online}
            pending = self._remaining or [
                (serial, setting) for serial in online for setting in OpenerSetting
            ]
            for index, key in enumerate(pending):
                serial, setting = key
                if serial not in online or key in self._unsupported:
                    continue
                try:
                    value = await self.doors.client.async_read_opener_setting(
                        online[serial], setting
                    )
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
            await self._async_readback(door, setting)

    async def async_readback(self, door: GarageDoor, setting: OpenerSetting) -> None:
        """Refresh one configuration value when requested by Home Assistant."""
        async with self._lock:
            await self._async_readback(door, setting)

    async def _async_readback(self, door: GarageDoor, setting: OpenerSetting) -> None:
        key = (door.serial_number, setting)
        if setting is OpenerSetting.LOCK_MODE:
            await self.doors.async_request_refresh()
            if key in self.data or not self.doors.last_update_success:
                return
            refreshed = self.doors.data.get(door.serial_number)
            if refreshed is None or refreshed.online is False:
                return
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
