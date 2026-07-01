from enum import StrEnum
from typing import Self

from ...exceptions import ValidationError


class PromptSource(StrEnum):
    USER = "user"
    FALLBACK = "fallback"
    LLM = "llm"

    @classmethod
    def ensure(cls, source: Self) -> Self:
        if not isinstance(source, cls):
            raise ValidationError("source must be a PromptSource")
        return source
