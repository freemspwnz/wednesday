"""Доменный объект для построения fallback промптов.

Инкапсулирует бизнес-правила форматирования fallback промптов.
"""

from __future__ import annotations

import random
from collections.abc import Callable

from domain.value_objects import Prompt


class FallbackPromptBuilder:
    """Доменный объект для построения fallback промптов.

    Инкапсулирует бизнес-правила форматирования fallback промптов.
    """

    DEFAULT_SUFFIX = "high quality, detailed, Wednesday frog meme"
    """Стандартный суффикс для fallback промптов."""

    @classmethod
    def build(
        cls,
        frog_prompts: list[str],
        styles: list[str],
        default_fallback: str,
        random_selector: Callable[[list[str]], str] = random.choice,
    ) -> Prompt:
        """Строит fallback промпт согласно бизнес-правилам.

        Если списки промптов или стилей пусты, возвращает default_fallback.
        Иначе выбирает случайный промпт и стиль, форматирует их по шаблону
        и возвращает валидированный Prompt.

        Args:
            frog_prompts: Список доступных промптов про лягушку.
            styles: Список доступных стилей.
            default_fallback: Промпт по умолчанию, если списки пусты.
            random_selector: Функция выбора случайного элемента (для тестирования).

        Returns:
            Валидированный Prompt.

        Raises:
            ValueError: Если результат невалиден (пробрасывается из Prompt).
        """
        if not frog_prompts or not styles:
            return Prompt(default_fallback)

        frog_prompt = random_selector(frog_prompts)
        style = random_selector(styles)
        prompt_text = f"{frog_prompt}, {style}, {cls.DEFAULT_SUFFIX}"
        return Prompt(prompt_text)
