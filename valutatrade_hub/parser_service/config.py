"""Конфигурация Parser Service: API, списки валют, пути и таймауты."""

import os
from dataclasses import dataclass, field

from valutatrade_hub.infra.settings import SettingsLoader

API_KEY_ENV = "EXCHANGERATE_API_KEY"


def _rates_path() -> str:
    return str(SettingsLoader().data_path("rates_file"))


def _history_path() -> str:
    return str(SettingsLoader().data_path("history_file"))


@dataclass(frozen=True)
class ParserConfig:
    """Все изменяемые параметры парсера в одном месте.

    API-ключ ExchangeRate-API не хранится в коде: он читается
    из переменной окружения EXCHANGERATE_API_KEY.
    """

    EXCHANGERATE_API_KEY: str | None = field(
        default_factory=lambda: os.getenv(API_KEY_ENV)
    )

    COINGECKO_URL: str = "https://api.coingecko.com/api/v3/simple/price"
    EXCHANGERATE_API_URL: str = "https://v6.exchangerate-api.com/v6"

    BASE_CURRENCY: str = "USD"
    FIAT_CURRENCIES: tuple = ("EUR", "GBP", "RUB")
    CRYPTO_CURRENCIES: tuple = ("BTC", "ETH", "SOL")
    CRYPTO_ID_MAP: dict = field(
        default_factory=lambda: {
            "BTC": "bitcoin",
            "ETH": "ethereum",
            "SOL": "solana",
        }
    )

    RATES_FILE_PATH: str = field(default_factory=_rates_path)
    HISTORY_FILE_PATH: str = field(default_factory=_history_path)

    REQUEST_TIMEOUT: int = 10
    UPDATE_INTERVAL_SECONDS: int = 300
