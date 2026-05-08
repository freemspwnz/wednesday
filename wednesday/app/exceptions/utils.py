from builtins import BaseException


def unwrap_exception(exception: BaseException) -> BaseException:
    current: BaseException = exception
    while True:
        cause = current.__cause__
        if cause is not None:
            current = cause
            continue

        context = current.__context__
        if context is not None:
            current = context
            continue

        return current
