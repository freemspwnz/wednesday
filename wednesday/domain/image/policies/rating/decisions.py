from dataclasses import dataclass


@dataclass(frozen=True)
class Hide:
    pass


@dataclass(frozen=True)
class Show:
    pass


@dataclass(frozen=True)
class NoOperation:
    pass


type RatingDecision = Hide | Show | NoOperation
