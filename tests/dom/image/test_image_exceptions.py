from collections.abc import Callable

import pytest

from domain.image.exceptions import (
    AccessDeniedError,
    ImageError,
    ImageNotFoundError,
    PromptRejectedError,
    ValidationError,
)


@pytest.mark.unit
def test_image_not_found_error() -> None:
    error = ImageNotFoundError("image-1")
    assert error.image_id == "image-1"
    assert isinstance(error, ImageError)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("code", "meta"),
    [
        ("prohibited_content", None),
        ("prohibited_content", {"word": "naked"}),
    ],
)
def test_prompt_rejected_error_valid(code: str, meta: dict[str, str] | None) -> None:
    error = PromptRejectedError(code, meta)
    assert error.code == code
    assert error.meta == (meta or {})


@pytest.mark.unit
@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (lambda: PromptRejectedError("", None), "code must be a non-empty str"),
        (lambda: PromptRejectedError("bad", {"word": 1}), "meta keys and values must be strings"),  # type: ignore[dict-item]
    ],
)
def test_prompt_rejected_error_invalid(factory: Callable[[], None], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        factory()


@pytest.mark.unit
def test_access_denied_error_code() -> None:
    error = AccessDeniedError("access_denied")
    assert error.code == "access_denied"
