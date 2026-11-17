class MyQError(Exception):
    """Base failure raised by the MyQ client and sign-in flows."""


class MyQAuthenticationError(MyQError):
    """The account authorization was rejected or could not be renewed."""


class MyQInvalidCredentialsError(MyQAuthenticationError):
    """The identity provider rejected the submitted credentials."""


class MyQInvalidMfaError(MyQAuthenticationError):
    """The verification code was rejected without ending the sign-in attempt."""


class MyQCloudflareChallengeError(MyQError):
    """Automatic sign-in encountered an interactive browser challenge."""


class MyQBrowserSessionExpiredError(MyQError):
    """Browser authorization expired or its callback was already consumed."""


class MyQInvalidCallbackError(MyQError):
    """A callback does not belong to the pending browser authorization."""


class MyQApiError(MyQError):
    """A cloud response could not be used by the requested operation."""


class MyQRateLimitError(MyQApiError):
    """A service has asked the client to pause further requests."""

    def __init__(self, retry_after: float) -> None:
        super().__init__("MyQ service requests are temporarily paused")
        self.retry_after = retry_after


class MyQUnsupportedAuthPageError(MyQApiError):
    """A successful identity response contains an unsupported verification page."""


class MyQWakeTimeoutError(MyQApiError):
    """The keypad did not report full power within the wake deadline."""
