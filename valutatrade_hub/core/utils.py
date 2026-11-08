"""Вспомогательные функции: валидация, форматирование, работа со временем."""

from datetime import datetime, timezone

from valutatrade_hub.core.currencies import get_currency, is_crypto

FIAT_DECIMALS = 2
CRYPTO_DECIMALS = 4
RATE_BIG_DECIMALS = 2
RATE_MEDIUM_DECIMALS = 4
RATE_SMALL_DECIMALS = 8
RATE_BIG_THRESHOLD = 100
ISO_UTC_SUFFIX = "Z"
DISPLAY_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def validate_currency_code(code) -> str:
    """Проверяет код валюты (непустой, известный) и приводит к верхнему регистру."""
    if not isinstance(code, str) or not code.strip():
        raise ValueError("Код валюты не может быть пустым")
    return get_currency(code).code


def validate_amount(amount) -> float:
    """Проверяет, что amount — положительное число, и возвращает float."""
    try:
        value = float(amount)
    except (TypeError, ValueError):
        raise ValueError("'amount' должен быть положительным числом") from None
    if isinstance(amount, bool) or value <= 0 or value != value:
        raise ValueError("'amount' должен быть положительным числом")
    return value


def format_amount(value: float, code: str) -> str:
    """Баланс: 4 знака для криптовалют, 2 — для фиата."""
    decimals = CRYPTO_DECIMALS if is_crypto(code) else FIAT_DECIMALS
    return f"{value:.{decimals}f}"


def format_money(value: float) -> str:
    """Денежная сумма с разделителями тысяч: 2,965.00."""
    return f"{value:,.{FIAT_DECIMALS}f}"


def format_rate(rate: float) -> str:
    """Курс: 2 знака для ≥ 100, 4 — для ≥ 1, до 8 знаков для маленьких."""
    if rate >= RATE_BIG_THRESHOLD:
        return f"{rate:.{RATE_BIG_DECIMALS}f}"
    if rate >= 1:
        return f"{rate:.{RATE_MEDIUM_DECIMALS}f}"
    text = f"{rate:.{RATE_SMALL_DECIMALS}f}".rstrip("0")
    return text if not text.endswith(".") else text + "0"


def utc_now() -> datetime:
    """Текущее время в UTC без микросекунд."""
    return datetime.now(timezone.utc).replace(microsecond=0)


def to_iso_utc(moment: datetime) -> str:
    """datetime → '2025-10-10T12:00:00Z'."""
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z"


def parse_iso(value: str) -> datetime:
    """Разбирает ISO-строку (с 'Z' или без зоны) в aware datetime UTC."""
    text = value.strip()
    if text.endswith(ISO_UTC_SUFFIX):
        text = text[:-1] + "+00:00"
    moment = datetime.fromisoformat(text)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment


def format_timestamp(value: str) -> str:
    """ISO-строка → '2025-10-09 00:03:22' для вывода пользователю."""
    return parse_iso(value).strftime(DISPLAY_TIME_FORMAT)
