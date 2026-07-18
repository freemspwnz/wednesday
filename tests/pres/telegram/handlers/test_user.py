"""Tests for user router handlers."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import Message
from dom.user.factories import descriptor_lite, descriptor_pro, dt, mk_user

from app.dto import UserContext
from domain.user.exceptions import ModelNotFoundError, ModelSelectionError
from presentation.aiogram.messages import commands as cmd_msg, exceptions as exc_msg, user as user_msg
from presentation.aiogram.routers import user as handlers

from ..factories import make_message, mk_user_context


@pytest.fixture
def user_context() -> UserContext:
    return mk_user_context()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cmd_me_replies_with_profile(user_context: UserContext) -> None:
    message = make_message(text="/me")
    expected = user_msg.format_me(user_context)
    with patch.object(Message, "answer", new_callable=AsyncMock) as answer:
        await handlers.cmd_me(message, user_context)
    answer.assert_awaited_once_with(text=expected)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_set_model_usage() -> None:
    message = make_message(text="/set_model")
    with patch.object(Message, "answer", new_callable=AsyncMock) as answer:
        await handlers.cmd_set_model_usage(message)
    answer.assert_awaited_once_with(cmd_msg.SET_MODEL_USAGE)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_set_model_success(user_context: UserContext, mock_scope: MagicMock, mock_logger: MagicMock) -> None:
    updated = mk_user(user_id=1, now=dt(10))
    mock_scope.user_commands_uc.select_model = AsyncMock(return_value=updated)
    message = make_message(text="/set_model gigachat-2-lite")

    with patch.object(Message, "answer", new_callable=AsyncMock) as answer:
        await handlers.cmd_set_model(
            message,
            ["gigachat-2-lite"],
            user_context,
            mock_scope,
            mock_logger,
        )

    mock_scope.user_commands_uc.select_model.assert_awaited_once()
    answer.assert_awaited_once_with(cmd_msg.format_set_model_success("gigachat-2-lite"))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_set_model_not_found(user_context: UserContext, mock_scope: MagicMock, mock_logger: MagicMock) -> None:
    mock_scope.user_commands_uc.select_model = AsyncMock(
        side_effect=ModelNotFoundError("missing-model"),
    )
    message = make_message(text="/set_model missing-model")

    with patch.object(Message, "answer", new_callable=AsyncMock) as answer:
        await handlers.cmd_set_model(
            message,
            ["missing-model"],
            user_context,
            mock_scope,
            mock_logger,
        )

    answer.assert_awaited_once_with(exc_msg.MODEL_NOT_FOUND)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_set_model_tier_denied(user_context: UserContext, mock_scope: MagicMock, mock_logger: MagicMock) -> None:
    mock_scope.user_commands_uc.select_model = AsyncMock(
        side_effect=ModelSelectionError("tier_too_low"),
    )
    message = make_message(text="/set_model gigachat-2-pro")

    with patch.object(Message, "answer", new_callable=AsyncMock) as answer:
        await handlers.cmd_set_model(
            message,
            ["gigachat-2-pro"],
            user_context,
            mock_scope,
            mock_logger,
        )

    answer.assert_awaited_once_with("Модель недоступна для вашей подписки.")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_models_filters_by_tier(
    user_context: UserContext, mock_scope: MagicMock, mock_logger: MagicMock
) -> None:
    mock_scope.models.list_active = AsyncMock(
        return_value=[descriptor_lite(), descriptor_pro()],
    )
    message = make_message(text="/list_models")

    with patch.object(Message, "answer", new_callable=AsyncMock) as answer:
        await handlers.cmd_list_models(message, user_context, mock_scope, mock_logger)

    answer.assert_awaited_once_with(cmd_msg.format_list_models(["gigachat-2-lite"]))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_models_empty_for_tier(
    user_context: UserContext, mock_scope: MagicMock, mock_logger: MagicMock
) -> None:
    mock_scope.models.list_active = AsyncMock(return_value=[descriptor_pro()])
    message = make_message(text="/list_models")

    with patch.object(Message, "answer", new_callable=AsyncMock) as answer:
        await handlers.cmd_list_models(message, user_context, mock_scope, mock_logger)

    answer.assert_awaited_once_with(cmd_msg.LIST_MODELS_EMPTY)
