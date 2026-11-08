"""Настройка логирования: формат, уровень и ротация файлов."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from valutatrade_hub.infra.settings import SettingsLoader

ACTIONS_LOGGER = "valutatrade.actions"
PARSER_LOGGER = "valutatrade.parser"
ACTIONS_LOG_FILE = "actions.log"
PARSER_LOG_FILE = "parser.log"
CONSOLE_FORMAT = "%(levelname)s: %(message)s"
FILE_ENCODING = "utf-8"


def _file_handler(filename: str) -> RotatingFileHandler:
    """Файловый обработчик с ротацией по размеру."""
    settings = SettingsLoader()
    log_dir = Path(settings.get("log_dir"))
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        log_dir / filename,
        maxBytes=settings.get("log_max_bytes"),
        backupCount=settings.get("log_backup_count"),
        encoding=FILE_ENCODING,
    )
    handler.setFormatter(
        logging.Formatter(settings.get("log_format"), settings.get("log_datefmt"))
    )
    return handler


def setup_logging() -> None:
    """Настраивает логгеры действий и парсера (повторный вызов безопасен).

    Формат — человекочитаемая строка:
    INFO 2025-10-09T12:05:22 BUY user='alice' currency='BTC' amount=0.0500 ...
    Файлы: logs/actions.log и logs/parser.log, ротация по размеру.
    """
    level = SettingsLoader().get("log_level")

    actions = logging.getLogger(ACTIONS_LOGGER)
    if not actions.handlers:
        actions.setLevel(level)
        actions.addHandler(_file_handler(ACTIONS_LOG_FILE))
        actions.propagate = False

    parser = logging.getLogger(PARSER_LOGGER)
    if not parser.handlers:
        parser.setLevel(level)
        parser.addHandler(_file_handler(PARSER_LOG_FILE))
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter(CONSOLE_FORMAT))
        parser.addHandler(console)
        parser.propagate = False
