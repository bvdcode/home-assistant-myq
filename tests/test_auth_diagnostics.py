"""Classify sign-in responses without including their private contents in errors."""

import pytest

from custom_components.myq.auth_pages import HttpPage, raise_for_auth_block
from custom_components.myq.exceptions import (
    MyQAuthorizationDeniedError,
    MyQCloudflareChallengeError,
)


@pytest.mark.parametrize("status", [200, 403, 503])
@pytest.mark.parametrize("marker", ["Just a moment", "Verify you are human"])
def test_browser_challenges_report_status_and_path_only(status: int, marker: str) -> None:
    page = HttpPage(
        "https://partner-identity.myq-cloud.com/AccountMfa/VerifyOtp?code=private-code"
        "#private-fragment",
        status,
        "com.myqops://android?code=private-callback",
        f"<title>{marker}</title><body>private-body driver@example.com</body>",
    )
    with pytest.raises(MyQCloudflareChallengeError) as error:
        raise_for_auth_block(page)
    assert str(error.value) == (
        f"Interactive browser verification required (HTTP {status} at /AccountMfa/VerifyOtp)"
    )


@pytest.mark.parametrize(
    ("status", "path", "body"),
    [
        (200, "/connect/authorize", "Resource not authorized"),
        (403, "/Account/Login", "Resource not authorized"),
        (403, "/connect/authorize", "Other refusal"),
        (200, "/Account/Login", '<form><input name="Password"></form>'),
    ],
)
def test_unrelated_responses_do_not_claim_an_authorization_block(
    status: int, path: str, body: str
) -> None:
    raise_for_auth_block(
        HttpPage(f"https://partner-identity.myq-cloud.com{path}", status, None, body)
    )


def test_explicit_challenge_takes_precedence_over_generic_denial_text() -> None:
    page = HttpPage(
        "https://partner-identity.myq-cloud.com/connect/authorize",
        403,
        None,
        "<title>Just a moment</title>Resource not authorized",
    )
    with pytest.raises(MyQCloudflareChallengeError):
        raise_for_auth_block(page)


def test_authorization_denial_excludes_request_and_response_details() -> None:
    page = HttpPage(
        "https://partner-identity.myq-cloud.com/connect/authorize?state=private-state",
        403,
        None,
        '{"reason":"Resource not authorized","detail":"private-body"}',
    )
    with pytest.raises(MyQAuthorizationDeniedError) as error:
        raise_for_auth_block(page)
    assert str(error.value) == (
        "Authorization request denied (HTTP 403 at /connect/authorize, "
        "reason=Resource not authorized)"
    )
