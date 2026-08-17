"""HTTP client errors, mapped from httpx2 adapter failures."""

from ..base import AppError, UnexpectedAppError


class HttpError(AppError):
    """Base exception for outbound HTTP client errors."""


class HttpRequestError(HttpError):
    """HTTP error with request context."""

    def __init__(self, message: str, *, method: str, url: str) -> None:
        super().__init__(message)
        self.method = method
        self.url = url


class HttpTimeoutError(HttpRequestError):
    """HTTP request exceeded client timeout."""


class HttpTransportError(HttpRequestError):
    """Network-level HTTP failure (DNS, TCP, TLS, connection reset)."""


class HttpResponseError(HttpRequestError):
    """HTTP response returned an error status code."""

    def __init__(
        self,
        message: str,
        *,
        method: str,
        url: str,
        status_code: int,
        body: str = "",
    ) -> None:
        super().__init__(message, method=method, url=url)
        self.status_code = status_code
        self.body = body


class HttpAuthError(HttpRequestError):
    """HTTP authentication error."""


class UnexpectedHttpError(UnexpectedAppError):
    """Unexpected HTTP client error."""

    def __init__(self, message: str, *, method: str, url: str) -> None:
        super().__init__(message)
        self.method = method
        self.url = url
