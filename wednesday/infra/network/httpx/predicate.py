from http import HTTPStatus

from httpx2 import HTTPStatusError, TimeoutException, TransportError

from app.exceptions import CircuitOpenError, TooManyRequests, iter_exception_chain

NO_RETRY_STATUS_CODES: set[int] = {
    HTTPStatus.BAD_REQUEST,  # 400
    HTTPStatus.UNAUTHORIZED,  # 401
    HTTPStatus.FORBIDDEN,  # 403
    HTTPStatus.NOT_FOUND,  # 404
    HTTPStatus.UNPROCESSABLE_ENTITY,  # 422
}
RETRY_SERVER_ERRORS: set[int] = {
    HTTPStatus.INTERNAL_SERVER_ERROR,  # 500
    HTTPStatus.BAD_GATEWAY,  # 502
    HTTPStatus.SERVICE_UNAVAILABLE,  # 503
    HTTPStatus.GATEWAY_TIMEOUT,  # 504
}
_HTTP_5XX_END = 600  # exclusive upper bound of 5xx


def is_httpx_retryable(exception: BaseException) -> bool:
    """
    Decide if the exception is retryable for outbound HTTP calls.

    Expects raw httpx2 errors from inside the retry loop (before app-layer mapping).
    Any retryable frame in the cause/context chain counts.
    """

    return any(_is_httpx_retryable_frame(item) for item in iter_exception_chain(exception))


def _is_httpx_retryable_frame(exception: BaseException) -> bool:
    if isinstance(exception, TimeoutException):
        return True

    if isinstance(exception, TransportError):
        return True

    if isinstance(exception, HTTPStatusError):
        status = exception.response.status_code
        if status == HTTPStatus.TOO_MANY_REQUESTS:
            return True
        if status in RETRY_SERVER_ERRORS:
            return True
        if status in NO_RETRY_STATUS_CODES:
            return False
        if HTTPStatus.INTERNAL_SERVER_ERROR <= status < _HTTP_5XX_END:
            return True
        return False

    if isinstance(exception, CircuitOpenError):
        return True

    if isinstance(exception, TooManyRequests):
        return True

    return False
