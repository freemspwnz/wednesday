from httpx2 import HTTPError, HTTPStatusError, TimeoutException, TransportError

from app.exceptions import (
    AppError,
    HttpResponseError,
    HttpTimeoutError,
    HttpTransportError,
    UnexpectedHttpError,
)


def map_httpx_error(exc: BaseException, *, method: str, url: str) -> AppError:
    """Translate httpx2 failures into application-layer HTTP errors."""
    if isinstance(exc, AppError):
        return exc

    if isinstance(exc, TimeoutException):
        return HttpTimeoutError(
            f"HTTP request timed out: {method} {url}",
            method=method,
            url=url,
        )

    if isinstance(exc, TransportError):
        return HttpTransportError(
            f"HTTP transport error: {method} {url}",
            method=method,
            url=url,
        )

    if isinstance(exc, HTTPStatusError):
        status_code = exc.response.status_code
        return HttpResponseError(
            f"HTTP {status_code} for {method} {url}",
            method=method,
            url=url,
            status_code=status_code,
        )

    if isinstance(exc, HTTPError):
        return UnexpectedHttpError(
            f"HTTP error during {method} {url}",
            method=method,
            url=url,
        )

    return UnexpectedHttpError(
        f"Unexpected error during {method} {url}",
        method=method,
        url=url,
    )
