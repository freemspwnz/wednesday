#!/usr/bin/env python3
"""
Скрипт проверки качества тестов.

Проверяет:
1. Запрет новых autouse фикстур (кроме разрешённых)
2. Наличие маркеров ресурсов (db, redis, celery, slow) где нужно
3. Соответствие маркеров использованным фикстурам

Использование:
    python tests/check_test_quality.py
"""

import ast
import sys
from pathlib import Path
from typing import TypedDict

# Разрешённые autouse фикстуры
ALLOWED_AUTOUSE_FIXTURES = {
    "session_env_defaults",
    "base_env",
    "patch_models_store",
}

# Валидные маркеры тестов
VALID_MARKERS = {
    "unit",
    "integration",
    "e2e",
    "infra",
    "db",
    "redis",
    "celery",
    "slow",
}

# Исключаемые аргументы (не фикстуры)
NON_FIXTURE_ARGS = {"self", "mocker", "monkeypatch", "tmp_path", "tmp_path_factory"}

# Соответствие фикстур и маркеров
FIXTURE_TO_MARKER = {
    "cleanup_tables": "db",
    "postgres_transaction": "db",
    "celery_test_queues": "celery",
    "celery_worker_ready": "celery",
    "reset_singletons": None,  # не требует маркера
}

# Соответствие маркеров и фикстур (обратное)
MARKER_TO_FIXTURES = {
    "db": ["cleanup_tables", "postgres_transaction"],
    "redis": [],  # проверяется по использованию redis клиента
    "celery": ["celery_test_queues", "celery_worker_ready"],
    "slow": [],  # проверяется по таймаутам и долгим операциям
}


class TestInfo(TypedDict):
    """Информация о тесте."""

    name: str
    line: int
    file: Path
    markers: set[str]
    fixtures: set[str]
    args: list[str]


class TestQualityChecker:
    """Проверяет качество тестов."""

    def __init__(self, tests_dir: Path, conftest_path: Path) -> None:
        self.tests_dir = tests_dir
        self.conftest_path = conftest_path
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def check_autouse_fixtures(self) -> None:
        """Проверяет autouse фикстуры в conftest.py."""
        if not self.conftest_path.exists():
            return

        try:
            with open(self.conftest_path, encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            self.errors.append(f"Не удалось прочитать {self.conftest_path}: {e}")
            return

        try:
            tree = ast.parse(content, filename=str(self.conftest_path))
        except SyntaxError as e:
            self.errors.append(f"Синтаксическая ошибка в {self.conftest_path}: {e}")
            return

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # Проверяем декораторы
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Call):
                        if isinstance(decorator.func, ast.Attribute):
                            if decorator.func.attr == "fixture":
                                # Проверяем аргументы fixture
                                for keyword in decorator.keywords:
                                    if keyword.arg == "autouse":
                                        if isinstance(keyword.value, ast.Constant):
                                            if keyword.value.value is True:
                                                fixture_name = node.name
                                                if fixture_name not in ALLOWED_AUTOUSE_FIXTURES:
                                                    allowed = ", ".join(ALLOWED_AUTOUSE_FIXTURES)
                                                    self.warnings.append(
                                                        f"Обнаружена новая autouse фикстура '{fixture_name}' "
                                                        f"в {self.conftest_path}:{node.lineno}. "
                                                        f"Разрешены только: {allowed}. "
                                                        f"Если фикстура действительно нужна всем тестам, "
                                                        f"обсудите с командой."
                                                    )

        # Проверяем также через поиск строки (на случай сложных случаев)
        lines = content.split("\n")
        for i, line in enumerate(lines, 1):
            if "@pytest.fixture" in line and "autouse=True" in line:
                # Пытаемся найти имя фикстуры
                for j in range(i, min(i + 5, len(lines))):
                    if "def " in lines[j]:
                        fixture_name = lines[j].split("def ")[1].split("(")[0].strip()
                        if fixture_name not in ALLOWED_AUTOUSE_FIXTURES:
                            self.warnings.append(
                                f"Обнаружена новая autouse фикстура '{fixture_name}' в {self.conftest_path}:{j + 1}. "
                                f"Разрешены только: {', '.join(ALLOWED_AUTOUSE_FIXTURES)}."
                            )
                        break

    def parse_test_file(self, file_path: Path) -> list[TestInfo]:
        """Парсит тестовый файл и возвращает информацию о тестах."""
        tests: list[TestInfo] = []

        try:
            with open(file_path, encoding="utf-8") as f:
                content = f.read()
        except Exception:
            return tests

        try:
            tree = ast.parse(content, filename=str(file_path))
        except SyntaxError:
            return tests

        # Собираем маркеры на уровне модуля (pytestmark)
        module_markers = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "pytestmark":
                        if isinstance(node.value, ast.List):
                            for elt in node.value.elts:
                                # Обрабатываем pytest.mark.xxx
                                if isinstance(elt, ast.Call):
                                    if isinstance(elt.func, ast.Attribute):
                                        # pytest.mark.xxx(...)
                                        if isinstance(elt.func.value, ast.Attribute):
                                            if isinstance(elt.func.value.value, ast.Name):
                                                if (
                                                    elt.func.value.value.id == "pytest"
                                                    and elt.func.value.attr == "mark"
                                                ):
                                                    # pytest.mark.xxx
                                                    marker_name = elt.func.attr
                                                    if marker_name in VALID_MARKERS:
                                                        module_markers.add(marker_name)
                                        # pytest.mark("xxx")
                                        elif isinstance(elt.func.value, ast.Name):
                                            if elt.func.value.id == "pytest" and elt.func.attr == "mark":
                                                if len(elt.args) > 0:
                                                    if isinstance(elt.args[0], ast.Constant):
                                                        marker_value = elt.args[0].value
                                                        if isinstance(marker_value, str):
                                                            module_markers.add(marker_value)
                                # Обрабатываем pytest.mark.xxx (без вызова)
                                elif isinstance(elt, ast.Attribute):
                                    if isinstance(elt.value, ast.Attribute):
                                        if isinstance(elt.value.value, ast.Name):
                                            if elt.value.value.id == "pytest" and elt.value.attr == "mark":
                                                marker_name = elt.attr
                                                if marker_name in VALID_MARKERS:
                                                    module_markers.add(marker_name)

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                test_info: TestInfo = {
                    "name": node.name,
                    "line": node.lineno,
                    "file": file_path,
                    "markers": set(module_markers),  # Начинаем с маркеров модуля
                    "fixtures": set(),
                    "args": [arg.arg for arg in node.args.args],
                }

                # Собираем маркеры из декораторов
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Call):
                        if isinstance(decorator.func, ast.Attribute):
                            if decorator.func.attr == "mark":
                                if isinstance(decorator.func.value, ast.Name):
                                    if decorator.func.value.id == "pytest":
                                        # @pytest.mark.xxx
                                        if len(decorator.args) > 0:
                                            if isinstance(decorator.args[0], ast.Constant):
                                                marker_value = decorator.args[0].value
                                                if isinstance(marker_value, str):
                                                    test_info["markers"].add(marker_value)
                    elif isinstance(decorator, ast.Attribute):
                        if decorator.attr in VALID_MARKERS:
                            test_info["markers"].add(decorator.attr)

                # Собираем фикстуры из аргументов
                for arg in test_info["args"]:
                    if arg not in NON_FIXTURE_ARGS:
                        test_info["fixtures"].add(arg)

                tests.append(test_info)

        return tests

    def check_test_markers(self) -> None:
        """Проверяет соответствие маркеров использованным фикстурам."""
        test_files = list(self.tests_dir.rglob("test_*.py"))
        test_files.extend(self.tests_dir.rglob("*_test.py"))

        for test_file in test_files:
            if "conftest" in test_file.name:
                continue

            tests = self.parse_test_file(test_file)

            for test in tests:
                # Проверяем соответствие фикстур и маркеров
                db_fixtures = {"cleanup_tables", "postgres_transaction"}
                celery_fixtures = {"celery_test_queues", "celery_worker_ready"}

                # Проверяем, что тесты с БД имеют маркер db
                if test["fixtures"].intersection(db_fixtures):
                    if "db" not in test["markers"]:
                        used_db_fixtures = test["fixtures"].intersection(db_fixtures)
                        self.warnings.append(
                            f"Тест '{test['name']}' в {test['file']}:{test['line']} "
                            f"использует фикстуру БД ({', '.join(used_db_fixtures)}), "
                            f"но не имеет маркера 'db'. Добавьте @pytest.mark.db"
                        )

                # Проверяем, что тесты с Celery имеют маркер celery
                if test["fixtures"].intersection(celery_fixtures):
                    if "celery" not in test["markers"]:
                        used_celery_fixtures = test["fixtures"].intersection(celery_fixtures)
                        self.warnings.append(
                            f"Тест '{test['name']}' в {test['file']}:{test['line']} "
                            f"использует фикстуру Celery ({', '.join(used_celery_fixtures)}), "
                            f"но не имеет маркера 'celery'. Добавьте @pytest.mark.celery"
                        )

                # Проверяем другие фикстуры (не БД и не Celery)
                for fixture in test["fixtures"]:
                    if fixture in FIXTURE_TO_MARKER and fixture not in db_fixtures and fixture not in celery_fixtures:
                        required_marker = FIXTURE_TO_MARKER[fixture]
                        if required_marker and required_marker not in test["markers"]:
                            self.warnings.append(
                                f"Тест '{test['name']}' в {test['file']}:{test['line']} "
                                f"использует фикстуру '{fixture}', но не имеет маркера '{required_marker}'. "
                                f"Добавьте @pytest.mark.{required_marker}"
                            )

                # Проверяем, что unit-тесты не используют БД/Redis/Celery
                if "unit" in test["markers"]:
                    if test["fixtures"].intersection(db_fixtures):
                        self.errors.append(
                            f"Unit-тест '{test['name']}' в {test['file']}:{test['line']} "
                            f"использует фикстуру БД. Unit-тесты не должны использовать реальную БД. "
                            f"Используйте моки или переименуйте тест в integration."
                        )
                    if test["fixtures"].intersection(celery_fixtures):
                        self.errors.append(
                            f"Unit-тест '{test['name']}' в {test['file']}:{test['line']} "
                            f"использует фикстуру Celery. Unit-тесты не должны использовать Celery. "
                            f"Используйте моки или переименуйте тест в e2e."
                        )

    def run_checks(self) -> int:
        """Запускает все проверки и возвращает код выхода."""
        print("Проверка качества тестов...")
        print(f"Директория тестов: {self.tests_dir}")
        print(f"Conftest: {self.conftest_path}")
        print()

        self.check_autouse_fixtures()
        self.check_test_markers()

        # Выводим результаты
        if self.errors:
            print("❌ ОШИБКИ:")
            for error in self.errors:
                print(f"  - {error}")
            print()

        if self.warnings:
            print("⚠️  ПРЕДУПРЕЖДЕНИЯ:")
            for warning in self.warnings:
                print(f"  - {warning}")
            print()

        if not self.errors and not self.warnings:
            print("✅ Все проверки пройдены!")
            return 0

        if self.errors:
            print(f"Найдено {len(self.errors)} ошибок и {len(self.warnings)} предупреждений.")
            return 1

        print(f"Найдено {len(self.warnings)} предупреждений.")
        return 0  # Предупреждения не блокируют, только ошибки


def main() -> int:
    """Главная функция."""
    project_root = Path(__file__).parent.parent
    tests_dir = project_root / "tests"
    conftest_path = tests_dir / "conftest.py"

    checker = TestQualityChecker(tests_dir, conftest_path)
    return checker.run_checks()


if __name__ == "__main__":
    sys.exit(main())
