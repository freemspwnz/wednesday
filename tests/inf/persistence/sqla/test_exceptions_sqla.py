import pytest

from app.exceptions import DataIntegrityError, RepositoryError, UnexpectedDBError


@pytest.mark.unit
@pytest.mark.infra
def test_repository_error_keeps_context() -> None:
    err = RepositoryError(
        "failed",
        operation="save",
        entity="user",
        entity_id=123,
    )
    assert err.operation == "save"
    assert err.entity == "user"
    assert err.entity_id == 123


@pytest.mark.unit
@pytest.mark.infra
def test_db_error_hierarchy() -> None:
    integrity_error = DataIntegrityError(
        "broken",
        operation="save",
        entity="chat",
        entity_id="abc",
    )
    assert isinstance(integrity_error, RepositoryError)
    assert isinstance(UnexpectedDBError("oops"), Exception)
