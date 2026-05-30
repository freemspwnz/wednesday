from __future__ import annotations

from functools import cached_property
from pathlib import Path

from app.exceptions import CatalogFormatError
from app.protocols import Logger
from domain.catalog import (
    Model,
    ModelCatalog,
    ModelDescriptor,
    Series,
    SubscriptionCatalog,
    SubscriptionPlan,
    SubscriptionTier,
    Vendor,
)
from infra.config import YamlConfig

from .catalog import YamlModelCatalog, YamlSubscriptionCatalog
from .loader import (
    load_yaml_mapping,
    require_bool,
    require_int,
    require_list,
    require_mapping,
    require_str,
)


class YamlCatalogFactory:
    """Builds read-only YAML-backed domain catalogs from configured paths."""

    def __init__(self, *, config: YamlConfig, logger: Logger) -> None:
        self._config = config
        self._logger = logger.bind(module=self.__class__.__name__)

    @cached_property
    def model_catalog(self) -> ModelCatalog:
        self._logger.debug("Building model catalog...", path=self._config.models_path)
        return self._build_model_catalog(self._config.models_path)

    @cached_property
    def subscription_catalog(self) -> SubscriptionCatalog:
        self._logger.debug("Building subscription catalog...", path=self._config.subscriptions_path)
        return self._build_subscription_catalog(self._config.subscriptions_path)

    @staticmethod
    def _build_model_catalog(path: Path) -> YamlModelCatalog:
        source = path
        data = load_yaml_mapping(source)
        vendors_raw = require_list(data.get("vendors"), field="vendors", path=source)

        by_model: dict[str, ModelDescriptor] = {}
        ordered: list[ModelDescriptor] = []
        vendors: list[Vendor] = []
        series_by_vendor: dict[str, list[Series]] = {}
        models_by_vendor_series: dict[tuple[str, str], list[Model]] = {}

        for vendor_raw in vendors_raw:
            vendor_node = require_mapping(vendor_raw, field="vendor", path=source)
            vendor_code = require_str(vendor_node.get("code"), field="vendor.code", path=source)
            vendor_active = require_bool(vendor_node.get("active"), field="vendor.active", path=source)
            vendor = Vendor.parse(vendor_code)
            if vendor_active:
                vendors.append(vendor)

            series_list = require_list(vendor_node.get("series"), field="vendor.series", path=source)
            vendor_series: list[Series] = []
            for series_raw in series_list:
                series_node = require_mapping(series_raw, field="series", path=source)
                series_code = require_str(series_node.get("code"), field="series.code", path=source)
                series_active = require_bool(series_node.get("active"), field="series.active", path=source)
                series = Series.parse(series_code)
                if vendor_active and series_active:
                    vendor_series.append(series)

                models_list = require_list(series_node.get("models"), field="series.models", path=source)
                vendor_series_models: list[Model] = []
                for model_raw in models_list:
                    model_node = require_mapping(model_raw, field="model", path=source)
                    model_code = require_str(model_node.get("code"), field="model.code", path=source)
                    model_active = require_bool(model_node.get("active"), field="model.active", path=source)
                    min_tier = SubscriptionTier(
                        require_int(model_node.get("min_tier"), field="model.min_tier", path=source)
                    )
                    display_name = require_str(
                        model_node.get("display_name"),
                        field="model.display_name",
                        path=source,
                    )
                    effective_active = vendor_active and series_active and model_active
                    descriptor = ModelDescriptor(
                        model=Model.parse(model_code),
                        vendor=vendor,
                        series=series,
                        min_tier=min_tier,
                        display_name=display_name,
                        active=effective_active,
                    )
                    model_key = str(descriptor.model)
                    if model_key in by_model:
                        raise CatalogFormatError(
                            f"duplicate model code {model_key!r} in {source}",
                            source=source,
                            field="model.code",
                        )
                    by_model[model_key] = descriptor
                    ordered.append(descriptor)
                    if effective_active:
                        vendor_series_models.append(descriptor.model)

                if vendor_active and series_active and vendor_series_models:
                    vendor_series_key = (str(vendor), str(series))
                    models_by_vendor_series[vendor_series_key] = sorted(vendor_series_models, key=str)

            if vendor_active and vendor_series:
                series_by_vendor[str(vendor)] = sorted(vendor_series, key=str)

        if not by_model:
            raise CatalogFormatError(f"no models defined in {source}", source=source, field="vendors")

        return YamlModelCatalog(
            _by_model=by_model,
            _ordered=ordered,
            _vendors=sorted(vendors, key=str),
            _series_by_vendor=series_by_vendor,
            _models_by_vendor_series=models_by_vendor_series,
        )

    @staticmethod
    def _build_subscription_catalog(path: Path) -> YamlSubscriptionCatalog:
        source = path
        data = load_yaml_mapping(source)
        plans_raw = require_list(data.get("plans"), field="plans", path=source)

        plans: dict[SubscriptionTier, SubscriptionPlan] = {}
        for plan_raw in plans_raw:
            plan_node = require_mapping(plan_raw, field="plan", path=source)
            tier = SubscriptionTier(require_int(plan_node.get("tier"), field="plan.tier", path=source))
            daily_limit = require_int(plan_node.get("daily_limit"), field="plan.daily_limit", path=source)
            cooldown_minutes = require_int(
                plan_node.get("cooldown_minutes"),
                field="plan.cooldown_minutes",
                path=source,
            )
            if tier in plans:
                raise CatalogFormatError(
                    f"duplicate subscription tier {tier.value} in {source}",
                    source=source,
                    field="plan.tier",
                )
            plans[tier] = SubscriptionPlan(
                tier=tier,
                daily_limit=daily_limit,
                cooldown_minutes=cooldown_minutes,
            )

        if SubscriptionTier.FREE not in plans:
            raise CatalogFormatError(
                f"free subscription plan is required in {source}",
                source=source,
                field="plans",
            )

        return YamlSubscriptionCatalog(_plans=plans)
