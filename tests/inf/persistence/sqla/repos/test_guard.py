"""Unit tests for shared SQLAlchemy repository guard."""

from uuid import UUID

import pytest
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.exceptions import (
    AggregateMappingError,
    DataIntegrityError,
    RepositoryError,
    UnexpectedDBError,
)
from infra.persistence.sqlalchemy.repos._guard import guard_repo

_ENTITY_ID = UUID(int=1)


async def _ok() -> str:
    return "ok"


@pytest.mark.unit
@pytest.mark.infra
@pytest.mark.asyncio
async def test_guard_repo_returns_result() -> None:
    result = await guard_repo(
        operation="op",
        entity="entity",
        sqlalchemy_message="sql",
        unexpected_message="unexpected",
        run=_ok,
    )
    assert result == "ok"


@pytest.mark.unit
@pytest.mark.infra
@pytest.mark.asyncio
async def test_guard_repo_maps_integrity_error() -> None:
    async def _run() -> None:
        raise IntegrityError("stmt", {}, Exception("boom"))

    with pytest.raises(DataIntegrityError) as exc_info:
        await guard_repo(
            operation="save",
            entity="user",
            entity_id=_ENTITY_ID,
            integrity_message="constraint violated",
            sqlalchemy_message="sql",
            unexpected_message="unexpected",
            run=_run,
        )

    err = exc_info.value
    assert err.operation == "save"
    assert err.entity == "user"
    assert err.entity_id == _ENTITY_ID


@pytest.mark.unit
@pytest.mark.infra
@pytest.mark.asyncio
async def test_guard_repo_reraises_integrity_without_message() -> None:
    async def _run() -> None:
        raise IntegrityError("stmt", {}, Exception("boom"))

    with pytest.raises(IntegrityError):
        await guard_repo(
            operation="save",
            entity="user",
            sqlalchemy_message="sql",
            unexpected_message="unexpected",
            run=_run,
        )


@pytest.mark.unit
@pytest.mark.infra
@pytest.mark.asyncio
async def test_guard_repo_maps_value_error() -> None:
    async def _run() -> None:
        raise ValueError("bad payload")

    with pytest.raises(AggregateMappingError) as exc_info:
        await guard_repo(
            operation="get_by_id",
            entity="image",
            entity_id=_ENTITY_ID,
            mapping_message="Failed to map aggregate.",
            sqlalchemy_message="sql",
            unexpected_message="unexpected",
            run=_run,
        )

    err = exc_info.value
    assert err.operation == "get_by_id"
    assert err.entity == "image"
    assert err.entity_id == _ENTITY_ID


@pytest.mark.unit
@pytest.mark.infra
@pytest.mark.asyncio
async def test_guard_repo_reraises_value_error_without_mapping_message() -> None:
    async def _run() -> None:
        raise ValueError("bad payload")

    with pytest.raises(ValueError, match="bad payload"):
        await guard_repo(
            operation="get_by_id",
            entity="image",
            sqlalchemy_message="sql",
            unexpected_message="unexpected",
            run=_run,
        )


@pytest.mark.unit
@pytest.mark.infra
@pytest.mark.asyncio
async def test_guard_repo_maps_sqlalchemy_error() -> None:
    async def _run() -> None:
        raise SQLAlchemyError("db down")

    with pytest.raises(RepositoryError) as exc_info:
        await guard_repo(
            operation="exists",
            entity="chat",
            entity_id=_ENTITY_ID,
            sqlalchemy_message="SQLAlchemy failed.",
            unexpected_message="unexpected",
            run=_run,
        )

    assert exc_info.value.entity_id == _ENTITY_ID


@pytest.mark.unit
@pytest.mark.infra
@pytest.mark.asyncio
async def test_guard_repo_maps_unexpected_error() -> None:
    async def _run() -> None:
        raise RuntimeError("boom")

    with pytest.raises(UnexpectedDBError, match="Unexpected error."):
        await guard_repo(
            operation="exists",
            entity="chat",
            sqlalchemy_message="sql",
            unexpected_message="Unexpected error.",
            run=_run,
        )
