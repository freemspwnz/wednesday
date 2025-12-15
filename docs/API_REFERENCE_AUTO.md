# Автоматический справочник API 🐸

> **Важно:** Эта документация автоматически генерируется из docstrings исходного кода проекта.  
> Для обновления документации после изменений в коде выполните: `mkdocs build`

---

## 🎯 Обработчики команд бота

Модуль содержит класс `CommandHandlers` для обработки всех команд Telegram-бота.

::: bot.handlers.CommandHandlers
    options:
      show_root_heading: true
      show_root_full_path: false
      show_source: true
      members_order: source
      show_signature_annotations: true
      group_by_category: true

---

## 🖼️ Генератор изображений

Сервис для генерации изображений жабы с использованием Kandinsky API и других моделей.

::: services.image_generator.ImageGenerator
    options:
      show_root_heading: true
      show_root_full_path: false
      show_source: true
      members_order: source
      show_signature_annotations: true
      group_by_category: true

---

## ⚙️ Celery задачи

Асинхронные задачи для фоновой обработки и планирования.

::: services.celery_tasks
    options:
      show_root_heading: true
      show_root_full_path: false
      show_source: true
      members_order: source
      show_signature_annotations: true
      group_by_category: true

---

## 🤖 Основной бот

Класс `WednesdayBot` для управления Telegram-ботом.

::: bot.wednesday_bot.WednesdayBot
    options:
      show_root_heading: true
      show_root_full_path: false
      show_source: true
      members_order: source
      show_signature_annotations: true
      group_by_category: true

---

## 📅 Планировщик задач

Сервис для планирования автоматической отправки изображений.

::: services.scheduler.TaskScheduler
    options:
      show_root_heading: true
      show_root_full_path: false
      show_source: true
      members_order: source
      show_signature_annotations: true
      group_by_category: true

---

## 🎨 Клиенты для генерации изображений

Интерфейсы и реализации клиентов для работы с внешними API.

### Интерфейсы

::: services.clients.interfaces.ITextToImageClient
    options:
      show_root_heading: true
      show_root_full_path: false
      show_source: true
      members_order: source
      show_signature_annotations: true

::: services.clients.interfaces.ITextToTextClient
    options:
      show_root_heading: true
      show_root_full_path: false
      show_source: true
      members_order: source
      show_signature_annotations: true

### Реализации

::: services.clients.kandinsky.KandinskyClient
    options:
      show_root_heading: true
      show_root_full_path: false
      show_source: true
      members_order: source
      show_signature_annotations: true
      group_by_category: true

::: services.clients.gigachat_text.GigaChatTextClient
    options:
      show_root_heading: true
      show_root_full_path: false
      show_source: true
      members_order: source
      show_signature_annotations: true
      group_by_category: true

---

## 🔄 Rate Limiter и Circuit Breaker

Механизмы ограничения частоты запросов и защиты от перегрузки.

::: services.rate_limiter.CircuitBreaker
    options:
      show_root_heading: true
      show_root_full_path: false
      show_source: true
      members_order: source
      show_signature_annotations: true
      group_by_category: true

---

## 💾 Хранилища данных

Утилиты для работы с хранилищами данных.

::: utils.chats_store.ChatsStore
    options:
      show_root_heading: true
      show_root_full_path: false
      show_source: true
      members_order: source
      show_signature_annotations: true
      group_by_category: true

::: utils.admins_store.AdminsStore
    options:
      show_root_heading: true
      show_root_full_path: false
      show_source: true
      members_order: source
      show_signature_annotations: true
      group_by_category: true

::: utils.models_store.ModelsStore
    options:
      show_root_heading: true
      show_root_full_path: false
      show_source: true
      members_order: source
      show_signature_annotations: true
      group_by_category: true

::: utils.prompts_store.PromptsStore
    options:
      show_root_heading: true
      show_root_full_path: false
      show_source: true
      members_order: source
      show_signature_annotations: true
      group_by_category: true

::: utils.images_store.ImagesStore
    options:
      show_root_heading: true
      show_root_full_path: false
      show_source: true
      members_order: source
      show_signature_annotations: true
      group_by_category: true

---

## 📊 Метрики и мониторинг

Утилиты для сбора и отслеживания метрик.

::: utils.metrics.Metrics
    options:
      show_root_heading: true
      show_root_full_path: false
      show_source: true
      members_order: source
      show_signature_annotations: true
      group_by_category: true

::: utils.usage_tracker.UsageTracker
    options:
      show_root_heading: true
      show_root_full_path: false
      show_source: true
      members_order: source
      show_signature_annotations: true
      group_by_category: true

---

## 🔧 Конфигурация

Модуль конфигурации приложения.

::: utils.config.config
    options:
      show_root_heading: true
      show_root_full_path: false
      show_source: true
      members_order: source
      show_signature_annotations: true

---

## 📝 Примечания

- Все классы и функции документированы с использованием Google-style docstrings
- Документация обновляется автоматически при сборке MkDocs
- Для просмотра документации локально используйте: `mkdocs serve`
- Для сборки статической документации используйте: `mkdocs build`
