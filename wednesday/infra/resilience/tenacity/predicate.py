from app.exceptions import CircuitOpenError, TooManyRequests, unwrap_exception


def is_retryable(exception: BaseException) -> bool:
    """
    Decides if the exception is retryable.
    """

    exception = unwrap_exception(exception)

    if isinstance(exception, CircuitOpenError):
        return True

    if isinstance(exception, TooManyRequests):
        return True

    return False
