from pathlib import Path
from typing import Any

import yaml
from yaml import YAMLError

from app.exceptions import CatalogFormatError, CatalogNotFoundError, CatalogParseError


def load_yaml_mapping(path: Path) -> dict[str, Any]:
    """Load a YAML file and return its root mapping."""
    if not path.is_file():
        raise CatalogNotFoundError(f"catalog file not found: {path}", source=path)

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CatalogNotFoundError(f"catalog file is not readable: {path}", source=path) from exc
    except YAMLError as exc:
        raise CatalogParseError(f"catalog file is not valid YAML: {path}", source=path) from exc

    if raw is None:
        raise CatalogFormatError(f"catalog file is empty: {path}", source=path)
    if not isinstance(raw, dict):
        raise CatalogFormatError(f"catalog root must be a mapping: {path}", source=path)
    return raw


def require_mapping(value: object, *, field: str, path: Path) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CatalogFormatError(f"{field} must be a mapping in {path}", source=path, field=field)
    return value


def require_list(value: object, *, field: str, path: Path) -> list[Any]:
    if not isinstance(value, list):
        raise CatalogFormatError(f"{field} must be a list in {path}", source=path, field=field)
    return value


def require_bool(value: object, *, field: str, path: Path) -> bool:
    if not isinstance(value, bool):
        raise CatalogFormatError(f"{field} must be a bool in {path}", source=path, field=field)
    return value


def require_str(value: object, *, field: str, path: Path) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CatalogFormatError(f"{field} must be a non-empty string in {path}", source=path, field=field)
    return value.strip()


def require_int(value: object, *, field: str, path: Path) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise CatalogFormatError(f"{field} must be an int in {path}", source=path, field=field)
    return value


def require_non_empty_str_list(value: object, *, field: str, path: Path) -> tuple[str, ...]:
    """Require a non-empty list of non-empty strings; return them as a tuple."""
    items = require_list(value, field=field, path=path)
    if not items:
        raise CatalogFormatError(f"{field} must be a non-empty list in {path}", source=path, field=field)
    return tuple(require_str(item, field=f"{field}[]", path=path) for item in items)
