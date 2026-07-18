from typing import Protocol, Self, runtime_checkable

from ..exceptions import ValidationError


@runtime_checkable
class TextGenerator(Protocol):
    """Text generator protocol."""

    async def generate_text(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
    ) -> str: ...

    @classmethod
    def ensure(cls, txt_gen: Self) -> Self:
        if not isinstance(txt_gen, cls):
            raise ValidationError("txt_gen must be an instance of TextGenerator")
        return txt_gen
