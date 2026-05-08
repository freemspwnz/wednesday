from __future__ import annotations

from ...exceptions import ValidationError


class ManagementActor:
    """Base class for management actors."""

    @classmethod
    def ensure(cls, actor: ManagementActor) -> ManagementActor:
        if not isinstance(actor, cls):
            raise ValidationError("actor must be a ManagementActor")
        return actor
