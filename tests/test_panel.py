"""The sidebar panel follows entry options and serves door inventory and appearance."""

import re
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components import frontend
from homeassistant.config_entries import ConfigEntryDisabler
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.typing import (
    ClientSessionGenerator,
    MockHAClientWebSocket,
    WebSocketGenerator,
)

from custom_components.myq.const import (
    CONF_CAMERA_LAN_ONLY,
    CONF_EMAIL,
    CONF_MFA_METHOD,
    CONF_PANEL_ENABLED,
    CONF_PANEL_ICON,
    CONF_PANEL_REQUIRE_ADMIN,
    CONF_PANEL_TITLE,
    CONF_TOKENS,
    DOMAIN,
    MFA_METHOD_EMAIL,
)
from custom_components.myq.models import GarageDoor, MyQCamera, MyQDevices
from custom_components.myq.panel import (
    DOOR_COLORS,
    DOOR_GLASS,
    DOOR_STYLES,
    DOOR_WIDTHS,
    DOOR_WINDOWS,
    FRONTEND_PATH,
    STORAGE_KEY,
    TRIM_COLORS,
    MyQPanel,
    _frontend_version,
    _stored_panel,
)

EMAIL = "driver@example.com"
ATTACHED = MyQCamera("TC-0005-10000001", True, "Integrated camera")
STANDALONE = MyQCamera("TC-0007-20000001", True, "vkp-camera", "Front entrance")
DOOR = GarageDoor(
    "account-1",
    "door-1",
    "Main garage",
    "Wi-Fi GDO",
    "closed",
    True,
    in_vacation_mode=False,
    attached_worklight_on=True,
    absolute_cycle_count=12,
    camera=ATTACHED,
)
OTHER_DOOR = GarageDoor("account-2", "door-2", "Barn", "Wi-Fi GDO", "open", True)
SHOWN = {CONF_PANEL_ENABLED: True}
PANEL_OPTIONS = {
    CONF_PANEL_ENABLED: True,
    CONF_PANEL_TITLE: "Garage",
    CONF_PANEL_ICON: "mdi:garage",
    CONF_PANEL_REQUIRE_ADMIN: True,
}


def _entry(email: str = EMAIL, options: dict[str, Any] | None = None) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=email,
        title=email,
        options=options or {},
        data={
            CONF_EMAIL: email,
            CONF_MFA_METHOD: MFA_METHOD_EMAIL,
            CONF_TOKENS: {
                "access_token": "access",
                "refresh_token": "refresh",
                "expires_at": 9876543210.0,
            },
        },
    )


@contextmanager
def _clients(*device_sets: MyQDevices) -> Iterator[None]:
    """Give each set-up entry its own mocked client, in setup order."""
    clients = []
    for devices in device_sets:
        client = MagicMock()
        client.async_get_devices = AsyncMock(return_value=devices)
        clients.append(client)
    with patch("custom_components.myq.MyQClient", side_effect=clients):
        yield


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def _panel(hass: HomeAssistant) -> frontend.Panel | None:
    return hass.data.get(frontend.DATA_PANELS, {}).get(DOMAIN)


async def _call(
    client: MockHAClientWebSocket, message: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Send a command and return its result plus any subscription events received first."""
    await client.send_json_auto_id(message)
    events: list[dict[str, Any]] = []
    while True:
        response = await client.receive_json()
        if response["type"] == "result" and response["id"] == message["id"]:
            return response, events
        events.append(response["event"])


@pytest.fixture
async def ws_client(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator
) -> AsyncIterator[MockHAClientWebSocket]:
    """Load HTTP and the websocket API before MyQ, as Home Assistant does at startup."""
    yield await hass_ws_client(hass)


async def test_panel_follows_entry_options_and_lifecycle(
    hass: HomeAssistant,
    ws_client: MockHAClientWebSocket,
    hass_client: ClientSessionGenerator,
) -> None:
    del ws_client
    entry = _entry()
    with _clients(MyQDevices((DOOR,)), MyQDevices((DOOR,)), MyQDevices((DOOR,))):
        await _setup(hass, entry)

        # The sidebar page is off until an account turns it on.
        assert _panel(hass) is None
        hass.config_entries.async_update_entry(entry, options=SHOWN)
        await hass.async_block_till_done()

        panel = _panel(hass)
        assert panel is not None
        assert (panel.sidebar_title, panel.sidebar_icon, panel.require_admin) == (
            "MyQ",
            "mdi:garage-variant",
            False,
        )
        assert panel.config is not None
        custom = panel.config["_panel_custom"]
        assert custom["name"] == "myq-panel"
        assert custom["embed_iframe"] is False
        module_url = custom["module_url"]
        assert re.fullmatch(r"/myq_panel/[0-9a-f]{12}/myq-panel\.js", module_url)

        http = await hass_client()
        module = await http.get(module_url)
        assert module.status == 200
        assert 'customElements.define("myq-panel"' in await module.text()
        strings = await http.get(module_url.replace("myq-panel.js", "i18n/en.json"))
        assert strings.status == 200
        assert (await strings.json())["door"]["open"] == "Open"

        hass.config_entries.async_update_entry(entry, options=PANEL_OPTIONS)
        await hass.async_block_till_done()
        panel = _panel(hass)
        assert panel is not None
        assert (panel.sidebar_title, panel.sidebar_icon, panel.require_admin) == (
            "Garage",
            "mdi:garage",
            True,
        )
        assert panel.config is not None
        assert panel.config["_panel_custom"]["module_url"] == module_url

        hass.config_entries.async_update_entry(
            entry, options={**PANEL_OPTIONS, CONF_PANEL_ENABLED: False}
        )
        await hass.async_block_till_done()
        assert _panel(hass) is None

        hass.config_entries.async_update_entry(entry, options=SHOWN)
        await hass.async_block_till_done()
        assert _panel(hass) is not None

        # The panel stays while an entry reloads or retries, so the page never disappears.
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        assert _panel(hass) is not None
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        await hass.config_entries.async_set_disabled_by(entry.entry_id, ConfigEntryDisabler.USER)
        await hass.async_block_till_done()
        assert _panel(hass) is None

        await hass.config_entries.async_set_disabled_by(entry.entry_id, None)
        await hass.async_block_till_done()
        assert _panel(hass) is not None

        await hass.config_entries.async_remove(entry.entry_id)
        await hass.async_block_till_done()
        assert _panel(hass) is None


async def test_panel_combines_accounts_that_show_it(
    hass: HomeAssistant, ws_client: MockHAClientWebSocket
) -> None:
    first = _entry(options={**SHOWN, CONF_PANEL_TITLE: "Home"})
    second = _entry("second@example.com", options={**PANEL_OPTIONS, CONF_PANEL_TITLE: "Cabin"})
    with _clients(MyQDevices((DOOR,)), MyQDevices((OTHER_DOOR,))):
        await _setup(hass, first)
        await _setup(hass, second)

    panel = _panel(hass)
    assert panel is not None
    assert (panel.sidebar_title, panel.require_admin) == ("Home", True)
    response, events = await _call(ws_client, {"type": "myq/panel/subscribe"})
    assert response["success"]
    payload = await ws_client.receive_json()
    assert [door["name"] for door in payload["event"]["doors"]] == ["Barn", "Main garage"]
    assert not events

    hass.config_entries.async_update_entry(first, options={CONF_PANEL_ENABLED: False})
    await hass.async_block_till_done()
    panel = _panel(hass)
    assert panel is not None
    assert (panel.sidebar_title, panel.require_admin) == ("Cabin", True)
    event = await ws_client.receive_json()
    assert [door["name"] for door in event["event"]["doors"]] == ["Barn"]
    assert [account["entry_id"] for account in event["event"]["accounts"]] == [second.entry_id]


async def test_panel_files_need_the_http_integration(hass: HomeAssistant) -> None:
    assert not await MyQPanel(hass)._async_serve_frontend()


async def test_dashboard_card_is_offered_without_the_sidebar_panel(
    hass: HomeAssistant,
    ws_client: MockHAClientWebSocket,
    hass_client: ClientSessionGenerator,
) -> None:
    # The frontend integration needs the built frontend package, so stand in for its module list.
    hass.data[frontend.DATA_EXTRA_MODULE_URL] = frontend.UrlManager(lambda *_: None, [])
    with _clients(MyQDevices((DOOR,))):
        await _setup(hass, _entry())

    assert _panel(hass) is None
    (card_url,) = hass.data[frontend.DATA_EXTRA_MODULE_URL].urls
    assert re.fullmatch(r"/myq_panel/[0-9a-f]{12}/myq-card\.js", card_url)
    module = await (await hass_client()).get(card_url)
    assert module.status == 200
    assert 'customElements.define("myq-door-card"' in await module.text()

    # Cards can show every account; the sidebar only lists accounts that enable it.
    response, _ = await _call(ws_client, {"type": "myq/panel/subscribe", "scope": "all"})
    assert response["success"]
    assert [door["name"] for door in (await ws_client.receive_json())["event"]["doors"]] == [
        "Main garage"
    ]
    response, _ = await _call(ws_client, {"type": "myq/panel/subscribe"})
    assert response["success"]
    assert (await ws_client.receive_json())["event"]["doors"] == []
    response, _ = await _call(ws_client, {"type": "myq/panel/subscribe", "scope": "everything"})
    assert response["error"]["code"] == "invalid_format"


async def test_subscription_describes_devices_and_follows_registry_changes(
    hass: HomeAssistant, ws_client: MockHAClientWebSocket
) -> None:
    entry = _entry(options=SHOWN)
    entry.add_to_hass(hass)
    # Disabled entities are left out; disable one before setup to avoid a delayed reload.
    er.async_get(hass).async_get_or_create(
        "sensor",
        DOMAIN,
        "door-1_absolute_cycle_count",
        config_entry=entry,
        disabled_by=er.RegistryEntryDisabler.USER,
    )
    with _clients(MyQDevices((DOOR,), (ATTACHED, STANDALONE))):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    response, _ = await _call(ws_client, {"type": "myq/panel/subscribe"})
    assert response["success"]
    payload = (await ws_client.receive_json())["event"]

    devices = dr.async_get(hass)
    entities = er.async_get(hass)
    door_device = devices.async_get_device(identifiers={(DOMAIN, DOOR.serial_number)})
    camera_device = devices.async_get_device(identifiers={(DOMAIN, STANDALONE.serial_number)})
    assert door_device is not None
    assert camera_device is not None

    def entity_id(platform: str, unique_id: str) -> str:
        found = entities.async_get_entity_id(platform, DOMAIN, unique_id)
        assert found is not None
        return found

    assert payload == {
        "doors": [
            {
                "device_id": door_device.id,
                "name": "Main garage",
                "model": "Wi-Fi GDO",
                "entities": {
                    "cover": entity_id("cover", "door-1"),
                    "door_open": entity_id("binary_sensor", "door-1_door_open"),
                    "vacation_mode": entity_id("binary_sensor", "door-1_vacation_mode"),
                    "work_light": entity_id("binary_sensor", "door-1_work_light"),
                    "active_fault": entity_id("binary_sensor", "door-1_active_fault"),
                    "camera": entity_id("camera", "door-1_camera"),
                },
            }
        ],
        "cameras": [
            {
                "device_id": camera_device.id,
                "name": "Front entrance",
                "model": "vkp-camera",
                "entity_id": entity_id("camera", f"{STANDALONE.serial_number}_camera"),
            }
        ],
        "appearance": {},
        "settings": {},
        "accounts": [{"entry_id": entry.entry_id, "state": "loaded", "title": EMAIL}],
    }

    entities.async_update_entity(entity_id("cover", "door-1"), new_entity_id="cover.driveway")
    await hass.async_block_till_done()
    event = (await ws_client.receive_json())["event"]
    assert event["doors"][0]["entities"]["cover"] == "cover.driveway"

    devices.async_update_device(door_device.id, name_by_user="Driveway")
    await hass.async_block_till_done()
    event = (await ws_client.receive_json())["event"]
    assert event["doors"][0]["name"] == "Driveway"


async def test_appearance_and_settings_are_validated_stored_and_shared(
    hass: HomeAssistant,
    ws_client: MockHAClientWebSocket,
    hass_storage: dict[str, Any],
) -> None:
    with _clients(MyQDevices((DOOR,))):
        await _setup(hass, _entry(options=SHOWN))
    door_device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, DOOR.serial_number)})
    assert door_device is not None
    response, _ = await _call(ws_client, {"type": "myq/panel/subscribe"})
    assert response["success"]
    await ws_client.receive_json()

    appearance = {
        "width": "double",
        "style": "carriage",
        "color": "#336699",
        "windows": "arched",
        "glass": "frosted",
        "hardware": False,
        "trim": "black",
    }
    response, events = await _call(
        ws_client,
        {"type": "myq/panel/save_appearance", "appearance": {door_device.id: appearance}},
    )
    assert response["success"]
    assert events[-1]["appearance"] == {door_device.id: appearance}
    assert hass_storage[STORAGE_KEY]["data"]["appearance"] == {door_device.id: appearance}

    for invalid in (
        {"style": "Raised Panel"},
        {"style": "castle"},
        {"color": "#GGGGGG"},
        {"color": "plaid"},
        {"windows": "round"},
        {"glass": "mirror"},
        {"trim": "Bright White"},
        {"trim": "cedar"},
        {"width": "triple"},
        {"x": 1},
    ):
        response, _ = await _call(
            ws_client,
            {"type": "myq/panel/save_appearance", "appearance": {door_device.id: invalid}},
        )
        assert not response["success"]
        assert response["error"]["code"] == "invalid_format"

    other = MockConfigEntry(domain="other")
    other.add_to_hass(hass)
    foreign = dr.async_get(hass).async_get_or_create(
        config_entry_id=other.entry_id, identifiers={("other", "device")}
    )
    for device_id in ("missing-device", foreign.id):
        response, _ = await _call(
            ws_client,
            {"type": "myq/panel/save_appearance", "appearance": {device_id: {"style": "glass"}}},
        )
        assert response["error"]["code"] == "not_found"

    response, events = await _call(
        ws_client,
        {
            "type": "myq/panel/save_settings",
            "settings": {"confirm": True, "order": [door_device.id]},
        },
    )
    assert response["success"]
    assert events[-1]["settings"] == {"confirm": True, "order": [door_device.id]}

    response, events = await _call(
        ws_client, {"type": "myq/panel/save_appearance", "appearance": {door_device.id: None}}
    )
    assert response["success"]
    assert events[-1]["appearance"] == {}
    assert hass_storage[STORAGE_KEY]["data"] == {
        "appearance": {},
        "settings": {"confirm": True, "order": [door_device.id]},
    }


async def test_open_warning_takes_whole_minutes_up_to_a_day(
    hass: HomeAssistant, ws_client: MockHAClientWebSocket
) -> None:
    with _clients(MyQDevices((DOOR,))):
        await _setup(hass, _entry())

    for invalid in (True, -1, 1441, 7.5, "30"):
        response, _ = await _call(
            ws_client, {"type": "myq/panel/save_settings", "settings": {"open_warning": invalid}}
        )
        assert response["error"]["code"] == "invalid_format", invalid
    for minutes in (0, 1440, 45):
        response, _ = await _call(
            ws_client, {"type": "myq/panel/save_settings", "settings": {"open_warning": minutes}}
        )
        assert response["success"]

    response, _ = await _call(ws_client, {"type": "myq/panel/subscribe"})
    assert response["success"]
    assert (await ws_client.receive_json())["event"]["settings"] == {"open_warning": 45}
    assert _stored_panel({"settings": {"open_warning": False}}) == {
        "appearance": {},
        "settings": {},
    }


async def test_only_administrators_change_the_panel(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    hass_read_only_access_token: str,
) -> None:
    client = await hass_ws_client(hass, hass_read_only_access_token)
    entry = _entry(options=SHOWN)
    with _clients(MyQDevices((DOOR,))):
        await _setup(hass, entry)
    door_device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, DOOR.serial_number)})
    assert door_device is not None

    response, _ = await _call(client, {"type": "myq/panel/subscribe"})
    assert response["success"]
    payload = (await client.receive_json())["event"]
    assert payload["accounts"] == [{"entry_id": entry.entry_id, "state": "loaded"}]
    assert payload["doors"][0]["name"] == "Main garage"

    for message in (
        {"type": "myq/panel/save_appearance", "appearance": {door_device.id: {"style": "glass"}}},
        {"type": "myq/panel/save_settings", "settings": {"confirm": True}},
    ):
        response, _ = await _call(client, message)
        assert response["error"]["code"] == "unauthorized"


async def test_stored_appearance_is_loaded_and_invalid_values_are_dropped(
    hass: HomeAssistant,
    ws_client: MockHAClientWebSocket,
    hass_storage: dict[str, Any],
) -> None:
    devices = dr.async_get(hass)
    entry = _entry(options=SHOWN)
    entry.add_to_hass(hass)
    door_device = devices.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, DOOR.serial_number)}
    )
    hass_storage[STORAGE_KEY] = {
        "version": 1,
        "minor_version": 1,
        "key": STORAGE_KEY,
        "data": {
            "appearance": {door_device.id: {"style": "plank"}, "other": {"style": "BAD"}},
            "settings": {"confirm": True},
        },
    }
    with _clients(MyQDevices((DOOR,))):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    response, _ = await _call(ws_client, {"type": "myq/panel/subscribe"})
    assert response["success"]
    payload = (await ws_client.receive_json())["event"]
    assert payload["appearance"] == {door_device.id: {"style": "plank"}}
    assert payload["settings"] == {"confirm": True}


def test_stored_panel_data_is_sanitized() -> None:
    assert _stored_panel(None) == {"appearance": {}, "settings": {}}
    assert _stored_panel({"appearance": [], "settings": "x"}) == {"appearance": {}, "settings": {}}
    assert _stored_panel(
        {
            "appearance": {
                "keep": {"style": "glass", "hardware": True},
                "bad-value": {"hardware": "yes"},
                "bad-shape": "glass",
                "": {"style": "glass"},
            },
            "settings": {"confirm": "yes"},
        }
    ) == {"appearance": {"keep": {"style": "glass", "hardware": True}}, "settings": {}}


def test_appearance_choices_match_the_door_drawing() -> None:
    source = (FRONTEND_PATH / "door-scene.js").read_text(encoding="utf-8")

    def js_list(name: str) -> str:
        found = re.search(rf"const {name} = \[(.*?)\];", source, re.DOTALL)
        assert found is not None, name
        return found.group(1)

    def names(name: str) -> tuple[str, ...]:
        return tuple(re.findall(r'"([^"]+)"', js_list(name)))

    assert names("WIDTHS") == DOOR_WIDTHS
    assert names("STYLES") == DOOR_STYLES
    assert names("GLASS") == DOOR_GLASS
    assert {*names("PANEL_WINDOWS"), *names("MODERN_WINDOWS")} == set(DOOR_WINDOWS)
    colors = re.findall(
        r'\{ id: "(\w+)", hex: "#[0-9a-f]{6}"(, finish: "\w+")? \}', js_list("DOOR_COLORS")
    )
    assert tuple(color for color, _ in colors) == DOOR_COLORS
    assert tuple(color for color, finish in colors if not finish) == TRIM_COLORS


def test_frontend_version_fingerprints_panel_files() -> None:
    version = _frontend_version()
    assert re.fullmatch(r"[0-9a-f]{12}", version)
    assert _frontend_version() == version


async def test_options_flow_configures_the_sidebar_panel(hass: HomeAssistant) -> None:
    entry = _entry()
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"
    schema = result["data_schema"]
    assert schema is not None
    # Every switch has a default, so one option can be changed without sending the others.
    assert schema({}) == {
        CONF_CAMERA_LAN_ONLY: False,
        CONF_PANEL_ENABLED: False,
        CONF_PANEL_REQUIRE_ADMIN: False,
    }
    suggested = {
        str(key): key.description["suggested_value"] for key in schema.schema if key.description
    }
    assert suggested == {CONF_PANEL_TITLE: "MyQ", CONF_PANEL_ICON: "mdi:garage-variant"}

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_PANEL_ENABLED: True,
            CONF_PANEL_TITLE: "  Garage  ",
            CONF_PANEL_ICON: "mdi:garage",
            CONF_PANEL_REQUIRE_ADMIN: True,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {**PANEL_OPTIONS, CONF_CAMERA_LAN_ONLY: False}

    # The camera option shares the form; changing only it keeps the panel's switches.
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_CAMERA_LAN_ONLY: True}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_CAMERA_LAN_ONLY] is True
    assert entry.options[CONF_PANEL_ENABLED] is True
    assert entry.options[CONF_PANEL_REQUIRE_ADMIN] is True

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_PANEL_ENABLED: False, CONF_PANEL_REQUIRE_ADMIN: False}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {
        CONF_CAMERA_LAN_ONLY: True,
        CONF_PANEL_ENABLED: False,
        CONF_PANEL_TITLE: "MyQ",
        CONF_PANEL_ICON: "mdi:garage-variant",
        CONF_PANEL_REQUIRE_ADMIN: False,
    }
