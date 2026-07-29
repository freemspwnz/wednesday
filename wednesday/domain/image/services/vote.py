from domain.user import UserId

from ..protocols import VoteRepo
from ..vo import ImageId
from ..vote import Vote


class ImageVoteService:
    """Vote for an image."""

    @staticmethod
    async def vote(
        *,
        vote: Vote,
        repo: VoteRepo,
    ) -> None:
        vote = Vote.ensure(vote)

        existing = await repo.get(vote.image_id, vote.voter_id)
        if existing is None:
            await repo.upsert(vote)
        elif existing.value != vote.value:
            await repo.upsert(existing.change(vote.value))
        else:
            return

    @staticmethod
    async def get_if_exists(
        *,
        image_id: ImageId,
        voter_id: UserId,
        repo: VoteRepo,
    ) -> Vote | None:
        image_id = ImageId.ensure(image_id)
        voter_id = UserId.ensure(voter_id)

        return await repo.get(image_id, voter_id)

    @staticmethod
    async def reset(
        *,
        id: ImageId,
        repo: VoteRepo,
    ) -> None:
        id = ImageId.ensure(id)

        await repo.reset(id)
