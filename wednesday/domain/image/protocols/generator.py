from typing import Protocol, Self, runtime_checkable

from ..exceptions import ValidationError


@runtime_checkable
class Generator(Protocol):
    """Image generator protocol."""

    async def generate_image(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
    ) -> bytes: ...

    async def generate_text(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
    ) -> str: ...

    @classmethod
    def ensure(cls, gen: object) -> Self:
        if not isinstance(gen, cls):
            raise ValidationError(f"gen must be an instance of {cls.__name__}")
        return gen
