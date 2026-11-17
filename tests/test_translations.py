import ast
import json
import re
from pathlib import Path
from string import Formatter

import pytest

from custom_components.myq.binary_sensor import BINARY_SENSOR_DESCRIPTIONS
from custom_components.myq.sensor import SENSOR_DESCRIPTIONS

INTEGRATION = Path(__file__).parents[1] / "custom_components" / "myq"
TRANSLATIONS = sorted((INTEGRATION / "translations").glob("*.json"))
CODE_SPAN = re.compile(r"`[^`]*`")


def _flatten(node: object, prefix: str = "") -> dict[str, str]:
    if isinstance(node, str):
        return {prefix: node}
    assert isinstance(node, dict), prefix
    flat: dict[str, str] = {}
    for key, value in node.items():
        flat.update(_flatten(value, f"{prefix}.{key}" if prefix else key))
    return flat


def _load(path: Path) -> dict[str, str]:
    return _flatten(json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_keys))


def _unique_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    values: dict[str, object] = {}
    for key, value in pairs:
        assert key not in values, f"Duplicate translation key: {key}"
        values[key] = value
    return values


def _placeholder_names(text: str) -> set[str]:
    return {name for _, name, _, _ in Formatter().parse(text) if name is not None}


STRINGS = _load(INTEGRATION / "strings.json")


def test_english_translation_matches_strings() -> None:
    assert _load(INTEGRATION / "translations" / "en.json") == STRINGS


@pytest.mark.parametrize("path", TRANSLATIONS, ids=[path.stem for path in TRANSLATIONS])
def test_translation_has_every_string_with_its_placeholders(path: Path) -> None:
    translation = _load(path)

    assert translation.keys() == STRINGS.keys()
    for key, text in translation.items():
        assert text.strip(), key
        assert _placeholder_names(text) == _placeholder_names(STRINGS[key]), key
        assert CODE_SPAN.findall(text) == CODE_SPAN.findall(STRINGS[key]), key


def test_framework_exceptions_have_translatable_messages() -> None:
    exceptions = {
        "ConfigEntryAuthFailed",
        "ConfigEntryError",
        "ConfigEntryNotReady",
        "HomeAssistantError",
        "UpdateFailed",
    }
    keys: set[str] = set()
    for path in INTEGRATION.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            if node.func.id not in exceptions:
                continue
            keywords = {keyword.arg: keyword.value for keyword in node.keywords}
            domain = keywords.get("translation_domain")
            key = keywords.get("translation_key")
            assert isinstance(domain, ast.Name) and domain.id == "DOMAIN", path
            assert isinstance(key, ast.Constant) and isinstance(key.value, str), path
            keys.add(key.value)

    assert keys
    assert {key for key in keys if f"exceptions.{key}.message" not in STRINGS} == set()


def test_entity_descriptions_have_translated_names_and_word_units() -> None:
    for domain, descriptions in (
        ("binary_sensor", BINARY_SENSOR_DESCRIPTIONS),
        ("sensor", SENSOR_DESCRIPTIONS),
    ):
        for description in descriptions:
            prefix = f"entity.{domain}.{description.translation_key}"
            assert f"{prefix}.name" in STRINGS
    for description in SENSOR_DESCRIPTIONS:
        if description.state_class is not None:
            prefix = f"entity.sensor.{description.translation_key}"
            assert f"{prefix}.unit_of_measurement" in STRINGS
            assert description.native_unit_of_measurement is None


@pytest.mark.parametrize(
    ("sensor", "value"),
    [("battery_backup_state", "charged"), ("last_activation_source", "myq_app")],
)
def test_observed_text_sensor_states_have_translations(sensor: str, value: str) -> None:
    assert f"entity.sensor.{sensor}.state.{value}" in STRINGS
