from __future__ import annotations

import urllib.parse
from collections.abc import Mapping
from contextlib import suppress
from typing import cast

from aiohttp import ClientSession

from .auth_pages import (
    HttpPage,
    MfaForm,
    consent_form,
    login_form,
    otp_form,
    raise_for_challenge,
    validation_error,
)
from .browser_auth import _BrowserAuthorization
from .const import (
    BROWSER_USER_AGENT,
    IDENTITY_BASE_URL,
    MFA_METHOD_EMAIL,
    MFA_METHOD_SMS,
    OAUTH_REDIRECT_URI,
)
from .exceptions import (
    MyQApiError,
    MyQBrowserSessionExpiredError,
    MyQInvalidCredentialsError,
    MyQInvalidMfaError,
)
from .models import OAuthTokens
from .oauth import async_exchange_code, create_authorization_url


class MyQLoginSession:
    """Carry the cookies and verification context of one sign-in attempt."""

    def __init__(self, session: ClientSession) -> None:
        self._session = session
        self._verifier: str | None = None
        self._mfa_form: MfaForm | None = None
        self._browser_authorization: _BrowserAuthorization | None = None

    async def async_start(
        self,
        email_address: str,
        password: str,
        mfa_method: str,
    ) -> OAuthTokens | None:
        """Submit credentials and return tokens when no verification step is needed."""
        authorization_url, verifier = create_authorization_url()
        self._verifier = verifier
        page = await self._request_page(
            "GET",
            authorization_url,
            headers=_login_headers(),
        )
        authorization_code, page = await self._follow_redirects(page)
        if authorization_code is not None:
            return await self._async_exchange_code(authorization_code)
        raise_for_challenge(page)

        form = login_form(page)
        fields = dict(form.fields)
        fields[cast(str, form.email_field)] = email_address
        fields[cast(str, form.password_field)] = password
        submitted = await self._request_page(
            "POST",
            urllib.parse.urljoin(page.url, form.action),
            data=fields,
            headers=_login_headers(referer=page.url, form_post=True),
        )
        authorization_code, result = await self._follow_redirects(submitted)
        if authorization_code is not None:
            return await self._async_exchange_code(authorization_code)
        raise_for_challenge(result)

        message = validation_error(result.body)
        if message is not None:
            raise MyQInvalidCredentialsError(message)
        authorization_code, result = await self._select_mfa_method(result, mfa_method)
        if authorization_code is not None:
            return await self._async_exchange_code(authorization_code)
        raise_for_challenge(result)
        self._set_mfa_form(result)
        return None

    async def async_submit_mfa(self, code: str) -> OAuthTokens:
        """Exchange a verification code using the current sign-in cookies."""
        if self._mfa_form is None:
            raise MyQApiError("No active MyQ MFA challenge")
        fields = dict(self._mfa_form.fields)
        fields[self._mfa_form.otp_field] = code
        submitted = await self._request_page(
            "POST",
            self._mfa_form.action,
            data=fields,
            headers=_login_headers(
                referer=self._mfa_form.page_url,
                form_post=True,
            ),
        )
        authorization_code, result = await self._follow_redirects(submitted)
        raise_for_challenge(result)
        authorization_code, result = await self._follow_consent(
            authorization_code,
            result,
        )
        if authorization_code is None:
            raise_for_challenge(result)
            message = validation_error(result.body)
            if message is None:
                self._set_mfa_form(result)
            else:
                with suppress(MyQApiError):
                    self._set_mfa_form(result)
            raise MyQInvalidMfaError(message or "MyQ rejected the MFA code")
        return await self._async_exchange_code(authorization_code)

    def start_browser(self) -> str:
        """Create a bounded browser authorization tied to this sign-in attempt."""
        authorization_url, verifier = create_authorization_url()
        self._verifier = verifier
        self._mfa_form = None
        self._browser_authorization = _BrowserAuthorization.create(authorization_url)
        return self._browser_authorization.url

    async def async_complete_browser(self, callback_url: str) -> OAuthTokens:
        """Consume the matching browser callback and exchange its authorization code."""
        if self._browser_authorization is None:
            raise MyQBrowserSessionExpiredError
        authorization_code = self._browser_authorization.consume(callback_url)
        return await self._async_exchange_code(authorization_code)

    async def _async_exchange_code(self, code: str) -> OAuthTokens:
        if self._verifier is None:
            raise MyQApiError("The PKCE verifier is missing")
        return await async_exchange_code(self._session, code, self._verifier)

    async def _follow_redirects(self, page: HttpPage) -> tuple[str | None, HttpPage]:
        current = page
        for _ in range(12):
            if current.location is None:
                return None, current
            target = urllib.parse.urljoin(current.url, current.location)
            if target.startswith(OAUTH_REDIRECT_URI):
                return _redirect_code(target), current
            current = await self._request_page(
                "GET",
                target,
                headers=_login_headers(),
            )
        raise MyQApiError("Too many redirects while completing MyQ sign-in")

    async def _select_mfa_method(
        self,
        page: HttpPage,
        mfa_method: str,
    ) -> tuple[str | None, HttpPage]:
        server_method = {
            MFA_METHOD_EMAIL: "Email",
            MFA_METHOD_SMS: "Sms",
        }.get(mfa_method)
        if server_method is None:
            raise MyQApiError("Unsupported MyQ MFA method")

        form = otp_form(page)
        selected_method = next(
            (
                value
                for name, value in form.fields.items()
                if name.casefold() == "selectedmfamethod"
            ),
            None,
        )
        if selected_method is not None and selected_method.casefold() == server_method.casefold():
            return None, page

        split_url = urllib.parse.urlsplit(page.url)
        query = [
            (name, value)
            for name, value in urllib.parse.parse_qsl(
                split_url.query,
                keep_blank_values=True,
            )
            if name.casefold() != "selectedmfamethod"
        ]
        query.append(("selectedMfaMethod", server_method))
        switch_url = urllib.parse.urlunsplit(
            (
                split_url.scheme,
                split_url.netloc,
                split_url.path,
                urllib.parse.urlencode(query),
                split_url.fragment,
            )
        )
        switched = await self._request_page(
            "GET",
            switch_url,
            headers=_login_headers(referer=page.url),
        )
        return await self._follow_redirects(switched)

    async def _follow_consent(
        self,
        authorization_code: str | None,
        page: HttpPage,
    ) -> tuple[str | None, HttpPage]:
        if authorization_code is not None:
            return authorization_code, page
        if urllib.parse.urlsplit(page.url).path.lower() != "/consent":
            return None, page

        form = consent_form(page.body)
        post_url = urllib.parse.urljoin(page.url, form.action)
        consented = await self._request_page(
            "POST",
            post_url,
            data=form.fields,
            headers=_login_headers(referer=page.url, form_post=True),
        )
        if consented.status == 200:
            return_url = urllib.parse.parse_qs(urllib.parse.urlsplit(post_url).query).get(
                "returnUrl", [""]
            )[0]
            resumed_url = urllib.parse.urljoin(IDENTITY_BASE_URL, return_url)
            resumed = urllib.parse.urlsplit(resumed_url)
            identity = urllib.parse.urlsplit(IDENTITY_BASE_URL)
            if (
                resumed.scheme == identity.scheme
                and resumed.netloc == identity.netloc
                and resumed.path == "/connect/authorize/callback"
            ):
                consented = await self._request_page(
                    "GET",
                    resumed_url,
                    headers=_login_headers(referer=page.url),
                )
        return await self._follow_redirects(consented)

    async def _request_page(
        self,
        method: str,
        url: str,
        *,
        data: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> HttpPage:
        async with self._session.request(
            method,
            url,
            data=data,
            headers=headers,
            allow_redirects=False,
        ) as response:
            return HttpPage(
                url=str(response.url),
                status=response.status,
                location=response.headers.get("Location"),
                body=await response.text(),
            )

    def _set_mfa_form(self, page: HttpPage) -> None:
        form = otp_form(page)
        self._mfa_form = MfaForm(
            page_url=page.url,
            action=urllib.parse.urljoin(page.url, form.action),
            fields=form.fields,
            otp_field=cast(str, form.otp_field),
        )


def _login_headers(
    *,
    referer: str | None = None,
    form_post: bool = False,
) -> dict[str, str]:
    headers = {
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Sec-CH-UA": '"Chromium";v="153", "Google Chrome";v="153", "Not_A Brand";v="99"',
        "Sec-CH-UA-Mobile": "?1",
        "Sec-CH-UA-Platform": '"Android"',
        "User-Agent": BROWSER_USER_AGENT,
        "Upgrade-Insecure-Requests": "1",
    }
    if referer is not None:
        headers["Referer"] = referer
    if form_post:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        headers["Origin"] = IDENTITY_BASE_URL
    return headers


def _redirect_code(redirect_url: str) -> str:
    code = urllib.parse.parse_qs(urllib.parse.urlsplit(redirect_url).query).get("code", [""])[0]
    if not code:
        raise MyQApiError("The MyQ callback did not contain an authorization code")
    return code
