from dataclasses import dataclass

from .code import ModelSelectionCode


@dataclass(frozen=True)
class ModelSelectionAllowed:
    pass


@dataclass(frozen=True)
class ModelSelectionDenied:
    code: ModelSelectionCode

    def __post_init__(self) -> None:
        ModelSelectionCode.ensure(self.code)


type ModelSelectionDecision = ModelSelectionAllowed | ModelSelectionDenied
