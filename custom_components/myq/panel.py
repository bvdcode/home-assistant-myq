"""Home Assistant sidebar panel and dashboard card for MyQ garage doors and cameras.

The panel is shared by every MyQ config entry that enables it. Entries are followed through
config entry change signals, so the panel stays registered while an entry reloads or retries
setup, and the frontend can explain why doors are unavailable. The dashboard card is offered
while any MyQ entry is set up, whether or not its sidebar panel is shown.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, NotRequired, TypedDict

import voluptuous as vol
from homeassistant.components import frontend, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.components.websocket_api.connection import ActiveConnection
from homeassistant.components.websocket_api.const import ERR_NOT_FOUND
from homeassistant.components.websocket_api.decorators import (
    async_response,
    require_admin,
    websocket_command,
)
from homeassistant.components.websocket_api.messages import event_message
from homeassistant.config_entries import (
    SIGNAL_CONFIG_ENTRY_CHANGED,
    ConfigEntry,
    ConfigEntryChange,
)
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.storage import Store
from homeassistant.util.hass_dict import HassKey

from .const import DOMAIN
from .panel_options import panel_options

_LOGGER = logging.getLogger(__name__)

PANEL_URL_PATH: Final = DOMAIN
PANEL_COMPONENT: Final = "myq-panel"
PANEL_MODULE: Final = "myq-panel.js"
CARD_MODULE: Final = "myq-card.js"
STATIC_URL_PREFIX: Final = f"/{DOMAIN}_panel"
FRONTEND_PATH: Final = Path(__file__).parent / "frontend"
STORAGE_KEY: Final = f"{DOMAIN}.panel"
STORAGE_VERSION: Final = 1
MAX_DEVICES: Final = 200
MAX_OPEN_WARNING: Final = 24 * 60

DATA_PANEL: HassKey[MyQPanel] = HassKey(f"{DOMAIN}_panel")

_SLUG = vol.All(str, vol.Match(r"^[a-z0-9_]{1,32}$"))
_COLOR = vol.All(str, vol.Match(r"^(#[0-9a-f]{6}|[a-z0-9_]{1,32})$"))
_DEVICE_ID = vol.All(str, vol.Length(min=1, max=64))


def _minutes(value: Any) -> int:
    """Accept whole minutes up to a day, where 0 turns the warning off."""
    # bool is a subclass of int, so compare the exact type.
    if type(value) is not int or not 0 <= value <= MAX_OPEN_WARNING:
        raise vol.Invalid(f"expected whole minutes from 0 to {MAX_OPEN_WARNING}")
    return value


APPEARANCE_SCHEMA: Final = vol.Schema(
    {
        vol.Optional("width"): vol.In(("single", "double")),
        vol.Optional("style"): _SLUG,
        vol.Optional("color"): _COLOR,
        vol.Optional("windows"): _SLUG,
        vol.Optional("glass"): _SLUG,
        vol.Optional("hardware"): bool,
        vol.Optional("trim"): _COLOR,
    }
)
SETTINGS_SCHEMA: Final = vol.Schema(
    {
        vol.Optional("confirm"): bool,
        vol.Optional("order"): vol.All([_DEVICE_ID], vol.Length(max=MAX_DEVICES)),
        vol.Optional("open_warning"): _minutes,
    }
)


class StoredPanel(TypedDict):
    appearance: dict[str, dict[str, Any]]
    settings: dict[str, Any]


class DoorPayload(TypedDict):
    device_id: str
    name: str
    model: str | None
    entities: dict[str, str]


class CameraPayload(TypedDict):
    device_id: str
    name: str
    model: str | None
    entity_id: str


class AccountPayload(TypedDict):
    entry_id: str
    state: str
    title: NotRequired[str]


class PanelPayload(TypedDict):
    doors: list[DoorPayload]
    cameras: list[CameraPayload]
    appearance: dict[str, dict[str, Any]]
    settings: dict[str, Any]
    accounts: list[AccountPayload]


@dataclass(frozen=True, slots=True)
class _Registration:
    title: str
    icon: str
    require_admin: bool


async def async_setup_panel(hass: HomeAssistant) -> None:
    """Create the shared panel manager and its websocket API."""
    panel = MyQPanel(hass)
    hass.data[DATA_PANEL] = panel
    websocket_api.async_register_command(hass, _ws_subscribe)
    websocket_api.async_register_command(hass, _ws_save_appearance)
    websocket_api.async_register_command(hass, _ws_save_settings)
    await panel.async_setup()


class MyQPanel:
    """Register the sidebar panel and serve its door inventory and appearance settings."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._store: Store[StoredPanel] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._data = StoredPanel(appearance={}, settings={})
        self._lock = asyncio.Lock()
        self._module_url: str | None = None
        self._registration: _Registration | None = None
        self._listeners: set[Callable[[], None]] = set()
        self._unsub_registries: list[Callable[[], None]] = []

    async def async_setup(self) -> None:
        self._data = _stored_panel(await self._store.async_load())
        async_dispatcher_connect(self.hass, SIGNAL_CONFIG_ENTRY_CHANGED, self._async_entry_changed)
        await self.async_refresh()

    async def async_refresh(self) -> None:
        """Serve the frontend while any entry exists, then match the sidebar to the options."""
        if self._entries():
            async with self._lock:
                await self._async_serve_frontend()
        self._async_apply()

    @callback
    def _async_apply(self) -> None:
        registration = self._desired_registration()
        if registration is None:
            if self._registration is not None:
                frontend.async_remove_panel(self.hass, PANEL_URL_PATH, warn_if_unknown=False)
                self._registration = None
        elif registration != self._registration and self._module_url is not None:
            frontend.async_register_built_in_panel(
                self.hass,
                "custom",
                sidebar_title=registration.title,
                sidebar_icon=registration.icon,
                frontend_url_path=PANEL_URL_PATH,
                config={
                    "_panel_custom": {
                        "name": PANEL_COMPONENT,
                        "module_url": self._module_url,
                        "embed_iframe": False,
                        "trust_external": False,
                    }
                },
                require_admin=registration.require_admin,
                update=True,
            )
            self._registration = registration
        self._async_notify()

    @callback
    def async_payload(self, *, is_admin: bool, every_account: bool = False) -> PanelPayload:
        """Describe the doors and cameras of the entries that show the panel, or of all entries."""
        device_registry = dr.async_get(self.hass)
        entity_registry = er.async_get(self.hass)
        doors: list[DoorPayload] = []
        cameras: list[CameraPayload] = []
        accounts: list[AccountPayload] = []
        for entry in self._entries() if every_account else self._panel_entries():
            account = AccountPayload(entry_id=entry.entry_id, state=entry.state.value)
            if is_admin:
                account["title"] = entry.title
            accounts.append(account)
            for device in dr.async_entries_for_config_entry(device_registry, entry.entry_id):
                _add_device(entity_registry, entry, device, doors, cameras)
        doors.sort(key=lambda door: (door["name"].casefold(), door["device_id"]))
        cameras.sort(key=lambda camera: (camera["name"].casefold(), camera["device_id"]))
        known = {item["device_id"] for item in (*doors, *cameras)}
        return PanelPayload(
            doors=doors,
            cameras=cameras,
            appearance={
                device_id: dict(appearance)
                for device_id, appearance in self._data["appearance"].items()
                if device_id in known
            },
            settings=dict(self._data["settings"]),
            accounts=accounts,
        )

    @callback
    def async_subscribe(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Call the listener whenever the payload may have changed."""
        if not self._listeners:
            self._unsub_registries = [
                self.hass.bus.async_listen(
                    er.EVENT_ENTITY_REGISTRY_UPDATED, self._async_registry_updated
                ),
                self.hass.bus.async_listen(
                    dr.EVENT_DEVICE_REGISTRY_UPDATED, self._async_registry_updated
                ),
            ]
        self._listeners.add(listener)

        @callback
        def unsubscribe() -> None:
            self._listeners.discard(listener)
            if not self._listeners:
                for unsub in self._unsub_registries:
                    unsub()
                self._unsub_registries = []

        return unsubscribe

    async def async_save_appearance(
        self, appearances: Mapping[str, Mapping[str, Any] | None]
    ) -> None:
        """Store the look of each listed door, or reset it to the default when None."""
        device_registry = dr.async_get(self.hass)
        for device_id in appearances:
            device = device_registry.async_get(device_id)
            if device is None or not any(domain == DOMAIN for domain, _ in device.identifiers):
                raise ValueError(f"Unknown MyQ device: {device_id}")
        stored = {
            device_id: value
            for device_id, value in self._data["appearance"].items()
            if device_registry.async_get(device_id) is not None
        }
        for device_id, appearance in appearances.items():
            if appearance is None:
                stored.pop(device_id, None)
            else:
                stored[device_id] = dict(appearance)
        await self._async_save(StoredPanel(appearance=stored, settings=self._data["settings"]))

    async def async_save_settings(self, settings: Mapping[str, Any]) -> None:
        """Merge panel-wide preferences into the stored settings."""
        await self._async_save(
            StoredPanel(
                appearance=self._data["appearance"],
                settings={**self._data["settings"], **settings},
            )
        )

    async def _async_save(self, data: StoredPanel) -> None:
        self._data = data
        await self._store.async_save(data)
        self._async_notify()

    async def _async_serve_frontend(self) -> bool:
        if self._module_url is not None:
            return True
        if "http" not in self.hass.config.components:
            _LOGGER.debug("Skipping the MyQ panel because the HTTP integration is not loaded")
            return False
        version = await self.hass.async_add_executor_job(_frontend_version)
        url = f"{STATIC_URL_PREFIX}/{version}"
        await self.hass.http.async_register_static_paths(
            [StaticPathConfig(url, str(FRONTEND_PATH), cache_headers=True)]
        )
        self._module_url = f"{url}/{PANEL_MODULE}"
        # Load the dashboard card on every frontend page, so dashboards can use it directly.
        if frontend.DATA_EXTRA_MODULE_URL in self.hass.data:
            frontend.add_extra_js_url(self.hass, f"{url}/{CARD_MODULE}")
        return True

    def _entries(self) -> list[ConfigEntry]:
        return self.hass.config_entries.async_entries(
            DOMAIN, include_ignore=False, include_disabled=False
        )

    def _panel_entries(self) -> list[ConfigEntry]:
        return [entry for entry in self._entries() if panel_options(entry.options)["panel_enabled"]]

    def _desired_registration(self) -> _Registration | None:
        options = [panel_options(entry.options) for entry in self._panel_entries()]
        if not options:
            return None
        return _Registration(
            title=options[0]["panel_title"],
            icon=options[0]["panel_icon"],
            require_admin=any(option["panel_require_admin"] for option in options),
        )

    @callback
    def _async_entry_changed(self, change: ConfigEntryChange, entry: ConfigEntry) -> None:
        del change
        if entry.domain != DOMAIN:
            return
        if self._module_url is None and self._entries():
            self.hass.async_create_task(self.async_refresh(), eager_start=True)
        else:
            self._async_apply()

    @callback
    def _async_registry_updated(self, event: Event[Any]) -> None:
        del event
        self._async_notify()

    @callback
    def _async_notify(self) -> None:
        for listener in list(self._listeners):
            listener()


def _add_device(
    entity_registry: er.EntityRegistry,
    entry: ConfigEntry,
    device: dr.DeviceEntry,
    doors: list[DoorPayload],
    cameras: list[CameraPayload],
) -> None:
    serial = next((value for domain, value in device.identifiers if domain == DOMAIN), None)
    if serial is None:
        return
    entities: dict[str, str] = {}
    for entity in er.async_entries_for_device(entity_registry, device.id):
        if entity.platform != DOMAIN or entity.config_entry_id != entry.entry_id:
            continue
        if entity.unique_id == serial:
            entities[entity.domain] = entity.entity_id
        elif entity.unique_id.startswith(f"{serial}_"):
            entities[entity.unique_id.removeprefix(f"{serial}_")] = entity.entity_id
    name = device.name_by_user or device.name or ""
    if "cover" in entities:
        doors.append(
            DoorPayload(device_id=device.id, name=name, model=device.model, entities=entities)
        )
    elif "camera" in entities:
        cameras.append(
            CameraPayload(
                device_id=device.id, name=name, model=device.model, entity_id=entities["camera"]
            )
        )


def _stored_panel(data: Mapping[str, Any] | None) -> StoredPanel:
    """Return valid stored settings, dropping anything a newer or damaged file contains."""
    stored = StoredPanel(appearance={}, settings={})
    if not isinstance(data, Mapping):
        return stored
    appearance = data.get("appearance")
    if isinstance(appearance, Mapping):
        for device_id, value in appearance.items():
            try:
                stored["appearance"][_DEVICE_ID(device_id)] = APPEARANCE_SCHEMA(value)
            except vol.Invalid:
                _LOGGER.debug("Ignoring invalid stored MyQ panel appearance")
    settings = data.get("settings")
    if isinstance(settings, Mapping):
        try:
            stored["settings"] = SETTINGS_SCHEMA(dict(settings))
        except vol.Invalid:
            _LOGGER.debug("Ignoring invalid stored MyQ panel settings")
    return stored


def _frontend_version() -> str:
    """Fingerprint the panel files so browsers fetch new code after every upgrade."""
    digest = hashlib.sha256()
    for path in sorted(FRONTEND_PATH.rglob("*")):
        if path.is_file():
            digest.update(path.relative_to(FRONTEND_PATH).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


@websocket_command(
    {
        vol.Required("type"): "myq/panel/subscribe",
        # The sidebar lists the accounts that show it; dashboard cards can use any account.
        vol.Optional("scope", default="panel"): vol.In(("panel", "all")),
    }
)
@callback
def _ws_subscribe(hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]) -> None:
    """Send the panel payload now and again whenever it changes."""
    panel = hass.data[DATA_PANEL]
    is_admin = connection.user.is_admin
    every_account = msg["scope"] == "all"
    last: PanelPayload | None = None

    @callback
    def send() -> None:
        nonlocal last
        payload = panel.async_payload(is_admin=is_admin, every_account=every_account)
        if payload != last:
            last = payload
            connection.send_message(event_message(msg["id"], payload))

    connection.subscriptions[msg["id"]] = panel.async_subscribe(send)
    connection.send_result(msg["id"])
    send()


@websocket_command(
    {
        vol.Required("type"): "myq/panel/save_appearance",
        vol.Required("appearance"): vol.All(
            {_DEVICE_ID: vol.Any(None, APPEARANCE_SCHEMA)},
            vol.Length(min=1, max=MAX_DEVICES),
        ),
    }
)
@require_admin
@async_response
async def _ws_save_appearance(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    try:
        await hass.data[DATA_PANEL].async_save_appearance(msg["appearance"])
    except ValueError as error:
        connection.send_error(msg["id"], ERR_NOT_FOUND, str(error))
        return
    connection.send_result(msg["id"])


@websocket_command(
    {
        vol.Required("type"): "myq/panel/save_settings",
        vol.Required("settings"): SETTINGS_SCHEMA,
    }
)
@require_admin
@async_response
async def _ws_save_settings(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    await hass.data[DATA_PANEL].async_save_settings(msg["settings"])
    connection.send_result(msg["id"])
