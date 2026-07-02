from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.exceptions import CatalogFormatError
from domain.image.protocols import PromptCatalog
from infra.config import YamlConfig
from infra.persistence.yaml import YamlCatalogFactory


def _project_catalog_config() -> YamlConfig:
    root = Path(__file__).resolve().parents[4]
    return YamlConfig(
        models_path=root / "catalog" / "models.yaml",
        subscriptions_path=root / "catalog" / "subscriptions.yaml",
        prompts_path=root / "catalog" / "prompts.yaml",
    )


def _catalog_factory(config: YamlConfig | None = None) -> YamlCatalogFactory:
    logger = MagicMock()
    logger.bind.return_value = logger
    return YamlCatalogFactory(config=config or _project_catalog_config(), logger=logger)


@pytest.mark.unit
@pytest.mark.infra
def test_yaml_prompt_catalog_loads_project_file() -> None:
    catalog = _catalog_factory().prompt_catalog
    assert PromptCatalog.ensure(catalog) is catalog


@pytest.mark.unit
@pytest.mark.infra
@pytest.mark.asyncio
async def test_yaml_prompt_catalog_exposes_system_prompts_and_components() -> None:
    catalog = _catalog_factory().prompt_catalog

    enrichment = await catalog.enrichment_prompt()
    generation = await catalog.generation_prompt()
    base = await catalog.base_prompt()
    components = await catalog.components()

    assert "Wednesday frog meme" in enrichment
    assert "Wednesday frog meme" in generation
    assert "Wednesday frog meme" in base
    assert components.heroes
    assert "Frog" in components.heroes
    assert components.colors
    assert components.styles
    assert components.professions
    assert components.actions
    assert components.places
    assert components.portraits


@pytest.mark.unit
@pytest.mark.infra
def test_yaml_prompt_catalog_rejects_empty_component_list(tmp_path: Path) -> None:
    path = tmp_path / "prompts.yaml"
    path.write_text(
        """
system_prompts:
  enrichment: enrich
  generation: generate
  base: base
components:
  heroes: []
  colors: [green]
  styles: [cartoon]
  professions: [chef]
  actions: [jumping]
  places: [forest]
  portraits: [portrait]
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(CatalogFormatError, match="components.heroes"):
        YamlCatalogFactory._build_prompt_catalog(path)
