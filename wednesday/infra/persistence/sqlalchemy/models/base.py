from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Базовый класс декларативных моделей SQLAlchemy."""

    metadata = MetaData(schema="wednesday_schema")
