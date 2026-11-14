"""Sidebar panel options stored on each MyQ config entry."""

from collections.abc import Mapping
from typing import TypedDict

from .const import (
    CONF_PANEL_ENABLED,
    CONF_PANEL_ICON,
    CONF_PANEL_REQUIRE_ADMIN,
    CONF_PANEL_TITLE,
    DEFAULT_PANEL_ICON,
    DEFAULT_PANEL_TITLE,
)


class PanelOptions(TypedDict):
    panel_enabled: bool
    panel_title: str
    panel_icon: str
    panel_require_admin: bool


def panel_options(options: Mapping[str, object]) -> PanelOptions:
    """Return complete panel options, filling in defaults for missing or blank values."""
    enabled = options.get(CONF_PANEL_ENABLED)
    require_admin = options.get(CONF_PANEL_REQUIRE_ADMIN)
    return PanelOptions(
        panel_enabled=enabled if isinstance(enabled, bool) else False,
        panel_title=_text(options.get(CONF_PANEL_TITLE)) or DEFAULT_PANEL_TITLE,
        panel_icon=_text(options.get(CONF_PANEL_ICON)) or DEFAULT_PANEL_ICON,
        panel_require_admin=require_admin if isinstance(require_admin, bool) else False,
    )


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""
