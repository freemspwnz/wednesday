from typing import Protocol, Self, runtime_checkable

from ..exceptions import ValidationError


@runtime_checkable
class ImageGenerator(Protocol):
    """Image generator protocol."""

    async def generate_image(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
    ) -> bytes: ...

    @classmethod
    def ensure(cls, img_gen: Self) -> Self:
        if not isinstance(img_gen, cls):
            raise ValidationError("img_gen must be an instance of ImageGenerator")
        return img_gen
