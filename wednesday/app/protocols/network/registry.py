from typing import Protocol, runtime_checkable

from domain.catalog import Vendor
from domain.image import Generator


@runtime_checkable
class GeneratorRegistry(Protocol):
    """Generator registry protocol."""

    def resolve(self, vendor: Vendor) -> Generator: ...
