"""SettingsLoader — единая точка конфигурации (Singleton)."""

import tomllib
from pathlib import Path
from typing import Any

PYPROJECT_FILE = "pyproject.toml"
CONFIG_SECTION = ("tool", "valutatrade")

DEFAULT_SETTINGS = {
    "data_dir": "data",
    "users_file": "users.json",
    "portfolios_file": "portfolios.json",
    "rates_file": "rates.json",
    "history_file": "exchange_rates.json",
    "rates_ttl_seconds": 300,
    "default_base_currency": "USD",
    "log_dir": "logs",
    "log_level": "INFO",
    "log_format": "%(levelname)s %(asctime)s %(message)s",
    "log_datefmt": "%Y-%m-%dT%H:%M:%S",
    "log_max_bytes": 1_048_576,
    "log_backup_count": 3,
}

_MISSING = object()


class SettingsLoader:
    """Загружает и кеширует настройки из [tool.valutatrade] в pyproject.toml.

    Singleton реализован через __new__: это самый простой и читаемый
    способ — без метаклассов, а повторные вызовы SettingsLoader()
    (в том числе при импортах из разных модулей) возвращают тот же объект.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            instance = super().__new__(cls)
            instance._settings = {}
            instance.reload()
            cls._instance = instance
        return cls._instance

    def reload(self) -> None:
        """Перечитывает конфигурацию (значения по умолчанию + pyproject.toml)."""
        settings = dict(DEFAULT_SETTINGS)
        path = Path.cwd() / PYPROJECT_FILE
        if path.exists():
            with path.open("rb") as file:
                section = tomllib.load(file)
            for key in CONFIG_SECTION:
                section = section.get(key, {})
            settings.update(section)
        self._settings = settings

    def get(self, key: str, default: Any = _MISSING) -> Any:
        """Возвращает значение настройки; KeyError, если ключа нет и нет default."""
        if key in self._settings:
            return self._settings[key]
        if default is _MISSING:
            raise KeyError(key)
        return default

    def data_path(self, file_key: str) -> Path:
        """Путь к файлу данных: <data_dir>/<значение file_key>."""
        return Path(self.get("data_dir")) / self.get(file_key)
