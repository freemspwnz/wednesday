from __future__ import annotations

from dataclasses import dataclass
from typing import Self
from uuid import UUID

from ...catalog import Model
from ..exceptions import ValidationError


@dataclass(frozen=True)
class ImageMeta:
    """Snapshot of who created the catalog entry and which model was used."""

    author_id: UUID
    model: Model

    def __post_init__(self) -> None:
        if not isinstance(self.author_id, UUID):
            raise ValidationError("author_id must be a UUID")
        Model.ensure(self.model)

    @classmethod
    def ensure(cls, meta: Self) -> Self:
        if not isinstance(meta, ImageMeta):
            raise ValidationError("meta must be an ImageMeta")
        return meta
