"""Exercise localized names and existing entity registry entries through HA setup."""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.myq.const import CONF_EMAIL, CONF_MFA_METHOD, CONF_TOKENS, DOMAIN
from custom_components.myq.keypad_state import POWER_MAX_AGE, KeypadPower
from custom_components.myq.models import MyQCamera, MyQDevices


async def test_localized_keypad_entities_keep_user_names_and_ids(hass: HomeAssistant) -> None:
    hass.config.language = "de"
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_EMAIL: "driver@example.com",
            CONF_MFA_METHOD: "email",
            CONF_TOKENS: {"access_token": "access", "refresh_token": "refresh", "expires_at": 9e9},
        },
    )
    entry.add_to_hass(hass)
    keypad = MyQCamera("TC-0007-20000001", True, "vkp-camera", "Entrance")
    registry = er.async_get(hass)
    existing = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{keypad.serial_number}_keypad_battery",
        config_entry=entry,
        suggested_object_id="front_keypad_charge",
    )
    registry.async_update_entity(existing.entity_id, name="Meine Batterie")
    client = MagicMock()
    client.async_get_devices = AsyncMock(return_value=MyQDevices((), (keypad,)))
    with patch("custom_components.myq.MyQClient", return_value=client):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    battery = registry.async_get(existing.entity_id)
    assert battery is not None and battery.name == "Meine Batterie"
    assert battery.original_name == "Batterie"
    for domain, key, label in [
        ("button", "refresh_power", "Batterie- und Energiezustand aktualisieren"),
        ("binary_sensor", "session_problem", "Sitzungsproblem"),
        ("sensor", "transport", "Videoübertragungsweg"),
    ]:
        entity_id = registry.async_get_entity_id(
            domain, DOMAIN, f"{keypad.serial_number}_keypad_{key}"
        )
        assert entity_id is not None
        item = registry.async_get(entity_id)
        assert item is not None and item.original_name == label
        assert item.translation_key == f"keypad_{key}"
    coordinator = entry.runtime_data.coordinator
    serial = keypad.serial_number
    client.async_get_keypad_power = AsyncMock()
    coordinator._set_keypad_power(serial, KeypadPower(time.time(), 71, "FP"))
    original = coordinator._power_expiry[serial]
    coordinator._set_keypad_power(
        serial, KeypadPower(time.time() - POWER_MAX_AGE + 0.05, 71, "LPDS")
    )
    assert original.cancelled()
    coordinator.async_keypad_changed()
    assert (battery_state := hass.states.get(existing.entity_id)) and battery_state.state == "71"
    power_id = registry.async_get_entity_id("sensor", DOMAIN, f"{serial}_keypad_power_state")
    assert power_id is not None
    assert (power_state := hass.states.get(power_id)) and power_state.state == "lpds"
    assert power_state.attributes["options"] == ["fp", "lpds"]
    await asyncio.sleep(0.08)
    assert hass.states.is_state(existing.entity_id, "unavailable")
    assert hass.states.is_state(power_id, "unavailable")
    client.async_get_keypad_power.assert_not_awaited()
    assert await hass.config_entries.async_unload(entry.entry_id)
