## Аудит слоя `domain/` (актуальное состояние на 2025‑12‑23)

**Цель:** найти архитектурные нарушения, протечки абстракций и зоны для рефакторинга в текущем коде `src/domain`.

Проверялись файлы:
- `src/domain/__init__.py`
- `src/domain/value_objects.py`
- `src/domain/prompt_generation.py`
- `src/domain/image_generation.py`
- `src/domain/caption_service.py`
а также связанный application‑сервис и базовые исключения:
- `src/app/prompt_service.py`
- `src/shared/base/exceptions.py`

---

## Критические замечания (что нужно исправить сейчас)

На момент аудита **критических архитектурных нарушений не обнаружено**:
- нет прямых импортов из `infra/` или работы с БД/кэшем/файловой системой в `src/domain`;
- все внешние зависимости проходят через протоколы и конфигурационные объекты из `shared/`;
- доменные сервисы транслируют инфраструктурные ошибки в доменные исключения.

Тем не менее, есть **две зоны, которые потенциально могут стать источником проблем**, если их не зафиксировать явно:

1. **Жёстко закодированный идентификатор промпта в `PromptGenerationService`**
   - **Где:** `src/domain/prompt_generation.py`, метод `generate`
   - **Суть:** строковый литерал `"prompt_for_kandinsky"` зашит внутри доменного сервиса. Это:
     - затрудняет переиспользование сервиса для других типов промптов;
     - усложняет конфигурацию/перенастройку без правки доменного кода;
     - чуть размывает SRP (часть конфигурации зашита в код).

   **Риск:** при расширении числа типов промптов или появлении разных моделей генерации придётся модифицировать доменный сервис вместо того, чтобы прокидывать конфигурацию извне.

2. **Смешение ответственности выбора конкретной fallback‑формулы и сервиса генерации**
   - **Где:** `src/domain/prompt_generation.py`, метод `get_fallback_prompt`
   - **Суть:** логика конструирования текстового fallback‑промпта (`"{frog_prompt}, {style}, high quality, detailed, Wednesday frog meme"`) находится непосредственно в `PromptGenerationService`.

   **Риск:** при изменении формата fallback‑промптов или добавлении новых стратегий придётся менять доменный сервис вместо изолированной стратегии/Value Object. Это не критично сейчас, но может привести к разрастанию класса.

---

## Рекомендации по улучшению (Best practices)

### 1. Чистота архитектуры (Layer Integrity)

**Текущее состояние:**
- Доменные сервисы (`PromptGenerationService`, `ImageGenerationService`, `CaptionService`) не зависят от модулей `infra/` и `app/`.
- Все внешние зависимости приходят через:
  - протоколы (`ITextToTextClient`, `ITextToImageClient`) из `shared.protocols`;
  - конфигурационные объекты (`PromptFallbackConfig`) из `shared.config`;
  - доменные/аппликационные исключения из `shared.base.exceptions`.

**Вывод:** слой `domain/` в целом **чистый**, зависимости инвертированы корректно, протечек инфраструктуры не найдено.

**Рекомендации:**
- Явно задокументировать в `docs/dev/domain-layer-audit/DOMAIN_AUDIT.md`, что:
  - конфиг‑объекты из `shared.config` допустимы в домене;
  - любые конкретные реализации клиентов/кэшей/логгеров должны находиться в `infra/` и подключаться через протоколы.

---

### 2. Бизнес‑логика и SOLID

#### 2.1. SRP и размещение логики

**Плюсы:**
- Вся логика валидации и нормализации промпта корректно вынесена в `Value Object` `Prompt` (`src/domain/value_objects.py`).
- `ImageGenerationService` использует `Prompt` и не дублирует бизнес‑правила валидации.
- `CaptionService` инкапсулирует правила выбора подписи (даже если они сейчас минимальны).

**Зоны роста:**
1. **`PromptGenerationService` совмещает:**
   - обращение к клиенту генерации текста;
   - доменную интерпретацию ошибок клиента (map в `PromptGenerationError`);
   - стратегию формирования fallback‑промпта.

   Сейчас объём логики небольшой, но при расширении стратегий fallback/источников промптов сервис может начать разрастаться.

**Рекомендация (не критично, но улучшит SRP):**
- Вынести стратегию fallback в отдельный компонент (например, `PromptFallbackStrategy` или `PromptTemplateBuilder`), который:
  - получает `PromptFallbackConfig`;
  - на основе бизнес‑правил возвращает готовую строку промпта.
- Тогда `PromptGenerationService` останется координатором:
  - "попробовать сгенерировать через клиента";
  - "если не получилось — спросить стратегию fallback".

#### 2.2. Расширяемость (OCP)

**Что хорошо:**
- Использование протоколов (`ITextToTextClient`, `ITextToImageClient`) даёт возможность подменять реализации без изменения доменного кода.
- Вынесение `Prompt` в отдельный Value Object упрощает расширение правил валидации/нормализации без модификации сервисов.

**Рекомендации:**
- Для `PromptGenerationService`:
  - параметризовать идентификатор промпта (`"prompt_for_kandinsky"`) через:
    - аргумент конструктора, **или**
    - поле конфигурации (`PromptGenerationConfig`), инжектируемой извне;
  - это позволит обслуживать несколько типов промптов в будущем без изменения класса.

---

### 3. Обработка ошибок и отказоустойчивость

#### 3.1. Трансляция инфраструктурных ошибок в доменные

**`ImageGenerationService`:**
- Корректно перехватывает:
  - `AuthenticationError`, `NetworkError`, `APIError`, `ClientError`;
  - мапит их на `ImageGenerationError` или `UnexpectedImageGenerationError`.
- Это соответствует ожиданиям: доменный сервис даёт высокоуровневую причину сбоя, не "просвечивая" детали реализации клиента.

**`PromptGenerationService`:**
- Валидирует наличие `_text_client` и бросает `PromptGenerationError`, если клиент не предоставлен.
- Любые ошибки клиента (`AuthenticationError`, `NetworkError`, `APIError`, `ClientError`) оборачиваются в `PromptGenerationError` с информативным сообщением.
- Ошибки валидации промпта (`ValueError` из `Prompt`) также транслируются в `PromptGenerationError`.
- Неожиданные ошибки попадают в `PromptGenerationError` с явным текстом "Неожиданная ошибка...".

**Вывод:** стратегия трансляции ошибок в доменные исключения реализована **корректно и единообразно**.

#### 3.2. Fallback и "проглатывание" ошибок

- Fallback‑логика реализована **не в доменном слое**, а в application‑сервисе `PromptService` (`src/app/prompt_service.py`):
  - при `PromptGenerationError` идёт попытка взять fallback‑промпт;
  - при ошибке fallback создаётся `UnexpectedPromptError` и ошибка логируется.
- Таким образом:
  - доменный слой **не занимается graceful degradation** — он только сигнализирует об ошибках;
  - application‑слой осознанно решает, как деградировать.

**Вывод:** "проглатывания" ошибок на доменном уровне нет, модели ответственности распределены корректно.

#### 3.3. Async/await

- Все методы, взаимодействующие с клиентами, объявлены как `async`.
- Нет синхронных блокирующих операций внутри async‑методов.
- Вызовы клиентов выполняются через `await`, без пропуска await/забытых корутин.

**Вывод:** с точки зрения асинхронности доменный слой реализован корректно.

---

### 4. Качество кода и типизация

#### 4.1. Type hints

- Все публичные методы доменных сервисов и Value Object имеют явные аннотации типов.
- Используется современный синтаксис `X | Y` вместо `Optional[X]`.
- Коллекции типизированы (`list[str] | tuple[str, ...]` в `CaptionService` и т.п.).

**Рекомендации:**
- Продолжать придерживаться полного покрытия типами, особенно при добавлении новых методов;
- Для конфиг‑объектов и протоколов в `shared/` следить за строгой типизацией полей — это критично для того, чтобы домен оставался "тонким" и предсказуемым.

#### 4.2. DRY и переиспользование

- Валидация/нормализация промпта **не дублируется** — сосредоточена в `Prompt`.
- Обработка ошибок в `ImageGenerationService` и `PromptGenerationService` построена по схожему паттерну ("поймал инфраструктурное → обернул в доменное").
- `CaptionService` не дублирует логику других компонентов.

**Вывод:** явного дублирования логики не выявлено, код достаточно DRY.

#### 4.3. Паттерны и базовые классы

- В доменном слое **осознанно не используется** `BaseService` — он применяется только в application‑слое (`PromptService`), что соответствует принципу разделения слоёв.
- Retry‑логика, судя по docstring‑ам, ожидается на уровне клиентов (`ITextToImageClient`, `ITextToTextClient`), а не в домене — это корректно, чтобы не "затащить" инфраструктурные детали в domain.

---

### 5. Управление ресурсами и транзакционность

- Доменные сервисы не управляют явно внешними ресурсами:
  - нет открытия/закрытия файлов;
  - нет прямой работы с соединениями к БД или сетевыми соединениями;
  - транзакции БД не используются.
- Вся работа с ресурсами делегирована в клиентов, реализующих протоколы из `shared.protocols`.

**Вывод:** нарушений транзакционной целостности или неправильного управления ресурсами в доменном слое не обнаружено.

**Рекомендация:** если в будущем появятся доменные операции, требующие атомарности на уровне нескольких инфраструктурных операций, оборачивать их в application‑сервисы, а не переносить транзакционность в domain.

---

## Конкретные примеры рефакторинга ("Было" → "Стало")

Ниже — примеры улучшений, которые не являются критическими, но повысят гибкость и читаемость доменного слоя.

### Пример 1: Конфигурируемый идентификатор промпта в `PromptGenerationService`

**Было** (`src/domain/prompt_generation.py`, упрощённо):

```startLine:endLine:src/domain/prompt_generation.py
        try:
            prompt_text = await self._text_client.generate("prompt_for_kandinsky")
            # Валидация промпта сразу после получения от клиента
            return Prompt(prompt_text)
```

**Стало** (предлагаемый вариант с конфигурацией):

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class PromptGenerationConfig:
    """Конфигурация генерации промптов."""

    preset_id: str = "prompt_for_kandinsky"


class PromptGenerationService:
    def __init__(
        self,
        text_client: ITextToTextClient | None = None,
        fallback_config: PromptFallbackConfig | None = None,
        generation_config: PromptGenerationConfig | None = None,
    ) -> None:
        self._text_client = text_client
        self._fallback_config = fallback_config
        self._config = generation_config or PromptGenerationConfig()

    async def generate(self) -> Prompt:
        if self._text_client is None:
            raise PromptGenerationError("Text client is not available")

        try:
            prompt_text = await self._text_client.generate(self._config.preset_id)
            return Prompt(prompt_text)
        except (AuthenticationError, NetworkError, APIError, ClientError) as exc:
            raise PromptGenerationError(
                f"Ошибка клиента при генерации промпта: {exc}"
            ) from exc
```

**Эффект:**
- доменный сервис становится конфигурируемым без изменения кода;
- легче тестировать разные сценарии с разными `preset_id`.

---

### Пример 2: Выделение стратегии формирования fallback‑промпта

**Было** (`src/domain/prompt_generation.py`, упрощённо):

```startLine:endLine:src/domain/prompt_generation.py
        try:
            if not self._fallback_config.frog_prompts or not self._fallback_config.styles:
                fallback_text = self._fallback_config.default_fallback_prompt
            else:
                frog_prompt = random.choice(self._fallback_config.frog_prompts)
                style = random.choice(self._fallback_config.styles)
                fallback_text = f"{frog_prompt}, {style}, high quality, detailed, Wednesday frog meme"

            # Валидация fallback промпта
            return Prompt(fallback_text)
        except ValueError as exc:
            raise PromptGenerationError(f"Невалидный fallback промпт: {exc}") from exc
```

**Стало** (предлагаемый вариант с отдельной стратегией):

```python
class FallbackPromptBuilder:
    """Стратегия построения fallback‑промпта."""

    def __init__(self, config: PromptFallbackConfig) -> None:
        self._config = config

    def build(self) -> str:
        if not self._config.frog_prompts or not self._config.styles:
            return self._config.default_fallback_prompt

        frog_prompt = random.choice(self._config.frog_prompts)
        style = random.choice(self._config.styles)
        return f"{frog_prompt}, {style}, high quality, detailed, Wednesday frog meme"


class PromptGenerationService:
    def __init__(
        self,
        text_client: ITextToTextClient | None = None,
        fallback_config: PromptFallbackConfig | None = None,
    ) -> None:
        self._text_client = text_client
        self._fallback_config = fallback_config
        self._fallback_builder = (
            FallbackPromptBuilder(fallback_config) if fallback_config else None
        )

    def get_fallback_prompt(self) -> Prompt:
        if not self._fallback_builder:
            raise PromptGenerationError(
                "Fallback config is required. Provide PromptFallbackConfig during initialization."
            )

        try:
            fallback_text = self._fallback_builder.build()
            return Prompt(fallback_text)
        except ValueError as exc:
            raise PromptGenerationError(f"Невалидный fallback промпт: {exc}") from exc
```

**Эффект:**
- `PromptGenerationService` избавляется от знания о конкретной формуле текста;
- стратегию можно заменить/расширять независимо от сервиса.

---

### Пример 3: Улучшение тестируемости `CaptionService` через инъекцию источника случайности

**Было** (`src/domain/caption_service.py`, упрощённо):

```startLine:endLine:src/domain/caption_service.py
    def get_random_caption(self) -> str:
        """Возвращает случайную подпись для изображения.

        Returns:
            Случайная подпись из доступных.
        """
        return random.choice(self._captions)
```

**Стало** (предлагаемый вариант, если понадобится детерминированность в тестах):

```python
from random import Random


class CaptionService:
    def __init__(
        self,
        captions: list[str] | tuple[str, ...],
        *,
        rng: Random | None = None,
    ) -> None:
        if not captions:
            raise ValueError("Список подписей не может быть пустым")
        self._captions = list(captions)
        self._rng = rng or Random()

    def get_random_caption(self) -> str:
        return self._rng.choice(self._captions)
```

**Эффект:**
- можно подставить детерминированный `Random` в тестах;
- источник случайности становится явной зависимостью, что делает поведение сервиса более предсказуемым.

---

## Итоговое резюме

- **Критических проблем в слое `domain/` не обнаружено**: архитектура чистая, зависимости инвертированы, протечек инфраструктуры нет.
- **Доменные правила валидации и нормализации промптов корректно инкапсулированы в Value Object `Prompt`**, использование Value Objects и протоколов отвечает принципам DDD и чистой архитектуры.
- Основные рекомендации касаются **повышения конфигурируемости и SRP** (`PromptGenerationService`) и **улучшения тестируемости** (`CaptionService`) без изменения текущего поведения.
