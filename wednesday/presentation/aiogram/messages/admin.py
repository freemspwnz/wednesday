"""Тексты админ-команд (ручные ответы до выброса исключений в UC)."""

ACTIVATE_USAGE = "Использование: /activate <telegram_chat_id>"

DEACTIVATE_USAGE = "Использование: /deactivate <telegram_chat_id>"

BAN_USAGE = "Использование: /ban <telegram_id> <дней>"

UNBAN_USAGE = "Использование: /unban <telegram_id>"

MOD_USAGE = "Использование: /mod <telegram_id>"

UNMOD_USAGE = "Использование: /unmod <telegram_id>"

SET_LIMIT_USAGE = "Использование: /set_limit <значение>"

SET_USED_USAGE = "Использование: /set_used <значение>"

BOT_NOT_IN_CHAT = "Бот не состоит в этом чате. Активация невозможна."

BOT_NOT_IN_CHAT_ALREADY_INACTIVE = "Бот не в чате. Чат {tg_chat_id} уже неактивен в базе — активация невозможна."

CHAT_DEACTIVATED_BOT_ABSENT = "Бот не в чате. Чат {tg_chat_id} был активен в базе — деактивирован."

CALLER_ROLE_UNKNOWN = "Не удалось определить роль вызывающего."

CHAT_ACTIVATED = "Чат {tg_chat_id} добавлен в рассылку."

CHAT_DEACTIVATED = "Чат {tg_chat_id} удалён из рассылки."

USER_PROMOTED = "Пользователь {tg_id} назначен админом."

USER_DEMOTED = "У пользователя {tg_id} сняты права админа."

USER_BANNED = "Пользователь {tg_id} забанен на {days} дн."

USER_UNBANNED = "Пользователь {tg_id} разбанен."
