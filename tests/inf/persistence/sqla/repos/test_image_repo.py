from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import pytest
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.exceptions import AggregateMappingError, DataIntegrityError, RepositoryError
from domain.image import ImageId, TelegramFileId
from domain.image.vote import Vote
from infra.persistence.sqlalchemy.models import ImageORM, ImageVoteORM
from infra.persistence.sqlalchemy.repos import SQLAImageRepo, SQLAImageSeenRepo, SQLAImageVoteRepo
from tests.dom.image.factories import dt, mk_image


def _dt(hour: int) -> datetime:
    return datetime(2026, 1, 1, hour, 0, tzinfo=UTC)


@pytest.mark.unit
@pytest.mark.infra
@pytest.mark.asyncio
async def test_image_save_uses_postgres_on_conflict() -> None:
    session = AsyncMock()
    repo = SQLAImageRepo(session=session)
    image = mk_image(image_id=1, created_at=dt(10))

    await repo.save(image)

    session.execute.assert_awaited_once()
    sql = str(session.execute.await_args.args[0])
    assert "ON CONFLICT" in sql
    assert "images" in sql


@pytest.mark.unit
@pytest.mark.infra
@pytest.mark.asyncio
async def test_image_save_wraps_integrity_error() -> None:
    session = AsyncMock()
    session.execute.side_effect = IntegrityError("stmt", {}, Exception("boom"))
    repo = SQLAImageRepo(session=session)

    with pytest.raises(DataIntegrityError):
        await repo.save(mk_image())


@pytest.mark.unit
@pytest.mark.infra
@pytest.mark.asyncio
async def test_image_get_by_id_maps_aggregate() -> None:
    image = mk_image(image_id=2, score=3, created_at=dt(11))
    orm_image = ImageORM(
        id=image.id.value,
        author_id=image.meta.author_id,
        model=str(image.meta.model),
        score=image.score,
        status="active",
        hidden_reason=None,
        created_at=_dt(11),
        user_prompt=None,
        enriched_prompt="enriched frog",
        telegram_file_id=None,
    )
    session = AsyncMock()
    result = Mock()
    result.scalar_one_or_none.return_value = orm_image
    session.execute.return_value = result
    repo = SQLAImageRepo(session=session)

    loaded = await repo.get_by_id(image.id)

    assert loaded is not None
    assert loaded.id == image.id
    assert loaded.score == 3
    assert str(loaded.meta.model) == "gigachat-2-lite"


@pytest.mark.unit
@pytest.mark.infra
@pytest.mark.asyncio
async def test_image_get_by_id_wraps_mapping_errors() -> None:
    session = AsyncMock()
    orm_image = ImageORM(
        id=mk_image().id.value,
        author_id=UUID(int=1),
        model="gigachat-2-lite",
        score=1,
        status="hidden",
        hidden_reason=None,
        created_at=_dt(10),
    )
    result = Mock()
    result.scalar_one_or_none.return_value = orm_image
    session.execute.return_value = result
    repo = SQLAImageRepo(session=session)

    with pytest.raises(AggregateMappingError):
        await repo.get_by_id(ImageId(UUID(int=2)))


@pytest.mark.unit
@pytest.mark.infra
@pytest.mark.asyncio
async def test_image_get_random_unseen_builds_expected_query() -> None:
    session = AsyncMock()
    result = Mock()
    result.scalar_one_or_none.return_value = None
    session.execute.return_value = result
    repo = SQLAImageRepo(session=session)
    chat_id = UUID(int=99)

    picked = await repo.get_random_unseen_for_chat(chat_id, min_score=1)

    assert picked is None
    sql = str(session.execute.await_args.args[0])
    assert "random()" in sql.lower()
    assert "image_seen" in sql


@pytest.mark.unit
@pytest.mark.infra
@pytest.mark.asyncio
async def test_image_exists_by_telegram_file_id() -> None:
    session = AsyncMock()
    result = Mock()
    result.scalar_one.return_value = True
    session.execute.return_value = result
    repo = SQLAImageRepo(session=session)

    exists = await repo.exists_by_telegram_file_id(TelegramFileId.parse("file-123"))

    assert exists is True


@pytest.mark.unit
@pytest.mark.infra
@pytest.mark.asyncio
async def test_vote_upsert_uses_on_conflict() -> None:
    session = AsyncMock()
    repo = SQLAImageVoteRepo(session=session)
    image_id = ImageId(UUID(int=5))
    voter_id = UUID(int=7)
    vote = Vote(image_id=image_id, voter_id=voter_id, value=1)

    await repo.upsert(vote)

    sql = str(session.execute.await_args.args[0])
    assert "ON CONFLICT" in sql
    assert "image_votes" in sql


@pytest.mark.unit
@pytest.mark.infra
@pytest.mark.asyncio
async def test_vote_get_returns_domain_vote() -> None:
    image_id = ImageId(UUID(int=5))
    voter_id = UUID(int=7)
    session = AsyncMock()
    result = Mock()
    result.scalar_one_or_none.return_value = ImageVoteORM(
        image_id=image_id.value,
        voter_id=voter_id,
        value=-1,
    )
    session.execute.return_value = result
    repo = SQLAImageVoteRepo(session=session)

    vote = await repo.get(image_id, voter_id)

    assert vote is not None
    assert vote.value == -1
    assert vote.voter_id == voter_id


@pytest.mark.unit
@pytest.mark.infra
@pytest.mark.asyncio
async def test_vote_list_for_image() -> None:
    image_id = ImageId(UUID(int=8))
    voter_a = UUID(int=1)
    voter_b = UUID(int=2)
    session = AsyncMock()
    result = Mock()
    result.scalars.return_value.all.return_value = [
        ImageVoteORM(image_id=image_id.value, voter_id=voter_a, value=1),
        ImageVoteORM(image_id=image_id.value, voter_id=voter_b, value=-1),
    ]
    session.execute.return_value = result
    repo = SQLAImageVoteRepo(session=session)

    votes = await repo.list_for_image(image_id)

    assert len(votes) == 2
    assert {item.value for item in votes} == {-1, 1}


@pytest.mark.unit
@pytest.mark.infra
@pytest.mark.asyncio
async def test_seen_mark_seen_is_idempotent() -> None:
    session = AsyncMock()
    repo = SQLAImageSeenRepo(session=session)
    chat_id = UUID(int=3)
    image_id = ImageId(UUID(int=4))
    at = dt(12)

    await repo.mark_seen(chat_id, image_id, at)

    sql = str(session.execute.await_args.args[0])
    assert "ON CONFLICT" in sql
    assert "DO NOTHING" in sql
    assert "image_seen" in sql


@pytest.mark.unit
@pytest.mark.infra
@pytest.mark.asyncio
async def test_seen_is_seen_returns_bool() -> None:
    session = AsyncMock()
    result = Mock()
    result.scalar_one.return_value = False
    session.execute.return_value = result
    repo = SQLAImageSeenRepo(session=session)

    seen = await repo.is_seen(UUID(int=3), ImageId(UUID(int=4)))

    assert seen is False


@pytest.mark.unit
@pytest.mark.infra
@pytest.mark.asyncio
async def test_seen_mark_seen_wraps_integrity_error() -> None:
    session = AsyncMock()
    session.execute.side_effect = IntegrityError("stmt", {}, Exception("boom"))
    repo = SQLAImageSeenRepo(session=session)

    with pytest.raises(DataIntegrityError):
        await repo.mark_seen(UUID(int=3), ImageId(UUID(int=4)), dt(12))


@pytest.mark.unit
@pytest.mark.infra
@pytest.mark.asyncio
async def test_vote_get_wraps_sqla_error() -> None:
    session = AsyncMock()
    session.execute.side_effect = SQLAlchemyError("db down")
    repo = SQLAImageVoteRepo(session=session)

    with pytest.raises(RepositoryError):
        await repo.get(ImageId(UUID(int=1)), UUID(int=2))
