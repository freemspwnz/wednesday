from ..exceptions import ModelNotFoundError
from ..protocols import ModelRepo
from ..user import User
from ..vo import AwareDatetime, Model


class ModelSelectionService:
    """Service for selecting a model for a user."""

    @staticmethod
    async def select_model(
        *,
        user: User,
        model: Model,
        repo: ModelRepo,
        at: AwareDatetime,
    ) -> None:
        user = User.ensure(user)
        model = Model.ensure(model)
        repo = ModelRepo.ensure(repo)
        at = AwareDatetime.ensure(at)

        descriptor = await repo.get_by_model(model)
        if descriptor is None:
            raise ModelNotFoundError(str(model))

        user.change_settings(descriptor=descriptor, at=at)
