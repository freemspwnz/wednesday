from dataclasses import dataclass

from .code import ManagementAccessCode


@dataclass(frozen=True)
class ManagementAllowed:
    pass


@dataclass(frozen=True)
class ManagementDenied:
    code: ManagementAccessCode

    def __post_init__(self) -> None:
        ManagementAccessCode.ensure(self.code)


type ManagementAccessDecision = ManagementAllowed | ManagementDenied
