from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class YamlConfig(BaseModel):
    """Paths to YAML-backed domain catalogs."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    models_path: Path = Field(default=Path("catalog/models.yaml"))
    subscriptions_path: Path = Field(default=Path("catalog/subscriptions.yaml"))
    prompts_path: Path = Field(default=Path("catalog/prompts.yaml"))
