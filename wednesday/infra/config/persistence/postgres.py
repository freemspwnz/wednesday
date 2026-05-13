from functools import cached_property

from pydantic import BaseModel, ConfigDict, Field, PostgresDsn, SecretStr, computed_field


class PostgresConfig(BaseModel):
    """Validated PostgreSQL URL and pool/socket limits for ``asyncpg``."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    url: str | None = Field(default=None, description="Full PostgreSQL URL (overrides host/port/user/password/db_name)")
    user: str = Field(default="postgres", description="PostgreSQL username")
    password: SecretStr = Field(default=SecretStr("postgres"), description="PostgreSQL password")
    db_name: str = Field(default="postgres", description="PostgreSQL database name")
    pool_pre_ping: bool = Field(default=True, description="Enable pool pre-ping")
    echo: bool = Field(default=False, description="Enable SQLAlchemy echo")
    host: str = Field(default="localhost", description="PostgreSQL host")
    port: int = Field(default=5432, description="PostgreSQL port")
    pool_size: int = Field(default=10, description="PostgreSQL pool size")
    max_overflow: int = Field(default=20, description="PostgreSQL max overflow")

    @computed_field  # type: ignore[prop-decorator]
    @cached_property
    def dsn(self) -> str:
        """Connection string for ``asyncpg.create_pool``
        (built from ``url`` or host/port/user/password/db_name).
        """
        if self.url:
            return str(self.url).replace("postgresql://", "postgresql+asyncpg://", 1)

        return str(
            PostgresDsn.build(
                scheme="postgresql+asyncpg",
                username=self.user,
                password=self.password.get_secret_value(),
                host=self.host,
                port=self.port,
                path=f"{self.db_name}",
            )
        )
