from builtins import BaseException
from collections.abc import Iterator


def iter_exception_chain(exception: BaseException) -> Iterator[BaseException]:
    current: BaseException | None = exception
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        yield current
        seen.add(id(current))
        current = current.__cause__ or (current.__context__ if not current.__suppress_context__ else None)


def unwrap_exception(exception: BaseException) -> BaseException:
    *_, root = iter_exception_chain(exception)
    return root
