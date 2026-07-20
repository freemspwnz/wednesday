from ..protocols import UserRepo
from ..user import User
from ..vo import AwareDatetime, UserId, UserProfile, UserRole, UserSubscription
from .utils import load_or_raise


class UserManagementService:
    """Load user aggregate, apply administration command, and save."""

    @staticmethod
    async def change_role(
        *,
        id: UserId,
        actor: UserRole,
        new_role: UserRole,
        repo: UserRepo,
        at: AwareDatetime,
    ) -> User:
        id = UserId.ensure(id)
        actor = UserRole.ensure(actor)
        new_role = UserRole.ensure(new_role)
        at = AwareDatetime.ensure(at)

        user = await load_or_raise(repo=repo, id=id)
        user.change_role(actor=actor, new_role=new_role, at=at)
        await repo.save(user)
        return user

    @staticmethod
    async def change_profile(
        *,
        id: UserId,
        actor: UserRole,
        new_profile: UserProfile,
        repo: UserRepo,
        at: AwareDatetime,
    ) -> User:
        id = UserId.ensure(id)
        actor = UserRole.ensure(actor)
        new_profile = UserProfile.ensure(new_profile)
        at = AwareDatetime.ensure(at)

        user = await load_or_raise(repo=repo, id=id)
        user.change_profile(actor=actor, new_profile=new_profile, at=at)
        await repo.save(user)
        return user

    @staticmethod
    async def change_subscription(
        *,
        id: UserId,
        actor: UserRole,
        new_subscription: UserSubscription,
        repo: UserRepo,
        at: AwareDatetime,
    ) -> User:
        id = UserId.ensure(id)
        actor = UserRole.ensure(actor)
        new_subscription = UserSubscription.ensure(new_subscription)
        at = AwareDatetime.ensure(at)

        user = await load_or_raise(repo=repo, id=id)
        user.change_subscription(actor=actor, new_subscription=new_subscription, at=at)
        await repo.save(user)
        return user
