"""YamlCatalogFactory tests for model and subscription catalogs."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.exceptions import CatalogFormatError
from domain.catalog import Model, ModelCatalog, SubscriptionCatalog, SubscriptionTier
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
def test_yaml_model_catalog_loads_project_file() -> None:
    catalog = _catalog_factory().models
    assert ModelCatalog.ensure(catalog) is catalog


@pytest.mark.unit
@pytest.mark.infra
@pytest.mark.asyncio
async def test_yaml_model_catalog_exposes_active_sber_models() -> None:
    catalog = _catalog_factory().models

    assert await catalog.exists(Model.parse("gigachat-2-lite"))
    alice = await catalog.get_by_model(Model.parse("alicegpt-lite"))
    assert alice is not None
    assert not alice.active

    active = await catalog.list_active()
    active_codes = {str(item.model) for item in active}
    assert "gigachat-2-lite" in active_codes
    assert "alicegpt-lite" not in active_codes

    lite = await catalog.get_by_model(Model.parse("gigachat-2-lite"))
    assert lite is not None
    assert lite.display_name == "GigaChat 2 Lite"

    default_free = await catalog.default_for_tier(SubscriptionTier.FREE)
    assert default_free.model == Model.parse("gigachat-2-lite")

    default_premium = await catalog.default_for_tier(SubscriptionTier.PREMIUM)
    assert default_premium.model == Model.parse("gigachat-2-pro")

    vendors = await catalog.list_vendors()
    assert len(vendors) == 1
    assert str(vendors[0]) == "sber"


@pytest.mark.unit
@pytest.mark.infra
def test_yaml_subscription_catalog_loads_project_file() -> None:
    catalog = _catalog_factory().subscriptions
    assert SubscriptionCatalog.ensure(catalog) is catalog


@pytest.mark.unit
@pytest.mark.infra
@pytest.mark.asyncio
async def test_yaml_subscription_catalog_matches_yaml_limits() -> None:
    catalog = _catalog_factory().subscriptions

    free = await catalog.get_by_tier(SubscriptionTier.FREE)
    premium = await catalog.get_by_tier(SubscriptionTier.PREMIUM)
    assert free.daily_limit == 3
    assert free.cooldown_minutes == 3
    assert premium.daily_limit == 10
    assert premium.cooldown_minutes == 1

    assert (await catalog.default_plan()).tier is SubscriptionTier.FREE
    assert len(await catalog.list_active()) == 2


@pytest.mark.unit
@pytest.mark.infra
def test_yaml_model_catalog_rejects_duplicate_model(tmp_path: Path) -> None:
    path = tmp_path / "models.yaml"
    path.write_text(
        """
vendors:
  - code: sber
    active: true
    display_name: Sber
    series:
      - code: gigachat
        active: true
        display_name: GigaChat
        min_tier: 0
        models:
          - code: gigachat-2-lite
            active: true
            min_tier: 0
            display_name: Lite
  - code: other
    active: true
    display_name: Other
    series:
      - code: gigachat
        active: true
        display_name: GigaChat
        min_tier: 0
        models:
          - code: gigachat-2-lite
            active: true
            min_tier: 0
            display_name: Lite duplicate
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(CatalogFormatError, match="duplicate model"):
        YamlCatalogFactory._build_model_catalog(path)
