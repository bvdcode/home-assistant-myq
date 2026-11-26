from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from time import monotonic
from typing import Literal, cast
from urllib.parse import quote

from aiohttp import ClientSession

from .const import (
    ACCOUNT_DISCOVERY_INTERVAL,
    ACCOUNTS_BASE_URL,
    APP_VERSION,
    BRAND_ID,
    DEVICES_BASE_URL,
    GARAGE_DEVICES_BASE_URL,
    LIGHT_DEVICES_BASE_URL,
    TEND_API_BASE_URL,
    TEND_LOCALE,
    TEND_PARTNER_ID,
    USER_AGENT,
)
from .discovery import parse_garage_door, parse_light
from .exceptions import MyQApiError, MyQAuthenticationError, MyQUnsupportedDeviceError
from .keypad_state import KeypadPower
from .keypad_wake import async_wake_keypad
from .models import GarageDoor, MyQAccount, MyQCamera, MyQDevices, MyQLight
from .oauth import MyQAuth
from .opener_settings import REMOTE_TYPES, OpenerSetting
from .request_limits import RequestCooldown

type HeadersFn = Callable[[str], dict[str, str]]


class MyQClient:
    """Access account devices and camera metadata with shared OAuth and cooldowns."""

    def __init__(self, session: ClientSession, auth: MyQAuth) -> None:
        self._session = session
        self._auth = auth
        self._accounts: tuple[MyQAccount, ...] | None = None
        self._accounts_updated_at = 0.0
        self._accounts_lock = asyncio.Lock()
        self._request_cooldown = RequestCooldown()

    async def async_access_token(self) -> str:
        """Return the current OAuth token for Tend camera signaling."""
        return await self._auth.async_access_token()

    async def async_prepare_keypad(self, camera: MyQCamera) -> str | None:
        """Prepare only a battery keypad, retaining this client's refresh ownership."""
        if not camera.is_video_keypad:
            return None

        async def request(method: str, url: str, body: dict[str, object] | None) -> bytes:
            return await self._async_request(
                method,
                url,
                _metadata_headers,
                json_body=body,
                allow_redirects=False,
                max_body_bytes=1_024_000,
            )

        device = await async_wake_keypad(camera.tend_device_id, request)
        if "id" in device and device["id"] != camera.tend_device_id:
            raise MyQApiError("Tend returned a different camera identity")
        if "id" in device and "alias" in device:
            return _camera_alias(camera, device)
        return None

    async def async_get_accounts(self) -> tuple[MyQAccount, ...]:
        """Refresh account membership less frequently than device state."""
        async with self._accounts_lock:
            if (
                self._accounts is not None
                and monotonic() - self._accounts_updated_at
                < ACCOUNT_DISCOVERY_INTERVAL.total_seconds()
            ):
                return self._accounts
            accounts = await self._async_fetch_accounts()
            self._accounts = accounts
            self._accounts_updated_at = monotonic()
            return accounts

    async def _async_fetch_accounts(self) -> tuple[MyQAccount, ...]:
        payload = await self._async_request_json(
            "GET",
            f"{ACCOUNTS_BASE_URL}/api/v6.0/accounts",
        )
        raw_accounts = payload.get("accounts")
        if not isinstance(raw_accounts, list):
            raise MyQApiError("MyQ account discovery returned no account list")

        accounts: list[MyQAccount] = []
        for raw_account in raw_accounts:
            if not isinstance(raw_account, dict):
                raise MyQApiError("MyQ returned an invalid account")
            account = cast(dict[str, object], raw_account)
            account_id = account.get("id")
            name = account.get("name")
            if not isinstance(account_id, str):
                raise MyQApiError("MyQ returned an account without an ID")
            accounts.append(
                MyQAccount(
                    account_id=account_id,
                    name=name if isinstance(name, str) else account_id,
                )
            )
        return tuple(accounts)

    async def async_get_devices(self) -> MyQDevices:
        """Discover supported devices together without retaining a partial result."""
        accounts = await self.async_get_accounts()
        groups = await asyncio.gather(
            *(self._async_get_account_devices(account) for account in accounts)
        )
        cameras = {camera.serial_number: camera for group in groups for camera in group.cameras}
        return MyQDevices(
            doors=tuple(door for group in groups for door in group.doors),
            cameras=tuple(cameras.values()),
            lights=tuple(light for group in groups for light in group.lights),
        )

    async def async_open_door(self, door: GarageDoor) -> None:
        """Request opening for the door in its owning account."""
        await self._async_command(door, "open")

    async def async_close_door(self, door: GarageDoor) -> None:
        """Request closing for the door in its owning account."""
        await self._async_command(door, "close")

    async def async_turn_on_light(self, light: MyQLight) -> None:
        """Turn on a standalone light control in its owning account."""
        await self._async_light_command(light, "on")

    async def async_turn_off_light(self, light: MyQLight) -> None:
        """Turn off a standalone light control in its owning account."""
        await self._async_light_command(light, "off")

    async def _async_light_command(self, light: MyQLight, command: Literal["on", "off"]) -> None:
        url = (
            f"{LIGHT_DEVICES_BASE_URL}/api/v6.0/accounts/{quote(light.account_id, safe='')}/"
            f"lamps/{quote(light.serial_number, safe='')}/{command}"
        )
        await self._async_request("PUT", url)

    async def async_get_camera_image(self, camera: MyQCamera) -> bytes:
        """Return the latest JPEG image supplied by Tend."""
        image = await self._async_request(
            "GET",
            f"{TEND_API_BASE_URL}/devices/{camera.tend_device_id}/cam/recentImage.jpg",
            _tend_headers,
        )
        if not image.startswith(b"\xff\xd8"):
            raise MyQApiError("Tend returned a camera snapshot that is not a JPEG")
        return image

    async def _async_camera_metadata(self, camera: MyQCamera) -> dict[str, object]:
        if not camera.tend_device_id.isdecimal():
            raise MyQApiError("Invalid camera video identifier")
        payload = await self._async_request_json(
            "GET",
            f"{TEND_API_BASE_URL}/devices/{camera.tend_device_id}",
            _metadata_headers,
            bounded=True,
        )
        if payload.get("id") != camera.tend_device_id:
            raise MyQApiError("Tend returned a different camera identity")
        return payload

    async def async_get_keypad_power(self, camera: MyQCamera) -> KeypadPower:
        """Read this keypad's reported power with one explicit metadata GET."""
        if not camera.is_video_keypad:
            raise MyQApiError("Camera is not a Video Keypad")
        async with asyncio.timeout(15):
            metadata = await self._async_camera_metadata(camera)
        try:
            return KeypadPower.from_device(metadata)
        except ValueError:
            raise MyQApiError("Keypad returned an invalid power report") from None

    async def async_get_camera_alias(self, camera: MyQCamera) -> str:
        """Resolve one camera's signaling destination from its Tend device ID."""
        payload = await self._async_camera_metadata(camera)
        return _camera_alias(camera, payload)

    async def _async_get_account_devices(
        self,
        account: MyQAccount,
    ) -> MyQDevices:
        payload = await self._async_request_json(
            "GET",
            f"{DEVICES_BASE_URL}/api/v6.2/Accounts/{account.account_id}/Devices",
        )
        raw_items = payload.get("items")
        if not isinstance(raw_items, list):
            raise MyQApiError("MyQ device discovery returned no item list")

        door_items: list[dict[str, object]] = []
        cameras: dict[str, MyQCamera] = {}
        lights: list[MyQLight] = []
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                raise MyQApiError("MyQ returned an invalid device")
            item = cast(dict[str, object], raw_item)
            match item.get("device_family"):
                case "garagedoor":
                    door_items.append(item)
                case "lamp":
                    lights.append(parse_light(account.account_id, item))
                case "camera":
                    serial_number = item.get("serial_number")
                    if isinstance(serial_number, str) and serial_number:
                        model = item.get("device_model")
                        name = item.get("name")
                        cameras[serial_number] = MyQCamera(
                            serial_number,
                            _online(item.get("state")),
                            model if isinstance(model, str) else None,
                            name if isinstance(name, str) else None,
                        )
        return MyQDevices(
            doors=tuple(
                parse_garage_door(account.account_id, item, cameras) for item in door_items
            ),
            cameras=tuple(cameras.values()),
            lights=tuple(lights),
        )

    async def async_read_opener_setting(
        self, door: GarageDoor, setting: OpenerSetting
    ) -> int | bool | None:
        """Read one setting, returning None for devices without the capability."""
        if setting is OpenerSetting.LOCK_MODE and door.in_vacation_mode is None:
            return None
        path = "accessories" if setting is OpenerSetting.LOCK_MODE else setting.value
        async with asyncio.timeout(15):
            payload = await self._async_request_json("GET", _opener_url(door, path), bounded=True)
        if setting is OpenerSetting.LOCK_MODE:
            remotes = payload.get("gdo_transmitter_names")
            if isinstance(remotes, list) and any(
                isinstance(remote, dict)
                and isinstance(remote_type := remote.get("transmitter_type"), str)
                and remote_type in REMOTE_TYPES
                for remote in remotes
            ):
                return door.in_vacation_mode
            return None
        return setting.read(payload)

    async def async_write_opener_setting(
        self, door: GarageDoor, setting: OpenerSetting, value: int | bool
    ) -> None:
        """Apply one validated setting to its owning opener."""
        await self._async_request(
            "PUT",
            _opener_url(door, setting.value),
            json_body=setting.payload(value),
            allow_redirects=False,
        )

    async def _async_command(self, door: GarageDoor, command: str) -> None:
        await self._async_request("PUT", _opener_url(door, command))

    async def _async_request_json(
        self, method: str, url: str, headers: HeadersFn | None = None, *, bounded: bool = False
    ) -> dict[str, object]:
        body = (
            await self._async_request(
                method, url, headers, allow_redirects=False, max_body_bytes=1_024_000
            )
            if bounded
            else await self._async_request(method, url, headers)
        )
        try:
            parsed = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise MyQApiError("MyQ returned an invalid JSON response") from error
        if not isinstance(parsed, dict):
            raise MyQApiError("MyQ returned an unexpected JSON response")
        return cast(dict[str, object], parsed)

    async def _async_request(
        self,
        method: str,
        url: str,
        headers: HeadersFn | None = None,
        *,
        json_body: dict[str, object] | None = None,
        allow_redirects: bool | None = None,
        max_body_bytes: int | None = None,
    ) -> bytes:
        self._request_cooldown.check(url)
        access_token = await self._auth.async_access_token()
        self._request_cooldown.check(url)
        request_headers = (headers or _api_headers)(access_token)
        if allow_redirects is None:
            request = self._session.request(method, url, headers=request_headers)
        else:
            request = self._session.request(
                method,
                url,
                headers=request_headers,
                json=json_body,
                allow_redirects=allow_redirects,
            )
        async with request as response:
            if max_body_bytes is None:
                body = await response.read()
            else:
                received = bytearray()
                async for chunk in response.content.iter_chunked(65536):
                    received.extend(chunk)
                    if len(received) > max_body_bytes:
                        raise MyQApiError("MyQ response exceeds size limit")
                body = bytes(received)
            self._request_cooldown.check_response(url, response.status, response.headers)
            if response.status == 400:
                try:
                    problem = json.loads(body)
                except UnicodeDecodeError, json.JSONDecodeError:
                    problem = None
                if isinstance(problem, dict) and problem.get("code") == "400.003":
                    raise MyQUnsupportedDeviceError("Device does not support this operation")
            if response.status in {401, 403}:
                raise MyQAuthenticationError(f"MyQ returned HTTP {response.status}")
            if response.status >= (300 if allow_redirects is False else 400):
                raise MyQApiError(f"MyQ returned HTTP {response.status}")
            return body


def _opener_url(door: GarageDoor, path: str) -> str:
    return (
        f"{GARAGE_DEVICES_BASE_URL}/api/v6.0/accounts/{quote(door.account_id, safe='')}/"
        f"door_openers/{quote(door.serial_number, safe='')}/{path}"
    )


def _camera_alias(camera: MyQCamera, payload: dict[str, object]) -> str:
    if payload.get("id") != camera.tend_device_id:
        raise MyQApiError("Tend returned a different camera identity")
    alias = payload.get("alias")
    if not isinstance(alias, str):
        raise MyQApiError("Tend returned a camera without a signaling alias")
    owner, separator, device = alias.partition(":")
    if not owner or not separator or not device:
        raise MyQApiError("Tend returned an invalid signaling alias")
    return alias


def _online(raw_state: object) -> bool | None:
    if not isinstance(raw_state, dict):
        return None
    online = cast(dict[str, object], raw_state).get("online")
    return online if isinstance(online, bool) else None


def _api_headers(access_token: str) -> dict[str, str]:
    return {
        "Accept": "application/json",
        "App-Version": APP_VERSION,
        "Authorization": f"Bearer {access_token}",
        "BrandId": BRAND_ID,
        "User-Agent": USER_AGENT,
    }


def _tend_headers(access_token: str) -> dict[str, str]:
    return {
        "AntiCSRF": "AntiCSRF",
        "Authorization": f"Bearer {access_token}",
        "SeedonkLocale": TEND_LOCALE,
        "partnerId": TEND_PARTNER_ID,
    }


def _metadata_headers(access_token: str) -> dict[str, str]:
    return {**_api_headers(access_token), **_tend_headers(access_token)}
