"""DatabaseManager — абстракция над JSON-хранилищем (Singleton)."""

import json
import os
import tempfile
from pathlib import Path

from valutatrade_hub.infra.settings import SettingsLoader

FILE_ENCODING = "utf-8"
JSON_INDENT = 4


def read_json(path: Path, default):
    """Читает JSON-файл; если его нет или он пуст — возвращает default."""
    try:
        with open(path, encoding=FILE_ENCODING) as file:
            content = file.read()
    except FileNotFoundError:
        return default
    return json.loads(content) if content.strip() else default


def write_json_atomic(path: Path, data) -> None:
    """Атомарная запись: временный файл в той же папке → os.replace."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding=FILE_ENCODING) as file:
            json.dump(data, file, ensure_ascii=False, indent=JSON_INDENT)
        os.replace(tmp_name, path)
    except BaseException:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)
        raise


class DatabaseManager:
    """Единая точка доступа к users.json, portfolios.json и rates.json."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            instance = super().__new__(cls)
            instance._settings = SettingsLoader()
            cls._instance = instance
        return cls._instance

    def _path(self, file_key: str) -> Path:
        return self._settings.data_path(file_key)

    def load_users(self) -> list:
        """Список пользователей."""
        return read_json(self._path("users_file"), [])

    def save_users(self, users: list) -> None:
        """Сохраняет список пользователей."""
        write_json_atomic(self._path("users_file"), users)

    def load_portfolios(self) -> list:
        """Список портфелей."""
        return read_json(self._path("portfolios_file"), [])

    def save_portfolios(self, portfolios: list) -> None:
        """Сохраняет список портфелей."""
        write_json_atomic(self._path("portfolios_file"), portfolios)

    def load_rates(self) -> dict:
        """Снимок текущих курсов (rates.json)."""
        return read_json(self._path("rates_file"), {})

    def save_rates(self, rates: dict) -> None:
        """Сохраняет снимок курсов."""
        write_json_atomic(self._path("rates_file"), rates)
