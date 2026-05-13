import pytest

from app.exceptions import SQLADataIntegrityError, SQLARepositoryError, UnexpectedSQLAError


@pytest.mark.unit
@pytest.mark.infra
def test_sqla_repository_error_keeps_context() -> None:
    err = SQLARepositoryError(
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
def test_sqla_error_hierarchy() -> None:
    integrity_error = SQLADataIntegrityError(
        "broken",
        operation="save",
        entity="chat",
        entity_id="abc",
    )
    assert isinstance(integrity_error, SQLARepositoryError)
    assert isinstance(UnexpectedSQLAError("oops"), Exception)
