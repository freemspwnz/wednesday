from domain.catalog import Model, ModelCatalog, SubscriptionCatalog

from ..exceptions import ModelNotFoundError, UserNotFoundError, ValidationError
from ..protocols import UserRepo
from ..user import User
from ..vo import AwareDatetime, UserId


class ModelSelectionService:
    """Service for selecting a model for a user."""

    @staticmethod
    async def select_model(  # noqa: PLR0913
        *,
        user_id: UserId,
        model: Model,
        user_repo: UserRepo,
        models: ModelCatalog,
        subs: SubscriptionCatalog,
        at: AwareDatetime,
    ) -> User:
        user_id = UserId.ensure(user_id)
        model = Model.ensure(model)
        at = AwareDatetime.ensure(at)
        if not isinstance(user_repo, UserRepo):
            raise ValidationError("user_repo must implement UserRepo")
        models = ModelCatalog.ensure(models)
        subs = SubscriptionCatalog.ensure(subs)

        user = await user_repo.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError(str(user_id))

        descriptor = await models.get_by_model(model)
        if descriptor is None:
            raise ModelNotFoundError(str(model))

        fallback = await subs.default_plan()

        user.change_settings(fallback=fallback, descriptor=descriptor, at=at)
        await user_repo.save(user)
        return user
