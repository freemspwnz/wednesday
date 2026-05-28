from domain.catalog import Model, ModelCatalog, SubscriptionCatalog

from ..exceptions import ModelNotFoundError
from ..user import User
from ..vo import AwareDatetime


class ModelSelectionService:
    """Service for selecting a model for a user."""

    @staticmethod
    async def select_model(
        *,
        user: User,
        model: Model,
        model_catalog: ModelCatalog,
        sub_catalog: SubscriptionCatalog,
        at: AwareDatetime,
    ) -> None:
        user = User.ensure(user)
        model = Model.ensure(model)
        model_catalog = ModelCatalog.ensure(model_catalog)
        sub_catalog = SubscriptionCatalog.ensure(sub_catalog)
        at = AwareDatetime.ensure(at)

        descriptor = await model_catalog.get_by_model(model)
        if descriptor is None:
            raise ModelNotFoundError(str(model))

        fallback = await sub_catalog.default_plan()

        user.change_settings(fallback=fallback, descriptor=descriptor, at=at)
