import json
import re
from pathlib import Path
from string import Formatter

import pytest

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
    return _flatten(json.loads(path.read_text(encoding="utf-8")))


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


PANEL_I18N = INTEGRATION / "frontend" / "i18n"
PANEL_TRANSLATIONS = sorted(path for path in PANEL_I18N.glob("*.json") if path.stem != "en")
PLURAL_FORMS = {"zero", "one", "two", "few", "many", "other"}
PLURAL_CATEGORIES = {
    "cs": {"one", "few", "many", "other"},
    "pl": {"one", "few", "many", "other"},
    "ru": {"one", "few", "many", "other"},
    "zh-Hans": {"other"},
}


def _panel_strings(path: Path) -> dict[str, str | dict[str, str]]:
    """Flatten panel strings, keeping plural forms together as one entry."""

    def walk(node: dict[str, object], prefix: str) -> dict[str, str | dict[str, str]]:
        flat: dict[str, str | dict[str, str]] = {}
        for key, value in node.items():
            name = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict) and value.keys() <= PLURAL_FORMS:
                flat[name] = value
            elif isinstance(value, dict):
                flat.update(walk(value, name))
            else:
                assert isinstance(value, str), name
                flat[name] = value
        return flat

    return walk(json.loads(path.read_text(encoding="utf-8")), "")


PANEL_STRINGS = _panel_strings(PANEL_I18N / "en.json")


def test_panel_translations_cover_every_integration_language() -> None:
    languages = {path.stem for path in TRANSLATIONS}
    assert {path.stem for path in PANEL_I18N.glob("*.json")} == languages
    source = (INTEGRATION / "frontend" / "i18n.js").read_text(encoding="utf-8")
    available = re.search(r"const AVAILABLE = \[([^\]]*)\]", source)
    assert available is not None
    assert set(re.findall(r'"([^"]+)"', available.group(1))) == languages


@pytest.mark.parametrize("path", PANEL_TRANSLATIONS, ids=[path.stem for path in PANEL_TRANSLATIONS])
def test_panel_translation_has_every_string_with_its_placeholders(path: Path) -> None:
    translation = _panel_strings(path)

    assert translation.keys() == PANEL_STRINGS.keys()
    for key, english in PANEL_STRINGS.items():
        text = translation[key]
        if isinstance(english, dict):
            assert isinstance(text, dict), key
            assert text.keys() == PLURAL_CATEGORIES.get(path.stem, {"one", "other"}), key
            for form in text.values():
                assert form.strip(), key
                assert _placeholder_names(form) == _placeholder_names(english["other"]), key
        else:
            assert isinstance(text, str), key
            assert text.strip(), key
            assert _placeholder_names(text) == _placeholder_names(english), key
