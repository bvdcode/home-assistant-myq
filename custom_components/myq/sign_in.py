"""Sign-in attempts, recoverable failures and cookie-session lifecycle."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from aiohttp import ClientError, ClientSession

from .auth import MyQLoginSession
from .exceptions import (
    MyQAuthenticationError,
    MyQAuthorizationDeniedError,
    MyQBrowserSessionExpiredError,
    MyQCloudflareChallengeError,
    MyQError,
    MyQInvalidCallbackError,
    MyQInvalidCredentialsError,
    MyQInvalidMfaError,
    MyQUnsupportedAuthPageError,
)
from .models import OAuthTokens

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class LoginAttempt:
    """The tokens, recoverable error or browser continuation of a sign-in step."""

    tokens: OAuthTokens | None = None
    error: str | None = None
    browser_url: str | None = None


class MyQSignIn:
    """Manage sign-in using sessions borrowed from a shared HTTP connector."""

    def __init__(self, session_factory: Callable[[], ClientSession]) -> None:
        self._session_factory = session_factory
        self._login_session: ClientSession | None = None
        self._login: MyQLoginSession | None = None
        self._browser_url: str | None = None

    async def async_start(self, email: str, password: str, mfa_method: str) -> LoginAttempt:
        """Start automatic sign-in with a fresh cookie session."""
        self._create_login_session()
        try:
            tokens = await self._required_login().async_start(
                email,
                password,
                mfa_method,
            )
        except MyQInvalidCredentialsError:
            self.close()
            return LoginAttempt(error="invalid_auth")
        except (
            MyQAuthorizationDeniedError,
            MyQCloudflareChallengeError,
            MyQUnsupportedAuthPageError,
        ) as error:
            return self._browser_fallback(error, step="login")
        except ClientError, TimeoutError:
            self.close()
            return LoginAttempt(error="cannot_connect")
        except MyQError:
            _LOGGER.exception("Unexpected MyQ error while starting authentication")
            self.close()
            return LoginAttempt(error="unknown")
        return LoginAttempt(tokens=tokens)

    async def async_complete_browser(self, callback_url: str) -> LoginAttempt:
        """Complete browser authorization or renew an expired attempt."""
        if self._login is None:
            return LoginAttempt(error="authentication_expired")
        try:
            tokens = await self._required_login().async_complete_browser(callback_url)
        except MyQInvalidCallbackError:
            return LoginAttempt(error="invalid_callback")
        except MyQBrowserSessionExpiredError:
            return self._restart_browser("browser_session_expired")
        except MyQAuthenticationError:
            return self._restart_browser("browser_auth_failed")
        except ClientError, TimeoutError:
            return self._restart_browser("cannot_connect")
        except MyQError:
            _LOGGER.exception("Unexpected MyQ error while completing browser authentication")
            return self._restart_browser("unknown")
        return LoginAttempt(tokens=tokens)

    async def async_submit_mfa(self, code: str) -> LoginAttempt:
        """Verify a code while retaining the session for retryable failures."""
        if self._login is None:
            return LoginAttempt(error="authentication_expired")
        try:
            tokens = await self._required_login().async_submit_mfa(code)
        except MyQInvalidMfaError:
            return LoginAttempt(error="invalid_mfa")
        except (
            MyQAuthorizationDeniedError,
            MyQCloudflareChallengeError,
            MyQUnsupportedAuthPageError,
        ) as error:
            return self._browser_fallback(error, step="MFA verification")
        except ClientError, TimeoutError:
            return LoginAttempt(error="cannot_connect")
        except MyQError:
            _LOGGER.exception("Unexpected MyQ error while submitting MFA")
            self.close()
            return LoginAttempt(error="unknown")
        return LoginAttempt(tokens=tokens)

    def close(self) -> None:
        """Release cookies and sign-in state without closing the shared connector."""
        if self._login_session is not None:
            self._login_session.detach()
        self._login_session = None
        self._login = None
        self._browser_url = None

    def _create_login_session(self) -> None:
        self.close()
        self._login_session = self._session_factory()
        self._login = MyQLoginSession(self._login_session)

    def begin_browser(self) -> None:
        """Begin browser authorization with a fresh sign-in session."""
        self._create_login_session()
        self._start_browser()

    def _start_browser(self) -> str:
        self._browser_url = self._required_login().start_browser()
        return self._browser_url

    def _browser_fallback(
        self,
        error: MyQAuthorizationDeniedError
        | MyQCloudflareChallengeError
        | MyQUnsupportedAuthPageError,
        *,
        step: str,
    ) -> LoginAttempt:
        reason = f"{type(error).__name__}: {error}".rstrip(": ")
        _LOGGER.warning(
            "Automatic MyQ authentication could not continue during %s; "
            "offering browser sign-in: %s",
            step,
            reason,
        )
        return LoginAttempt(browser_url=self._start_browser())

    def _restart_browser(self, error: str) -> LoginAttempt:
        self._start_browser()
        return LoginAttempt(error=error)

    @property
    def browser_url(self) -> str:
        """Return the current browser authorization URL."""
        if self._browser_url is None:
            raise RuntimeError("No active MyQ browser authorization")
        return self._browser_url

    def _required_login(self) -> MyQLoginSession:
        if self._login is None:
            raise RuntimeError("No active MyQ sign-in session")
        return self._login
