from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, TypedDict

from homeassistant.config_entries import ConfigEntry

from .models import GarageDoor, OAuthTokens, StoredTokens

if TYPE_CHECKING:
    from .client import MyQClient
    from .coordinator import MyQDataUpdateCoordinator


class MyQConfigData(TypedDict):
    """Persisted account identity, verification method and OAuth credentials."""

    email: str
    mfa_method: str
    tokens: StoredTokens


type MyQCoordinatorData = dict[str, GarageDoor]


@dataclass(frozen=True, slots=True)
class MyQRuntimeData:
    """The client and shared coordinator owned by one loaded account entry."""

    client: MyQClient
    coordinator: MyQDataUpdateCoordinator


type MyQConfigEntry = ConfigEntry[MyQRuntimeData]


def tokens_to_data(tokens: OAuthTokens) -> StoredTokens:
    """Serialize credentials using the configuration entry token schema."""
    return StoredTokens(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_at=tokens.expires_at,
    )


def tokens_from_data(data: Mapping[str, object]) -> OAuthTokens:
    """Validate persisted token fields before constructing runtime credentials."""
    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token")
    expires_at = data.get("expires_at")
    if not isinstance(access_token, str) or not isinstance(refresh_token, str):
        raise ValueError("Stored OAuth tokens are invalid")
    if not isinstance(expires_at, int | float):
        raise ValueError("Stored OAuth expiry is invalid")
    return OAuthTokens(access_token, refresh_token, float(expires_at))
