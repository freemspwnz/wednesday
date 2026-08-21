import json
from dataclasses import asdict, fields
from datetime import datetime
from functools import cache
from types import UnionType
from typing import Union, get_args, get_origin, get_type_hints

from app.dto import ChatContext, UserContext
from app.exceptions import CacheInvalidDataError, CacheStaleDataError

USER_CONTEXT_VERSION = 3
CHAT_CONTEXT_VERSION = 2


def dump_user_context(context: UserContext) -> str:
    data = asdict(context)
    for key, value in data.items():
        if isinstance(value, datetime):
            data[key] = value.isoformat()
    return json.dumps({
        "v": USER_CONTEXT_VERSION,
        **data,
    })


def dump_chat_context(context: ChatContext) -> str:
    data = asdict(context)
    for key, value in data.items():
        if isinstance(value, datetime):
            data[key] = value.isoformat()
    return json.dumps({
        "v": CHAT_CONTEXT_VERSION,
        **data,
    })


def load_user_context(payload: str) -> UserContext:
    try:
        op = "load_user_context"
        data = _validate_json(payload, op)
        _validate_version(data, USER_CONTEXT_VERSION)
        data.pop("v")
        for key in _datetime_fields(UserContext):
            value = data.get(key)
            if isinstance(value, str):
                data[key] = datetime.fromisoformat(value)
        return UserContext(**data)

    except CacheStaleDataError:
        raise
    except CacheInvalidDataError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise CacheInvalidDataError(str(exc), operation=op) from exc


def load_chat_context(payload: str) -> ChatContext:
    try:
        op = "load_chat_context"
        data = _validate_json(payload, op)
        _validate_version(data, CHAT_CONTEXT_VERSION)
        data.pop("v")
        for key in _datetime_fields(ChatContext):
            value = data.get(key)
            if isinstance(value, str):
                data[key] = datetime.fromisoformat(value)
        if "schedules" in data:
            data["schedules"] = [tuple(schedule) for schedule in data["schedules"]]
        return ChatContext(**data)

    except CacheStaleDataError:
        raise
    except CacheInvalidDataError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise CacheInvalidDataError(str(exc), operation=op) from exc


def _validate_version(payload: dict, version: int) -> None:
    if payload["v"] != version:
        raise CacheStaleDataError(
            f"Version mismatch: expected {version}, got {payload['v']}", operation="validate_version"
        )


def _validate_json(payload: str, operation: str) -> dict:
    try:
        raw = json.loads(payload)
        if not isinstance(raw, dict):
            raise CacheInvalidDataError(f"Invalid JSON: {payload}", operation=operation)
        return raw
    except json.JSONDecodeError as e:
        raise CacheInvalidDataError(f"Invalid JSON: {payload}", operation=operation) from e


def _includes_datetime(hint: object) -> bool:
    if hint is datetime:
        return True
    origin = get_origin(hint)
    if origin is Union or origin is UnionType:
        return any(arg is datetime for arg in get_args(hint))
    return False


@cache
def _datetime_fields(cls: type) -> frozenset[str]:
    hints = get_type_hints(cls)
    return frozenset(f.name for f in fields(cls) if _includes_datetime(hints[f.name]))
