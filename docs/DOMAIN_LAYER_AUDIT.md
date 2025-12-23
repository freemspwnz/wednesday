## Аудит слоя `domain/`

**Дата:** 2025-12-22  
**Аудитор:** GPT-5.1 (AI Assistant в Cursor)  
**Область:** `src/domain/` (`caption_service.py`, `image_generation.py`, `prompt_generation.py`)

---

## 1. Резюме

- **Общая оценка архитектурной чистоты:** **8.5/10**
- **Сильные стороны:**
  - **Чистота слоя:** нет импортов из `infra/`, отсутствует прямой доступ к БД, кэшу, логгеру, HTTP/клиентам — все зависимости заходят через `shared.protocols`.
  - **Чёткая роль доменных сервисов:** валидация и нормализация данных, инкапсуляция правил генерации, отсутствие побочных эффектов.
  - **Правильная работа с исключениями:** маппинг инфраструктурных/клиентских ошибок в доменные (`ImageGenerationError` и др.).
  - **Типизация:** полные type hints, явные контракты входов/выходов.
- **Зоны для улучшения:**
  - **Обработка ошибок и fallback:** в `PromptGenerationService` есть «проглатывание» ошибок без явного доменного сигнала о причине.
  - **Сигнализация ошибок через `None`:** смешиваются две семантики — «клиента нет» и «клиент есть, но не смог сгенерировать».
  - **Магические значения в домене:** дефолтный fallback-промпт захардкожен в доменном сервисе, а не вынесен в конфигурацию/Value Object.

---

## 2. Чистота архитектуры (Layer Integrity)

### 2.1 Зависимости и импорты

- **Факт:** доменные сервисы импортируют только:
  - протоколы из `shared.protocols` (`ITextToImageClient`, `ITextToTextClient`);
  - доменные/общие исключения из `shared.base.exceptions`;
  - конфигурационную модель `PromptFallbackConfig` из `shared.config`;
  - стандартную библиотеку (`random`).
- **Наблюдение:** прямых импортов из `infra/` нет, доступ к сети/БД/файлам/логгерам не выполняется.
- **Вывод:** **границы слоя выдержаны**, зависимости проходят через абстракции (`Protocol`) и общие DTO/конфиг-модели из `shared/`. Это соответствует плану по выносу логирования и retry из `domain` в `app`.

### 2.2 Возможные улучшения

- **Конфигурация в домене:**  
  `PromptGenerationService` зависит от `PromptFallbackConfig` из `shared.config`. Это допустимо при условии, что модель является чистым DTO без знания об окружении (env, файлы и т.п.).  
  **Рекомендация:** зафиксировать контракт `PromptFallbackConfig` как чистый Value Object (без чтения из окружения внутри) и явно документировать это в `shared.config`.

---

## 3. Бизнес-логика и SOLID

### 3.1 SRP и инкапсуляция правил

- **`CaptionService`**
  - Отвечает только за работу с подписями: хранение, валидация на пустой список и выбор случайной подписи.
  - **SRP соблюдён**, логика проста и хорошо инкапсулирована.

- **`ImageGenerationService`**
  - Чётко разделяет:
    - нормализацию промпта (`_normalize_prompt`);
    - валидацию (`_validate_prompt`, константы `MIN_PROMPT_LENGTH`, `MAX_PROMPT_LENGTH`);
    - вызов клиента и маппинг ошибок в `ImageGenerationError`.
  - **SRP соблюдён**, бизнес-правила (ограничения длины, нормализация) оформлены как часть домена, а не инфраструктуры.

- **`PromptGenerationService`**
  - Решает две задачи:
    - генерация промпта через `ITextToTextClient` с graceful degradation;
    - выбор fallback-промпта на основе конфигурации.
  - В целом **SRP формально соблюдён**, но:
    - смешиваются две семантики неудачи (`text_client is None` и ошибки клиента);
    - дефолтный промпт захардкожен строкой в домене.

### 3.2 Расширяемость (OCP)

- **Позитив:**
  - Замена клиентов (`ITextToImageClient`, `ITextToTextClient`) и изменение их retry-политик не требует изменений домена.
  - Расширение правил нормализации/валидации промптов возможно без изменения интерфейсов.
- **Зоны роста:**
  - Для `PromptGenerationService` потенциально полезен отдельный Value Object для «результата генерации промпта», где явно указано:
    - был ли использован AI-клиент;
    - была ли ошибка и какого типа;
    - нужно ли использовать fallback.

---

## 4. Обработка ошибок и отказоустойчивость

### 4.1 `ImageGenerationService.generate`

- **Плюсы:**
  - Валидационные ошибки `ValueError` конвертируются в `ImageGenerationError` с понятным сообщением.
  - Инфраструктурные ошибки клиента (`AuthenticationError`, `NetworkError`, `APIError`, `ClientError`) маппятся в единый доменный тип `ImageGenerationError` с разными текстами.
  - Асинхронность используется корректно: `await` только на клиенте; нет блокирующих синхронных операций.
- **Замечание:**
  - Последний блок `except Exception` оборачивает любые неожиданные ошибки в `ImageGenerationError`. Это **приемлемо** для домена, но:
    - затрудняет различение «нормальных» доменных ошибок и багов/ошибок программирования;
    - может затруднить диагностику на уровне `app/`.

**Рекомендация (умеренная, не критичная):**
- Сузить последний `except` до конкретных ожидаемых типов (или добавить отдельный тип `UnexpectedImageGenerationError`, если нужно логически отделить его на уровне `app/`).

### 4.2 `PromptGenerationService.generate`

- **Плюсы:**
  - Явно реализована стратегия graceful degradation: в случае любых ошибок возвращается `None`, вызывающий код может применить статический fallback.
  - Явное разделение контракта: метод не бросает исключения клиента, а сигнализирует о необходимости fallback через возвращаемое значение.
- **Минусы (архитектурные):**
  - **Проглатывание ошибок:**  
    - Блок `except (AuthenticationError, NetworkError, APIError, ClientError)` возвращает `None` без какой-либо доменной информации.
    - Дополнительный блок `except Exception` полностью гасит любые другие ошибки (включая потенциальные баги).
  - **Неоднозначная семантика `None`:**
    - `None` возвращается как при отсутствии клиента (`text_client is None`), так и при наличии клиента, но с ошибками.

**Рекомендации (важно, но не критично):**

- Ввести доменный объект результата, например:

```python
from dataclasses import dataclass
from enum import Enum, auto


class PromptSource(Enum):
    AI = auto()
    FALLBACK = auto()
    UNAVAILABLE = auto()


@dataclass
class PromptGenerationResult:
    prompt: str | None
    source: PromptSource
```

- Изменить контракт `generate()` так, чтобы он возвращал `PromptGenerationResult`, а не «голый» `str | None`. Тогда вызывающий код сможет:
  - различать «клиент недоступен» и «AI вернул ошибку»;
  - принимать разные решения (логирование, метрики) в `app/` слое, не нарушая чистоту домена.

### 4.3 `PromptGenerationService.get_fallback_prompt`

- **Плюсы:**
  - Корректно обрабатывает отсутствие/пустоту конфигурации.
- **Минусы:**
  - Дефолтный промпт захардкожен строкой:
    - сложнее менять без правок кода;
    - невозможно централизованно переиспользовать/сконфигурировать.

**Рекомендация:**
- Вынести дефолтный промпт в:
  - либо константу в `shared.config` / отдельный Value Object;
  - либо параметр конструктора `PromptGenerationService` с безопасным значением по умолчанию.

---

## 5. Качество кода и типизация

- **Типизация:**
  - Все публичные методы доменных сервисов типизированы.
  - Нет использования `Any` или неявных возвращаемых типов.
- **DRY / повторное использование:**
  - Дублирования логики между доменными сервисами не выявлено.
  - Валидация и нормализация инкапсулированы внутри `ImageGenerationService`.
- **Паттерны:**
  - Использование Protocol-интерфейсов (`ITextToImageClient`, `ITextToTextClient`) соответствует DIP.
  - Отсутствуют инфраструктурные паттерны (retry, circuit breaker) — они грамотно вынесены на уровень клиентов/infra/app.

---

## 6. Управление ресурсами и транзакционность

- В доменном слое **нет прямой работы** с ресурсами (соединения, файлы, транзакции БД).
- Все потенциально ресурсоёмкие операции делегированы абстрактным клиентам (`ITextToImageClient`, `ITextToTextClient`).
- Атомарность и транзакции реализуются на уровне `app/` + `infra/` (см. ранее проведённый аудит `app/`), здесь нарушений нет.

---

## 7. Критические замечания (что исправить сейчас)

Критических архитектурных нарушений (утечек `infra/`, прямой работы с БД/сетевыми клиентами, логгерами) **в слое `domain/` не обнаружено**.  
Однако есть **важные места для улучшения, влияющие на диагностику и прозрачность ошибок**:

1. **`PromptGenerationService.generate` «проглатывает» любые ошибки** (включая потенциальные баги) и сводит всё к `None`.  
   - Рекомендуется:
     - либо ограничить `except Exception` до ожидаемых типов;
     - либо вернуть более выразительный доменный результат (см. ниже пример «Стало»).
2. **Магический fallback-промпт захардкожен строкой** в `PromptGenerationService`.  
   - Рекомендуется вынести его в конфигурацию/константу, чтобы избежать разбросанных по коду значений.

---

## 8. Рекомендации (Best Practices) и примеры «Было» → «Стало»

### 8.1 Улучшение контракта `PromptGenerationService.generate`

**Было (упрощённый фрагмент):**

```python
class PromptGenerationService:
    async def generate(self) -> str | None:
        if self._text_client is None:
            return None

        try:
            prompt = await self._text_client.generate("prompt_for_kandinsky")
            return prompt

        except (AuthenticationError, NetworkError, APIError, ClientError):
            return None
        except Exception:
            return None
```

**Стало (вариант с явным результатом и более честной обработкой ошибок):**

```python
from dataclasses import dataclass
from enum import Enum, auto


class PromptSource(Enum):
    AI = auto()
    FALLBACK_REQUIRED = auto()
    UNAVAILABLE = auto()


@dataclass
class PromptGenerationResult:
    prompt: str | None
    source: PromptSource


class PromptGenerationService:
    async def generate(self) -> PromptGenerationResult:
        if self._text_client is None:
            return PromptGenerationResult(
                prompt=None,
                source=PromptSource.UNAVAILABLE,
            )

        try:
            prompt = await self._text_client.generate("prompt_for_kandinsky")
            return PromptGenerationResult(prompt=prompt, source=PromptSource.AI)

        except (AuthenticationError, NetworkError, APIError, ClientError):
            # ожидаемые ошибки клиента → используем fallback
            return PromptGenerationResult(
                prompt=None,
                source=PromptSource.FALLBACK_REQUIRED,
            )
```

> Примечание: неожиданные ошибки (`Exception`, не входящие в перечисленные) можно либо пробрасывать дальше, либо оборачивать в отдельное доменное исключение, чтобы `app/`-слой мог корректно их залогировать.

### 8.2 Вынесение дефолтного fallback-промпта из кода

**Было (фрагмент):**

```python
class PromptGenerationService:
    def get_fallback_prompt(self) -> str:
        if not self._fallback_config or not self._fallback_config.frog_prompts or not self._fallback_config.styles:
            return "cartoon frog, green, high quality, detailed, Wednesday frog meme"

        frog_prompt = random.choice(self._fallback_config.frog_prompts)
        style = random.choice(self._fallback_config.styles)
        return f"{frog_prompt}, {style}, high quality, detailed, Wednesday frog meme"
```

**Стало (дефолт вынесен в конфиг/константу и параметризован):**

```python
DEFAULT_FALLBACK_PROMPT = "cartoon frog, green, high quality, detailed, Wednesday frog meme"


class PromptGenerationService:
    def __init__(
        self,
        text_client: ITextToTextClient | None = None,
        fallback_config: PromptFallbackConfig | None = None,
        default_fallback_prompt: str = DEFAULT_FALLBACK_PROMPT,
    ) -> None:
        self._text_client = text_client
        self._fallback_config = fallback_config
        self._default_fallback_prompt = default_fallback_prompt

    def get_fallback_prompt(self) -> str:
        if not self._fallback_config or not self._fallback_config.frog_prompts or not self._fallback_config.styles:
            return self._default_fallback_prompt

        frog_prompt = random.choice(self._fallback_config.frog_prompts)
        style = random.choice(self._fallback_config.styles)
        return f"{frog_prompt}, {style}, high quality, detailed, Wednesday frog meme"
```

> Это позволит настраивать дефолтный промпт через DI/конфигурацию без изменений доменного кода.

### 8.3 Уточнение обработки неожиданных ошибок в `ImageGenerationService`

**Было (хвост блока try/except):**

```python
        try:
            image_data = await self._image_client.generate(normalized_prompt, user_id=user_id_str)
            return image_data

        except AuthenticationError as exc:
            raise ImageGenerationError("Ошибка аутентификации при генерации изображения") from exc
        except NetworkError as exc:
            raise ImageGenerationError("Сетевая ошибка при генерации изображения") from exc
        except APIError as exc:
            raise ImageGenerationError(f"Ошибка API при генерации изображения: {exc}") from exc
        except ClientError as exc:
            raise ImageGenerationError("Ошибка клиента при генерации изображения") from exc
        except Exception as e:
            raise ImageGenerationError(f"Ошибка при генерации изображения: {e}") from e
```

**Стало (вариант с отдельным типом для неожиданных ошибок):**

```python
class UnexpectedImageGenerationError(ImageGenerationError):
    """Неожиданная ошибка при генерации изображения (баг или нестандартный сценарий)."""


class ImageGenerationService:
    async def generate(...):
        ...
        try:
            image_data = await self._image_client.generate(normalized_prompt, user_id=user_id_str)
            return image_data

        except AuthenticationError as exc:
            raise ImageGenerationError("Ошибка аутентификации при генерации изображения") from exc
        except NetworkError as exc:
            raise ImageGenerationError("Сетевая ошибка при генерации изображения") from exc
        except APIError as exc:
            raise ImageGenerationError(f"Ошибка API при генерации изображения: {exc}") from exc
        except ClientError as exc:
            raise ImageGenerationError("Ошибка клиента при генерации изображения") from exc
        except Exception as exc:
            # Явно помечаем как неожиданный сценарий
            raise UnexpectedImageGenerationError(
                f"Неожиданная ошибка при генерации изображения: {exc}"
            ) from exc
```

> Это позволит `app/`-слою по типу исключения отличать ожидаемые бизнес-ошибки от инцидентов, требующих отдельного логирования/алертинга.

---

## 9. Заключение

- Слой `domain/` в текущем виде **соответствует принципам чистой архитектуры**: не зависит от `infra/`, использует протоколы и общие DTO из `shared/`, инкапсулирует бизнес-правила и не содержит побочных эффектов.
- Основные улучшения касаются **прозрачности обработки ошибок** и **явности контрактов fallback-логики** в `PromptGenerationService` (разделение сценариев и устранение «немых» `None`).
- Внедрение предложенных изменений повысит наблюдаемость системы, улучшит диагностику и подготовит почву для дальнейшего расширения доменной логики без нарушения границ слоёв.
