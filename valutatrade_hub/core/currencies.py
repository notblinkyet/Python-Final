"""Иерархия валют и реестр поддерживаемых валют."""

from abc import ABC, abstractmethod

from valutatrade_hub.core.exceptions import CurrencyNotFoundError

MIN_CODE_LENGTH = 2
MAX_CODE_LENGTH = 5
MCAP_FORMAT = ".2e"


class Currency(ABC):
    """Абстрактная валюта: человекочитаемое имя и код (тикер)."""

    def __init__(self, name: str, code: str):
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Название валюты не может быть пустым")
        if (
            not isinstance(code, str)
            or not MIN_CODE_LENGTH <= len(code) <= MAX_CODE_LENGTH
            or code != code.upper()
            or " " in code
        ):
            raise ValueError(f"Некорректный код валюты '{code}'")
        self.name = name.strip()
        self.code = code

    @abstractmethod
    def get_display_info(self) -> str:
        """Возвращает строку с описанием валюты для UI и логов."""


class FiatCurrency(Currency):
    """Фиатная валюта с указанием страны или зоны эмиссии."""

    def __init__(self, name: str, code: str, issuing_country: str):
        super().__init__(name, code)
        self.issuing_country = issuing_country

    def get_display_info(self) -> str:
        """'[FIAT] USD — US Dollar (Issuing: United States)'."""
        return f"[FIAT] {self.code} — {self.name} (Issuing: {self.issuing_country})"


class CryptoCurrency(Currency):
    """Криптовалюта с алгоритмом и рыночной капитализацией."""

    def __init__(self, name: str, code: str, algorithm: str, market_cap: float):
        super().__init__(name, code)
        self.algorithm = algorithm
        self.market_cap = market_cap

    def get_display_info(self) -> str:
        """'[CRYPTO] BTC — Bitcoin (Algo: SHA-256, MCAP: 1.12e+12)'."""
        return (
            f"[CRYPTO] {self.code} — {self.name} "
            f"(Algo: {self.algorithm}, MCAP: {self.market_cap:{MCAP_FORMAT}})"
        )


_CURRENCY_REGISTRY: dict[str, Currency] = {
    currency.code: currency
    for currency in (
        FiatCurrency("US Dollar", "USD", "United States"),
        FiatCurrency("Euro", "EUR", "Eurozone"),
        FiatCurrency("British Pound", "GBP", "United Kingdom"),
        FiatCurrency("Russian Ruble", "RUB", "Russia"),
        CryptoCurrency("Bitcoin", "BTC", "SHA-256", 1.12e12),
        CryptoCurrency("Ethereum", "ETH", "Ethash", 4.5e11),
        CryptoCurrency("Solana", "SOL", "Proof of History", 6.8e10),
    )
}


def get_currency(code: str) -> Currency:
    """Возвращает валюту по коду или бросает CurrencyNotFoundError."""
    normalized = code.strip().upper() if isinstance(code, str) else code
    try:
        return _CURRENCY_REGISTRY[normalized]
    except (KeyError, TypeError):
        raise CurrencyNotFoundError(code) from None


def get_supported_codes() -> list[str]:
    """Возвращает отсортированный список поддерживаемых кодов."""
    return sorted(_CURRENCY_REGISTRY)


def is_crypto(code: str) -> bool:
    """Проверяет, является ли валюта криптовалютой."""
    return isinstance(_CURRENCY_REGISTRY.get(code), CryptoCurrency)
