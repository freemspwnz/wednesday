from app.protocols import Logger, UoW


class ImageBaseUseCase:
    """Shared UoW + logging for image catalog command use cases."""

    _uow: UoW
    _logger: Logger

    def __init__(
        self,
        *,
        uow: UoW,
        logger: Logger,
    ) -> None:
        self._uow = uow
        self._logger = logger.bind(module=self.__class__.__name__)
