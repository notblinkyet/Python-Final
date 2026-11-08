"""Клиенты внешних API курсов: CoinGecko (крипто) и ExchangeRate-API (фиат)."""

import time
from abc import ABC, abstractmethod

import requests

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.parser_service.config import API_KEY_ENV, ParserConfig

HTTP_OK = 200
MS_IN_SECOND = 1000
PAIR_SEPARATOR = "_"
HTTP_ERROR_REASONS = {
    401: "неверный или отсутствующий API-ключ (401)",
    403: "доступ запрещён, проверьте API-ключ (403)",
    404: "ресурс не найден (404)",
    429: "превышен лимит запросов (429 Too Many Requests)",
}


def make_pair(from_code: str, to_code: str) -> str:
    """'BTC', 'USD' → 'BTC_USD'."""
    return f"{from_code}{PAIR_SEPARATOR}{to_code}"


class BaseApiClient(ABC):
    """Единый интерфейс получения курсов: fetch_rates() -> {'BTC_USD': 59337.21}."""

    source_name: str = ""
    source_key: str = ""

    def __init__(self, config: ParserConfig | None = None):
        self.config = config or ParserConfig()
        self.last_meta: dict = {}

    def _get_json(self, url: str, params: dict | None = None) -> dict:
        """GET-запрос с таймаутом, проверкой status_code и разбором JSON."""
        started = time.monotonic()
        try:
            response = requests.get(
                url, params=params, timeout=self.config.REQUEST_TIMEOUT
            )
        except requests.exceptions.Timeout:
            raise ApiRequestError("превышен таймаут запроса") from None
        except requests.exceptions.RequestException as error:
            raise ApiRequestError(f"Network error ({type(error).__name__})") from None

        self.last_meta = {
            "request_ms": round((time.monotonic() - started) * MS_IN_SECOND),
            "status_code": response.status_code,
            "etag": response.headers.get("ETag"),
        }
        if response.status_code != HTTP_OK:
            reason = HTTP_ERROR_REASONS.get(
                response.status_code, f"HTTP {response.status_code}"
            )
            raise ApiRequestError(reason)
        try:
            return response.json()
        except ValueError:
            raise ApiRequestError("ответ не JSON") from None

    @abstractmethod
    def fetch_rates(self) -> dict[str, float]:
        """Возвращает курсы в формате {'<FROM>_<TO>': rate}."""


class CoinGeckoClient(BaseApiClient):
    """Курсы криптовалют к базовой валюте через CoinGecko."""

    source_name = "CoinGecko"
    source_key = "coingecko"

    def fetch_rates(self) -> dict[str, float]:
        config = self.config
        base = config.BASE_CURRENCY
        id_map = {code: config.CRYPTO_ID_MAP[code] for code in config.CRYPTO_CURRENCIES}
        data = self._get_json(
            config.COINGECKO_URL,
            {"ids": ",".join(id_map.values()), "vs_currencies": base.lower()},
        )
        rates = {}
        for code, coin_id in id_map.items():
            value = data.get(coin_id, {}).get(base.lower())
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                rates[make_pair(code, base)] = float(value)
        if not rates:
            raise ApiRequestError("в ответе нет курсов")
        self.last_meta["raw_ids"] = id_map
        return rates


class ExchangeRateApiClient(BaseApiClient):
    """Курсы фиатных валют через ExchangeRate-API (нужен API-ключ)."""

    source_name = "ExchangeRate-API"
    source_key = "exchangerate"

    def fetch_rates(self) -> dict[str, float]:
        config = self.config
        if not config.EXCHANGERATE_API_KEY:
            raise ApiRequestError(f"не задан API-ключ (переменная {API_KEY_ENV})")
        base = config.BASE_CURRENCY
        url = (
            f"{config.EXCHANGERATE_API_URL}/{config.EXCHANGERATE_API_KEY}/latest/{base}"
        )
        data = self._get_json(url)
        if data.get("result") != "success":
            raise ApiRequestError(data.get("error-type", "неизвестная ошибка"))
        # API отдаёт «сколько единиц валюты за 1 USD» (USD→EUR = 0.927),
        # а в кеше храним стоимость 1 единицы валюты в USD (EUR→USD).
        source_rates = data.get("rates", {})
        rates = {}
        for code in config.FIAT_CURRENCIES:
            value = source_rates.get(code)
            if isinstance(value, (int, float)) and value > 0:
                rates[make_pair(code, base)] = 1 / float(value)
        if not rates:
            raise ApiRequestError("в ответе нет курсов")
        return rates
