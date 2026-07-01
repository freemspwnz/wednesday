from typing import Protocol, Self, runtime_checkable

from ..exceptions import ValidationError


@runtime_checkable
class TextGenerator(Protocol):
    """Text generator protocol."""

    async def generate(
        self,
        model: str,
        user_prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.7,
    ) -> str: ...

    @classmethod
    def ensure(cls, txt_gen: Self) -> Self:
        if not isinstance(txt_gen, cls):
            raise ValidationError("txt_gen must be an instance of TextGenerator")
        return txt_gen
