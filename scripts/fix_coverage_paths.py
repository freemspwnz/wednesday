#!/usr/bin/env python3
"""
Исправляет пути в coverage файлах из Docker контейнера.

Заменяет пути /app/... на локальные пути относительно текущей директории.
"""

import os
import sqlite3
import sys
import traceback

MIN_ARGS = 2  # минимум: имя скрипта и путь к coverage-файлу


def fix_coverage_paths(coverage_file: str) -> None:
    """Исправляет пути /app/ на локальные пути в coverage файле."""
    if not os.path.exists(coverage_file):
        print(f"⚠ Файл покрытия не найден: {coverage_file}")
        return

    # Определяем корень репозитория на хосте:
    # 1. Через переменную окружения HOST_REPO_ROOT (если задана)
    # 2. Иначе через директорию coverage-файла (coverage-файлы лежат в корне репозитория)
    host_repo_root = os.environ.get("HOST_REPO_ROOT")
    if not host_repo_root:
        # Coverage-файл лежит в корне репозитория, его директория и есть корень
        host_repo_root = os.path.dirname(os.path.abspath(coverage_file))

    print(f"Исправляю пути в {coverage_file} (замена /app/ на {host_repo_root}/)")

    try:
        # Coverage использует SQLite для хранения данных
        conn = sqlite3.connect(coverage_file)
        cursor = conn.cursor()

        # Получаем все пути из таблицы file
        cursor.execute("SELECT id, path FROM file")
        files = cursor.fetchall()

        updated = 0
        paths_to_fix = []
        for file_id, path in files:
            if path.startswith("/app/"):
                new_path = path.replace("/app/", f"{host_repo_root}/")
                paths_to_fix.append((file_id, path, new_path))

        # Исправляем пути, обрабатывая дубликаты
        for file_id, old_path, new_path in paths_to_fix:
            cursor.execute("SELECT id FROM file WHERE path = ?", (new_path,))
            existing = cursor.fetchone()

            if existing:
                # Если новый путь уже существует, нужно объединить данные
                old_id = file_id
                new_id = existing[0]
                # Просто обновляем ссылки в таблице arc (объединяем данные покрытия)
                # Coverage сам обработает дубликаты при чтении
                cursor.execute("UPDATE arc SET file_id = ? WHERE file_id = ?", (new_id, old_id))
                # Также обновляем ссылки в других таблицах, если они есть
                try:
                    cursor.execute("UPDATE line_bits SET file_id = ? WHERE file_id = ?", (new_id, old_id))
                except sqlite3.OperationalError:
                    pass  # Таблица может не существовать в старых версиях coverage
                # Удаляем старую запись
                cursor.execute("DELETE FROM file WHERE id = ?", (old_id,))
                updated += 1
                print(f"  Объединено: {old_path} -> {new_path}")
            else:
                # Если нового пути нет, просто обновляем путь
                cursor.execute("UPDATE file SET path = ? WHERE id = ?", (new_path, file_id))
                updated += 1
                print(f"  Исправлено: {old_path} -> {new_path}")

        conn.commit()
        conn.close()

        if updated > 0:
            print(f"✓ Исправлено путей: {updated} в {coverage_file}")
        else:
            print(f"✓ Путей для исправления не найдено в {coverage_file}")
    except Exception as e:
        print(f"⚠ Ошибка при исправлении путей в {coverage_file}: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    if len(sys.argv) < MIN_ARGS:
        print("Использование: python3 scripts/fix_coverage_paths.py <coverage_file>")
        sys.exit(1)

    fix_coverage_paths(sys.argv[1])
