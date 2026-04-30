from dataclasses import dataclass

from ..exceptions import ValidationError


@dataclass(frozen=True)
class NonEmptyStr:
    value: str

    def __post_init__(self) -> None:
        if not self.value or not self.value.strip():
            raise ValidationError("String cannot be empty or blank")
        object.__setattr__(self, "value", self.value.strip())

    def __str__(self) -> str:
        return self.value
