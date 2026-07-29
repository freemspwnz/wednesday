from dataclasses import dataclass
from typing import Self

from domain.user import UserId

from ...catalog import Model
from ..exceptions import ValidationError


@dataclass(frozen=True)
class ImageMeta:
    """Snapshot of who created the catalog entry and which model was used."""

    author_id: UserId
    model: Model

    def __post_init__(self) -> None:
        UserId.ensure(self.author_id)
        Model.ensure(self.model)

    @classmethod
    def ensure(cls, meta: object) -> Self:
        if not isinstance(meta, cls):
            raise ValidationError(f"meta must be an instance of {cls.__name__}")
        return meta
