from __future__ import annotations

from .....exceptions import ValidationError


class ManagementAction:
    @classmethod
    def ensure(cls, action: ManagementAction) -> ManagementAction:
        if not isinstance(action, cls):
            raise ValidationError("action must be a ManagementAction")
        return action
