#!/usr/bin/env python3
"""
Объединяет JUnit XML файлы из разных фаз тестирования в один.

Находит все junit-*.xml файлы в корне репозитория и объединяет их в junit.xml.
"""

import glob
import os
import sys
from pathlib import Path

try:
    from junitparser import JUnitXml
except ImportError:
    print("⚠ Ошибка: junitparser не установлен. Установите: pip install junitparser")
    sys.exit(1)

MIN_ARGS = 1  # минимум: имя скрипта


def merge_junit_files(output_file: str = "junit.xml") -> None:
    """Объединяет все junit-*.xml файлы в один junit.xml."""
    # Определяем корень репозитория
    repo_root_str: str = os.environ.get("HOST_REPO_ROOT") or os.getcwd()
    repo_root = Path(repo_root_str).resolve()
    output_path = repo_root / output_file

    # Находим все junit-*.xml файлы
    junit_pattern = str(repo_root / "junit-*.xml")
    junit_files = sorted(glob.glob(junit_pattern))

    if not junit_files:
        print(f"⚠ JUnit XML файлы не найдены по паттерну: {junit_pattern}")
        return

    print(f"Найдено файлов: {len(junit_files)}")

    # Создаём объединённый XML
    merged_xml = None
    files_merged = 0

    for junit_file in junit_files:
        file_path = Path(junit_file)
        if not file_path.exists():
            print(f"⚠ Файл не найден: {junit_file}")
            continue

        try:
            xml = JUnitXml.fromfile(str(file_path))
            if merged_xml is None:
                merged_xml = xml
            else:
                merged_xml += xml
            files_merged += 1
            print(f"  ✓ Добавлен: {file_path.name}")
        except Exception as e:
            print(f"  ⚠ Ошибка при чтении {file_path.name}: {e}")
            continue

    if merged_xml is None or files_merged == 0:
        print("⚠ Нет данных для объединения")
        return

    # Сохраняем объединённый файл
    try:
        merged_xml.write(str(output_path))
        total_tests = sum(suite.tests for suite in merged_xml)
        total_failures = sum(suite.failures for suite in merged_xml)
        total_errors = sum(suite.errors for suite in merged_xml)
        total_skipped = sum(getattr(suite, "skipped", 0) for suite in merged_xml)
        print(f"✓ JUnit XML объединён в {output_file}")
        print(
            f"  Всего тестов: {total_tests}, ошибок: {total_errors}, "
            f"падений: {total_failures}, пропущено: {total_skipped}"
        )
    except Exception as e:
        print(f"⚠ Ошибка при сохранении {output_file}: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    output = sys.argv[1] if len(sys.argv) > 1 else "junit.xml"
    merge_junit_files(output)
