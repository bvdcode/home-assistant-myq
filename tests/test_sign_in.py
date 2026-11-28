"""Sign-in lifecycle and recovery independent of configuration forms."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import ClientConnectionError, ClientSession

from custom_components.myq.const import MFA_METHOD_EMAIL
from custom_components.myq.exceptions import (
    MyQApiError,
    MyQAuthenticationError,
    MyQBrowserSessionExpiredError,
)
from custom_components.myq.sign_in import MyQSignIn


async def test_restarting_credentials_replaces_the_cookie_session() -> None:
    first_session = MagicMock(spec=ClientSession)
    second_session = MagicMock(spec=ClientSession)
    factory = MagicMock(side_effect=[first_session, second_session])
    first_login = MagicMock(async_start=AsyncMock(return_value=None))
    second_login = MagicMock(async_start=AsyncMock(return_value=None))
    with patch(
        "custom_components.myq.sign_in.MyQLoginSession", side_effect=[first_login, second_login]
    ) as login_class:
        sign_in = MyQSignIn(factory)
        factory.assert_not_called()
        await sign_in.async_start("driver@example.com", "first-password", MFA_METHOD_EMAIL)
        first_session.detach.assert_not_called()

        await sign_in.async_start("driver@example.com", "second-password", MFA_METHOD_EMAIL)

        first_session.detach.assert_called_once_with()
        second_session.detach.assert_not_called()
        assert login_class.call_args_list[0].args == (first_session,)
        assert login_class.call_args_list[1].args == (second_session,)
        first_login.async_start.assert_awaited_once_with(
            "driver@example.com", "first-password", MFA_METHOD_EMAIL
        )
        second_login.async_start.assert_awaited_once_with(
            "driver@example.com", "second-password", MFA_METHOD_EMAIL
        )
        sign_in.close()
        second_session.detach.assert_called_once_with()


@pytest.mark.parametrize(
    ("failure", "error"),
    [
        (MyQBrowserSessionExpiredError, "browser_session_expired"),
        (MyQAuthenticationError, "browser_auth_failed"),
        (ClientConnectionError, "cannot_connect"),
        (MyQApiError, "unknown"),
    ],
)
async def test_browser_failure_renews_authorization_in_the_same_session(
    failure: type[Exception], error: str
) -> None:
    factory = MagicMock(return_value=MagicMock(spec=ClientSession))
    with patch("custom_components.myq.sign_in.MyQLoginSession") as login_class:
        login = login_class.return_value
        login.start_browser.side_effect = ["https://example.com/first", "https://example.com/next"]
        login.async_complete_browser = AsyncMock(side_effect=failure)
        sign_in = MyQSignIn(factory)
        sign_in.begin_browser()
        assert sign_in.browser_url == "https://example.com/first"

        result = await sign_in.async_complete_browser("com.myqops://android?code=expired")

        assert result.error == error
        assert result.tokens is None
        assert sign_in.browser_url == "https://example.com/next"
        factory.assert_called_once_with()
        factory.return_value.detach.assert_not_called()
        sign_in.close()


async def test_close_invalidates_pending_sign_in_and_releases_the_session_once() -> None:
    factory = MagicMock(return_value=MagicMock(spec=ClientSession))
    with patch("custom_components.myq.sign_in.MyQLoginSession") as login_class:
        sign_in = MyQSignIn(factory)
        sign_in.begin_browser()

        sign_in.close()
        sign_in.close()

        factory.return_value.detach.assert_called_once_with()
        assert (await sign_in.async_submit_mfa("123456")).error == "authentication_expired"
        result = await sign_in.async_complete_browser("com.myqops://android?code=expired")
        assert result.error == "authentication_expired"
        login_class.return_value.async_submit_mfa.assert_not_called()
        login_class.return_value.async_complete_browser.assert_not_called()
        with pytest.raises(RuntimeError, match="No active MyQ browser authorization"):
            _ = sign_in.browser_url
