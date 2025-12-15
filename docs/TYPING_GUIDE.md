# Руководство по типизации проекта Wednesday Frog Bot

## Обзор

Проект использует современные практики типизации Python 3.11+ с полным покрытием type hints и строгой проверкой типов через mypy. Все функции, методы классов и атрибуты имеют полные аннотации типов.

## Конфигурация mypy

Конфигурация mypy находится в `pyproject.toml` в секции `[tool.mypy]`:

```toml
[tool.mypy]
python_version = "3.11"
warn_unused_configs = true
disallow_untyped_defs = true
disallow_incomplete_defs = true
ignore_missing_imports = true
check_untyped_defs = true
warn_redundant_casts = true
warn_unused_ignores = true
warn_return_any = true
no_implicit_optional = true
strict_equality = true
exclude = "(?x)(^tests/_doubles/|^tests/utils/|^tests/common/|^tests/fixtures/|^services/celery_app_test\\.py|^services/celery_tasks_test\\.py)"
```

### Особенности конфигурации

- **`disallow_untyped_defs = true`**: Требует явной типизации всех функций и методов
- **`no_implicit_optional = true`**: Запрещает неявные Optional (требует явного `| None` или `Optional[T]`)
- **`strict_equality = true`**: Строгая проверка сравнений типов
- **`ignore_missing_imports = true`**: Игнорирует отсутствующие stub-файлы для сторонних библиотек

## Стандарты импорта

### Использование `from __future__ import annotations`

**Рекомендуется** использовать `from __future__ import annotations` в начале файла для отложенной оценки аннотаций. Это позволяет:

- Использовать типы до их определения (forward references)
- Использовать современный синтаксис без кавычек
- Улучшить производительность импорта

```python
from __future__ import annotations

from typing import Protocol

class MyProtocol(Protocol):
    def method(self) -> MyClass:  # Не нужно писать "MyClass" в кавычках
        ...
```

**Текущая практика в проекте:**
- ✅ Используется в большинстве файлов в `services/` и `utils/`
- ⚠️ Не используется в некоторых файлах `bot/` (можно добавить для консистентности)

### Использование стандартных типов

**Используйте встроенные типы** вместо типов из `typing`:

```python
# ✅ Хорошо (Python 3.9+)
def process_data(items: list[str], config: dict[str, int]) -> dict[str, Any]:
    ...

# ❌ Плохо (устаревший стиль)
from typing import Dict, List
def process_data(items: List[str], config: Dict[str, int]) -> Dict[str, Any]:
    ...
```

**Исключения:** Используйте типы из `typing` для:
- `Protocol` (для dependency injection)
- `TypeVar`, `ParamSpec` (для generic-типов)
- `TypeAlias` (для псевдонимов типов)
- `Final` (для констант)
- `TYPE_CHECKING` (для условных импортов)

## Обработка сложных типов

### Optional и Union

**Предпочтительно использовать оператор `|`** вместо `Optional` и `Union`:

```python
# ✅ Хорошо (современный стиль)
def get_user(user_id: int) -> User | None:
    ...

def process_value(value: str | int | None) -> bool:
    ...

# ⚠️ Допустимо (для обратной совместимости или сложных случаев)
from typing import Optional
def get_user(user_id: int) -> Optional[User]:
    ...
```

**Текущая практика в проекте:**
- Большинство файлов используют `| None` вместо `Optional[T]`
- `Optional` используется в некоторых местах (например, `services/image_generator.py`)

### Типизация Celery Tasks

Celery задачи должны быть типизированы с использованием `Task` из `celery`:

```python
from celery import Task
from typing import Any

@celery_app.task(bind=True, name="wednesday.send_frog")
async def send_wednesday_frog_task(
    self: Task,
    slot_time: str | None = None
) -> dict[str, Any]:
    """Celery задача для отправки изображения жабы.

    Args:
        self: Экземпляр Celery Task.
        slot_time: Время слота в формате "HH:MM" или None.

    Returns:
        Словарь с результатом выполнения.
    """
    ...
```

**Правила типизации Celery задач:**

1. **Первый параметр**: Всегда `self: Task` для задач с `bind=True`
2. **Возвращаемые значения**: Используйте конкретные типы (`dict[str, Any]`, `str`, `int` и т.д.)
3. **Параметры задачи**: Типизируйте все параметры явно
4. **Асинхронные задачи**: Используйте `async def` и типизируйте возвращаемое значение как `Awaitable[T]` или просто `T` (mypy понимает async функции)

**Пример с декоратором:**

```python
from collections.abc import Awaitable, Callable
from typing import Any, ParamSpec, TypeVar
from celery import Task

P = ParamSpec("P")
R = TypeVar("R")

def log_celery_task(
    task_name: str
) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
    """Декоратор для автоматического логирования Celery задач."""
    def decorator(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        async def wrapper(self: Task, *args: object, **kwargs: object) -> Any:
            ...
        return wrapper
    return decorator
```

**Примеры типизации сложных Celery задач:**

#### Задачи с *args и **kwargs

```python
from celery import Task
from typing import Any

@celery_app.task(bind=True, name="wednesday.process_batch")
async def process_batch_task(
    self: Task,
    batch_id: str,
    *args: object,
    **kwargs: object
) -> dict[str, Any]:
    """Celery задача с переменным количеством аргументов.

    Args:
        self: Экземпляр Celery Task.
        batch_id: Идентификатор батча.
        *args: Дополнительные позиционные аргументы.
        **kwargs: Дополнительные именованные аргументы.

    Returns:
        Словарь с результатом обработки батча.
    """
    # Типизация *args и **kwargs как object для гибкости
    # Внутри функции можно проверять типы при необходимости
    ...
```

#### Задачи с callback'ами

```python
from celery import Task
from typing import Any, Callable
from collections.abc import Awaitable

@celery_app.task(bind=True, name="wednesday.process_with_callback")
async def process_with_callback_task(
    self: Task,
    data: dict[str, Any],
    callback: Callable[[dict[str, Any]], Awaitable[None]] | None = None
) -> dict[str, Any]:
    """Celery задача с опциональным callback.

    Args:
        self: Экземпляр Celery Task.
        data: Данные для обработки.
        callback: Опциональная асинхронная функция обратного вызова.

    Returns:
        Результат обработки данных.
    """
    result = await process_data(data)

    if callback:
        await callback(result)

    return result
```

#### Задачи с retry логикой

```python
from celery import Task
from typing import Any
from celery.exceptions import Retry

@celery_app.task(
    bind=True,
    name="wednesday.retryable_task",
    autoretry_for=(ConnectionError, TimeoutError),
    retry_kwargs={"max_retries": 3, "countdown": 60}
)
async def retryable_task(
    self: Task,
    resource_id: str
) -> dict[str, Any]:
    """Celery задача с автоматическим retry.

    Args:
        self: Экземпляр Celery Task.
        resource_id: Идентификатор ресурса для обработки.

    Returns:
        Результат обработки ресурса.

    Raises:
        Retry: Если требуется повторная попытка.
    """
    try:
        result = await process_resource(resource_id)
        return result
    except (ConnectionError, TimeoutError) as exc:
        # Автоматический retry через autoretry_for
        raise self.retry(exc=exc)
```

#### Задачи с сигналами Celery

```python
from celery import Task
from typing import Any
from celery.signals import task_prerun, task_postrun

@task_prerun.connect
def task_prerun_handler(sender: str | None = None, task_id: str | None = None, **kwargs: Any) -> None:
    """Обработчик сигнала перед выполнением задачи."""
    if task_id:
        logger.info(f"Задача {sender} ({task_id}) начинается")

@task_postrun.connect
def task_postrun_handler(
    sender: str | None = None,
    task_id: str | None = None,
    retval: Any = None,
    state: str | None = None,
    **kwargs: Any
) -> None:
    """Обработчик сигнала после выполнения задачи."""
    if task_id:
        logger.info(f"Задача {sender} ({task_id}) завершена со статусом {state}")

@celery_app.task(bind=True, name="wednesday.tracked_task")
async def tracked_task(
    self: Task,
    data: dict[str, Any]
) -> dict[str, Any]:
    """Celery задача с отслеживанием через сигналы.

    Args:
        self: Экземпляр Celery Task.
        data: Данные для обработки.

    Returns:
        Результат обработки данных.
    """
    # Сигналы task_prerun и task_postrun будут вызваны автоматически
    return await process_data(data)
```

### Dependency Injection через Protocol

Проект использует `Protocol` для dependency injection, что позволяет:

- Определять интерфейсы без наследования
- Легко заменять реализации
- Улучшать тестируемость

```python
from __future__ import annotations
from typing import Protocol, runtime_checkable

@runtime_checkable
class ITextToImageClient(Protocol):
    """Интерфейс клиента текст-к-изображению."""

    async def generate(
        self,
        prompt: str,
        user_id: str | None = None
    ) -> bytes | None:
        """Генерирует изображение по текстовому промпту."""
        ...

    async def check_api_status(
        self,
        save_models: bool = True
    ) -> tuple[bool, str, list[str], tuple[str | None, str | None]]:
        """Проверяет статус API."""
        ...
```

**Правила использования Protocol:**

1. **`@runtime_checkable`**: Добавляйте для возможности проверки через `isinstance()`
2. **Методы без реализации**: Используйте `...` (ellipsis) вместо тела метода
3. **Документация**: Всегда документируйте методы Protocol
4. **Типизация**: Полная типизация всех параметров и возвращаемых значений

**Пример использования:**

```python
def create_image_client() -> ITextToImageClient:
    """Создаёт клиент генерации изображений."""
    kandinsky_client = KandinskyClient()
    container = get_image_client_container()
    container.set_initial_client(kandinsky_client)
    return container  # container реализует ITextToImageClient
```

## Пользовательские типы и псевдонимы

### TypeAlias для сложных структур

Используйте `TypeAlias` для создания псевдонимов сложных типов:

```python
from __future__ import annotations
from typing import TypeAlias
import redis.asyncio as redis

from utils.redis_client import _InMemoryRedis

# Псевдоним для Redis бэкенда (может быть реальным Redis или in-memory fallback)
RedisBackend: TypeAlias = redis.Redis | _InMemoryRedis
```

**Примеры использования в проекте:**

```python
# services/user_state_store.py
RedisBackend: TypeAlias = redis.Redis | _InMemoryRedis

# services/rate_limiter.py
RedisBackend: TypeAlias = redis.Redis | _InMemoryRedis

# services/prompt_cache.py
RedisBackend: TypeAlias = redis.Redis | _InMemoryRedis
```

**Рекомендации:**

1. **Используйте TypeAlias** для сложных типов, которые повторяются в нескольких местах
2. **Размещайте TypeAlias** в начале файла после импортов
3. **Документируйте назначение** псевдонима в комментарии
4. **Используйте понятные имена** (например, `RedisBackend`, `UserID`, `ChatSettings`)

### Псевдонимы для простых типов

Для простых типов можно использовать обычные type aliases без `TypeAlias`:

```python
# ✅ Хорошо для простых случаев
UserID = int
ChatID = int
MessageText = str

# ✅ Хорошо для сложных случаев
from typing import TypeAlias
ChatSettings: TypeAlias = dict[str, Any]
UserState: TypeAlias = dict[str, str | int | bool]
```

## Специфика фреймворка Telegram Bot

### Типизация обработчиков

Обработчики команд Telegram бота должны быть типизированы следующим образом:

```python
from telegram import Update
from telegram.ext import ContextTypes

async def command_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Обработчик команды.

    Args:
        update: Объект обновления от Telegram API.
        context: Контекст обработчика с данными бота.
    """
    user_id = update.effective_user.id if update.effective_user else None
    chat_id = update.effective_chat.id if update.effective_chat else None
    ...
```

**Правила типизации обработчиков:**

1. **`Update`**: Тип из `telegram` для объектов обновлений
2. **`ContextTypes.DEFAULT_TYPE`**: Тип контекста обработчика (используется по умолчанию)
3. **Возвращаемое значение**: Обычно `None` для обработчиков команд
4. **Проверка на None**: Всегда проверяйте `update.effective_user`, `update.effective_chat` и т.д. на `None`

**Пример из проекта:**

```python
# bot/handlers.py
async def set_frog_limit_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Обработчик команды /set_frog_limit."""
    if not update.effective_user:
        return
    ...
```

### Типизация Application и других объектов

```python
from telegram.ext import Application

class WednesdayBot:
    def __init__(self) -> None:
        self.application: Application = Application.builder().token(token).build()
        self.chat_id: str | None = config.chat_id
        self.is_running: bool = False
```

## Настройка MyPy

### Запуск проверки типов

```bash
# Проверка всех файлов
mypy .

# Проверка конкретного файла
mypy bot/wednesday_bot.py

# Проверка с HTML-отчётом
mypy . --html-report mypy-report

# Проверка с игнорированием конкретных ошибок (для постепенной миграции)
mypy . --ignore-missing-imports
```

### Исключения из проверки

Для исключения файлов или модулей используйте `exclude` в `pyproject.toml`:

```toml
[tool.mypy]
exclude = "(?x)(^tests/_doubles/|^tests/utils/|^tests/common/)"
```

Для переопределения правил для конкретных модулей:

```toml
[[tool.mypy.overrides]]
module = "tests.*"
disallow_untyped_defs = false
check_untyped_defs = false
ignore_errors = true
```

### Использование `# type: ignore`

Используйте `# type: ignore` только при необходимости и всегда с конкретным кодом ошибки:

```python
# ✅ Хорошо - с конкретным кодом ошибки
result = some_call()  # type: ignore[assignment]

# ✅ Хорошо - с комментарием объяснения
result = dynamic_attr  # type: ignore[attr-defined]  # Добавляется динамически

# ❌ Плохо - без объяснения
result = some_call()  # type: ignore
```

## Типы в проекте

### Основные используемые типы

- **`str | None`** / **`Optional[str]`** - для строк, которые могут быть None
- **`dict[str, Any]`** - для словарей с произвольными значениями
- **`list[T]`** - для списков элементов типа T
- **`tuple[T, ...]`** - для кортежей переменной длины
- **`Callable[[...], T]`** - для функций и методов
- **`Awaitable[T]`** - для асинхронных операций
- **`TypeVar`** - для generic-типов
- **`ParamSpec`** - для типизации декораторов

### Специфичные типы проекта

**Telegram Bot:**
- `Update` - объекты обновлений Telegram
- `ContextTypes.DEFAULT_TYPE` - контекст обработчиков
- `Application` - приложение бота
- ID чатов: `int`
- Пути к файлам: `str` или `Path`

**Services:**
- Промпты: `str`
- Изображения: `bytes`
- Время: `datetime`
- Celery задачи: `Task` из `celery`
- Redis бэкенд: `RedisBackend` (TypeAlias)

**Utils:**
- JSON хранилища: `dict[str, Any]`
- Метрики: `dict[str, Any]`
- Логгеры: `Logger` (loguru)

## Рекомендации по поддержанию тип-безопасности

### 1. Всегда добавляйте типы при создании новых функций

```python
# ✅ Хорошо
def process_message(text: str, user_id: int) -> bool:
    ...

# ❌ Плохо
def process_message(text, user_id):
    ...
```

### 2. Используйте конкретные типы вместо Any

```python
# ✅ Хорошо
def get_user(user_id: int) -> User | None:
    ...

# ⚠️ Допустимо только в исключительных случаях
def process_data(data: Any) -> Any:  # type: ignore[no-any-return]
    ...
```

### 3. Типизируйте атрибуты классов

```python
class MyClass:
    def __init__(self) -> None:
        self.name: str = ""
        self.count: int = 0
        self.items: list[str] = []
        self.optional_field: str | None = None
```

### 4. Используйте TypedDict для сложных структур данных

```python
from typing import TypedDict

class UserData(TypedDict):
    id: int
    name: str
    email: str | None
```

### 5. Используйте Final для констант

```python
from typing import Final

MAX_RETRIES: Final[int] = 3
DEFAULT_TIMEOUT: Final[float] = 30.0
```

### 6. Проверяйте типы перед коммитом

```bash
# Запускайте mypy перед коммитом
mypy .

# Добавьте в pre-commit hook
mypy . || exit 1
```

### 7. Используйте TYPE_CHECKING для условных импортов

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from utils.metrics import Metrics

class ImageGenerator:
    def __init__(self, metrics: Metrics | None = None) -> None:
        ...
```

## Расширение покрытия типов

### Следующие шаги для улучшения

1. **Добавить TypedDict для JSON структур**
   ```python
   class ChatData(TypedDict):
       chat_id: int
       title: str
       settings: dict[str, Any]
   ```

2. **Создать больше Protocol для зависимостей**
   ```python
   class ImageGeneratorProtocol(Protocol):
       async def generate_frog_image(
           self,
           user_id: int | None = None
       ) -> tuple[bytes, str] | None: ...
   ```

3. **Добавить Literal для фиксированных значений**
   ```python
   from typing import Literal

   Status = Literal["pending", "running", "stopped"]
   TaskStatus = Literal["success", "failed", "in_progress"]
   ```

4. **Использовать Final для констант**
   ```python
   MAX_RETRIES: Final[int] = 3
   DEFAULT_QUEUE: Final[str] = "wednesday"
   ```

## CI/CD интеграция

Добавьте проверку типов в CI:

```yaml
# .github/workflows/types.yml
- name: Run mypy
  run: |
    pip install mypy
    mypy .
```

Или добавьте в существующий workflow:

```yaml
- name: Type checking
  run: |
    pip install mypy
    mypy . || echo "Type checking failed"
```

## Известные ограничения

1. **Игнорирование импортов третьих сторон**
   - `ignore_missing_imports = True` используется для библиотек без stub-файлов
   - Telegram Bot, loguru, aiohttp и другие имеют ограниченную поддержку типов

2. **Динамические атрибуты**
   - Некоторые атрибуты добавляются динамически (например, `bot_data`)
   - Используются комментарии `# type: ignore` там, где необходимо

3. **Смешанное использование Optional и `| None`**
   - В проекте встречаются оба стиля
   - Рекомендуется постепенно мигрировать на `| None` для консистентности

## Полезные ресурсы

- [PEP 484 - Type Hints](https://peps.python.org/pep-0484/)
- [PEP 526 - Variable Annotations](https://peps.python.org/pep-0526/)
- [PEP 563 - Postponed Evaluation of Annotations](https://peps.python.org/pep-0563/)
- [PEP 604 - Allow writing union types as X | Y](https://peps.python.org/pep-0604/)
- [mypy Documentation](https://mypy.readthedocs.io/)
- [Typing Module Documentation](https://docs.python.org/3/library/typing.html)
- [Protocol Documentation](https://mypy.readthedocs.io/en/stable/protocols.html)

## Заключение

Проект использует современные практики типизации Python 3.11+ с полным покрытием type hints. Это улучшает:

- ✅ Читаемость кода
- ✅ Безопасность типов
- ✅ Поддержку IDE (автодополнение, проверка ошибок)
- ✅ Выявление ошибок на этапе разработки
- ✅ Рефакторинг и поддержку кода

Для поддержания тип-безопасности рекомендуется:

- Запускать mypy перед коммитами
- Использовать строгую проверку типов в IDE
- Регулярно проверять покрытие типов
- Постепенно мигрировать на современный синтаксис (`|` вместо `Union`, стандартные типы вместо `typing.Dict` и т.д.)
- Добавлять `from __future__ import annotations` в новые файлы
