import json
from dataclasses import replace
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp import ClientSession

from custom_components.myq.client import MyQClient
from custom_components.myq.exceptions import MyQApiError, MyQUnsupportedDeviceError
from custom_components.myq.opener_settings import OpenerSetting

from .http import FakeResponse, FakeSession
from .test_init import DOOR


@pytest.mark.parametrize(
    ("setting", "value", "payload"),
    [
        (OpenerSetting.LOCK_MODE, False, {"enable_lock_mode": False}),
        (OpenerSetting.TIME_TO_CLOSE, 0, {"time_to_close_setting": 0}),
        (OpenerSetting.TIME_TO_CLOSE, 99, {"time_to_close_setting": 5940}),
        (OpenerSetting.LIGHT_TIMER, 150, {"light_timer_setting": 150}),
        (OpenerSetting.MOTION_LIGHT, True, {"enable_pir_control": True, "enable_motion_wl": True}),
    ],
)
async def test_wire_contract(
    setting: OpenerSetting, value: int | bool, payload: dict[str, object]
) -> None:
    session = FakeSession(request_responses=[FakeResponse("", status=204)])
    auth = MagicMock()
    auth.async_access_token = AsyncMock(return_value="access")
    client = MyQClient(cast(ClientSession, session), auth)
    await client.async_write_opener_setting(replace(DOOR, serial_number="a/b"), setting, value)
    (call,) = session.calls
    assert call.method == "PUT"
    assert call.url.endswith(f"/accounts/{DOOR.account_id}/door_openers/a%2Fb/{setting.value}")
    assert call.kwargs["json"] == payload and call.kwargs["allow_redirects"] is False
    if setting is not OpenerSetting.LOCK_MODE:
        assert setting.read(payload) == value


@pytest.mark.parametrize(
    ("setting", "bad"),
    [
        (OpenerSetting.TIME_TO_CLOSE, -1),
        (OpenerSetting.TIME_TO_CLOSE, 100),
        (OpenerSetting.TIME_TO_CLOSE, True),
        (OpenerSetting.LIGHT_TIMER, 180),
        (OpenerSetting.LOCK_MODE, 1),
        (OpenerSetting.MOTION_LIGHT, 0),
    ],
)
def test_invalid_values_are_rejected(setting: OpenerSetting, bad: int | bool) -> None:
    with pytest.raises(ValueError):
        setting.payload(bad)


async def test_support_errors_and_remote_accessories() -> None:
    session = FakeSession(
        request_responses=[
            FakeResponse("", 400, '{"code":"400.003"}'),
            FakeResponse("", 400, '{"code":"another"}'),
            FakeResponse(
                "", body=json.dumps({"gdo_transmitter_names": [{"transmitter_type": "S3Keypad"}]})
            ),
            FakeResponse(
                "", body=json.dumps({"gdo_transmitter_names": [{"transmitter_type": "FhssTx"}]})
            ),
        ]
    )
    auth = MagicMock()
    auth.async_access_token = AsyncMock(return_value="access")
    client = MyQClient(cast(ClientSession, session), auth)
    with pytest.raises(MyQUnsupportedDeviceError):
        await client.async_read_opener_setting(DOOR, OpenerSetting.LIGHT_TIMER)
    with pytest.raises(MyQApiError, match="HTTP 400"):
        await client.async_read_opener_setting(DOOR, OpenerSetting.LIGHT_TIMER)
    assert await client.async_read_opener_setting(DOOR, OpenerSetting.LOCK_MODE) is None
    assert await client.async_read_opener_setting(DOOR, OpenerSetting.LOCK_MODE) is False
    assert session.calls[-1].url.endswith("/accessories")
    assert OpenerSetting.MOTION_LIGHT.read({"enable_motion_wl": True}) is True
    assert OpenerSetting.MOTION_LIGHT.read({"enable_pir_control": False}) is False
    with pytest.raises(MyQApiError):
        OpenerSetting.TIME_TO_CLOSE.read({"time_to_close_setting": 30})
