from __future__ import annotations

import html
import re
import urllib.parse
from dataclasses import dataclass

from .auth_forms import ParsedForm, parse_forms
from .exceptions import (
    MyQApiError,
    MyQCloudflareChallengeError,
    MyQUnsupportedAuthPageError,
)


@dataclass(frozen=True, slots=True)
class HttpPage:
    """An identity-provider response needed for redirects and form parsing."""

    url: str
    status: int
    location: str | None
    body: str


@dataclass(frozen=True, slots=True)
class MfaForm:
    """The verification endpoint and fields for a pending MFA challenge."""

    page_url: str
    action: str
    fields: dict[str, str]
    otp_field: str


def login_form(page: HttpPage) -> ParsedForm:
    """Select a form with unambiguous email and password fields."""
    form = next(
        (
            candidate
            for candidate in parse_forms(page.body, page.url)
            if candidate.password_field and candidate.email_field
        ),
        None,
    )
    if form is None:
        raise MyQApiError(f"The MyQ sign-in form was not found ({_page_summary(page)})")
    return form


def _page_summary(page: HttpPage) -> str:
    path = urllib.parse.urlsplit(page.url).path or "/"
    title_match = re.search(
        r"<title\b[^>]*>(.*?)</title>",
        page.body,
        re.IGNORECASE | re.DOTALL,
    )
    title = _plain_text(title_match.group(1)) if title_match else ""
    content = _plain_text(page.body)
    parts = [f"HTTP {page.status} at {path}"]
    if title:
        parts.append(f"title={title[:120]!r}")
    if content:
        parts.append(f"content={content[:240]!r}")
    return ", ".join(parts)


def _plain_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value))).strip()


def otp_form(page: HttpPage) -> ParsedForm:
    """Select an OTP form or distinguish an unknown page from an HTTP failure."""
    forms = parse_forms(page.body, page.url)
    form = next(
        (candidate for candidate in forms if candidate.otp_field),
        None,
    )
    if form is None or not 200 <= page.status < 300:
        path = urllib.parse.urlsplit(page.url).path or "/"
        message = (
            "The MyQ MFA form was not recognized "
            f"(HTTP {page.status} at {path}, forms={len(forms)})"
        )
        if 200 <= page.status < 300:
            raise MyQUnsupportedAuthPageError(message)
        raise MyQApiError(message)
    return form


def consent_form(page_html: str) -> ParsedForm:
    """Select the consent form and include its affirmative action."""
    form = next(
        (
            candidate
            for candidate in parse_forms(page_html)
            if "consent" in candidate.action.lower()
        ),
        None,
    )
    if form is None or not form.action:
        raise MyQApiError("The MyQ consent form was not recognized")
    fields = {**form.fields, "button": "yes"}
    return ParsedForm(form.action, fields, None, None, None)


def validation_error(page_html: str) -> str | None:
    """Extract the validation message shown by the identity provider."""
    flattened = re.sub(r"\s+", " ", page_html)
    match = re.search(
        r"validation-summary-errors.*?<ul>(.*?)</ul>|"
        r"field-validation-error[^>]*>(.*?)<",
        flattened,
        re.IGNORECASE,
    )
    if match is None:
        return None
    raw = match.group(1) or match.group(2) or ""
    message = html.unescape(re.sub(r"<[^>]+>", " ", raw)).strip()
    return re.sub(r"\s+", " ", message) or None


def raise_for_challenge(page: HttpPage) -> None:
    """Reject identity pages that require interactive browser verification."""
    authorize_forbidden = (
        page.status == 403
        and urllib.parse.urlsplit(page.url).path.lower() == "/connect/authorize"
        and "Resource not authorized" in page.body
    )
    if authorize_forbidden or any(
        marker in page.body for marker in ("Just a moment", "Verify you are human")
    ):
        raise MyQCloudflareChallengeError
