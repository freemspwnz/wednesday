from dataclasses import dataclass

from ....exceptions import ValidationError
from .code import ManagementAccessCode


@dataclass(frozen=True)
class ManagementAccessAllowed:
    pass


@dataclass(frozen=True)
class ManagementAccessDenied:
    code: ManagementAccessCode

    def __post_init__(self) -> None:
        if not isinstance(self.code, ManagementAccessCode):
            raise ValidationError("code must be a ManagementAccessCode")


type ManagementAccessDecision = ManagementAccessAllowed | ManagementAccessDenied
