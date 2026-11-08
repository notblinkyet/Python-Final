"""Бизнес-логика: регистрация, вход, портфель, покупка/продажа, курсы."""

import time

from valutatrade_hub.core.currencies import get_currency, is_crypto
from valutatrade_hub.core.exceptions import (
    ApiRequestError,
    CurrencyNotFoundError,
    EmptyRatesCacheError,
    InvalidPasswordError,
    RateUnavailableError,
    UsernameTakenError,
    UserNotFoundError,
    WalletNotFoundError,
)
from valutatrade_hub.core.models import Portfolio, User
from valutatrade_hub.core.utils import (
    parse_iso,
    utc_now,
    validate_amount,
    validate_currency_code,
)
from valutatrade_hub.decorators import log_action
from valutatrade_hub.infra.database import DatabaseManager
from valutatrade_hub.infra.settings import SettingsLoader
from valutatrade_hub.parser_service.api_clients import make_pair
from valutatrade_hub.parser_service.updater import build_updater

USD = "USD"
FIRST_USER_ID = 1

_settings = SettingsLoader()
_db = DatabaseManager()
# Время последней попытки автообновления — чтобы не долбить API при каждом запросе.
_last_refresh_attempt = {"at": None}


# ---------- пользователи ----------


def _load_users() -> list[User]:
    return [User.from_dict(item) for item in _db.load_users()]


def _find_user(username: str) -> User | None:
    for user in _load_users():
        if user.username == username:
            return user
    return None


def _find_user_by_id(user_id: int) -> User | None:
    for user in _load_users():
        if user.user_id == user_id:
            return user
    return None


@log_action("REGISTER")
def register(username: str, password: str) -> dict:
    """Создаёт пользователя и пустой портфель."""
    if not isinstance(username, str) or not username.strip():
        raise ValueError("Имя пользователя не может быть пустым")
    username = username.strip()
    users = _db.load_users()
    if any(item["username"] == username for item in users):
        raise UsernameTakenError(username)

    user_id = max((item["user_id"] for item in users), default=FIRST_USER_ID - 1) + 1
    user = User.create(user_id, username, password)
    users.append(user.to_dict())
    _db.save_users(users)

    portfolios = _db.load_portfolios()
    portfolios.append(Portfolio(user_id).to_dict())
    _db.save_portfolios(portfolios)
    return {"user_id": user_id, "username": username}


@log_action("LOGIN")
def login(username: str, password: str) -> dict:
    """Проверяет логин и пароль, возвращает данные пользователя."""
    user = _find_user(username.strip() if isinstance(username, str) else username)
    if user is None:
        raise UserNotFoundError(username)
    if not user.verify_password(password):
        raise InvalidPasswordError()
    return {"user_id": user.user_id, "username": user.username}


# ---------- портфели ----------


def _load_portfolio(user_id: int) -> Portfolio:
    """Читает портфель пользователя (создаёт пустой, если его нет)."""
    user = _find_user_by_id(user_id)
    for item in _db.load_portfolios():
        if item["user_id"] == user_id:
            return Portfolio.from_dict(item, user)
    return Portfolio(user_id, user=user)


def _save_portfolio(portfolio: Portfolio) -> None:
    """Чтение → замена портфеля пользователя → запись."""
    portfolios = [
        item for item in _db.load_portfolios() if item["user_id"] != portfolio.user_id
    ]
    portfolios.append(portfolio.to_dict())
    portfolios.sort(key=lambda item: item["user_id"])
    _db.save_portfolios(portfolios)


# ---------- курсы ----------


def _rates_pairs() -> dict:
    return _db.load_rates().get("pairs", {})


def _is_fresh(info: dict) -> bool:
    ttl = _settings.get("rates_ttl_seconds")
    age = (utc_now() - parse_iso(info["updated_at"])).total_seconds()
    return age <= ttl


def _try_refresh() -> None:
    """Пытается обновить кеш курсов, не чаще одного раза за TTL."""
    now = time.monotonic()
    last = _last_refresh_attempt["at"]
    if last is not None and now - last < _settings.get("rates_ttl_seconds"):
        return
    _last_refresh_attempt["at"] = now
    try:
        build_updater().run_update()
    except ApiRequestError:
        pass


def _usd_rates(codes) -> tuple[dict, list[dict]]:
    """Стоимость 1 единицы каждой валюты в USD.

    Если в кеше нет нужных пар или они старше TTL — пробует обновить кеш.
    Возвращает (курсы, использованные записи кеша).
    """
    needed = [code for code in codes if code != USD]
    pairs = _rates_pairs()
    if any(
        make_pair(code, USD) not in pairs or not _is_fresh(pairs[make_pair(code, USD)])
        for code in needed
    ):
        _try_refresh()
        pairs = _rates_pairs()

    rates, used = {USD: 1.0}, []
    for code in needed:
        info = pairs.get(make_pair(code, USD))
        if info is None:
            continue
        rates[code] = info["rate"]
        used.append(info)
    return rates, used


def get_rate(from_code: str, to_code: str) -> dict:
    """Курс from→to с меткой времени и признаком устаревания."""
    from_code = validate_currency_code(from_code)
    to_code = validate_currency_code(to_code)
    if from_code == to_code:
        now = utc_now().isoformat()
        return {"rate": 1.0, "inverse": 1.0, "updated_at": now, "stale": False}

    rates, used = _usd_rates([from_code, to_code])
    if from_code not in rates or to_code not in rates:
        raise RateUnavailableError(from_code, to_code)
    rate = rates[from_code] / rates[to_code]
    oldest = min(used, key=lambda info: parse_iso(info["updated_at"]))
    return {
        "from": from_code,
        "to": to_code,
        "rate": rate,
        "inverse": 1 / rate,
        "updated_at": oldest["updated_at"],
        "stale": not all(_is_fresh(info) for info in used),
    }


def _rate_to_usd(code: str) -> dict:
    """Курс code→USD для оценки сделки."""
    try:
        return get_rate(code, USD)
    except RateUnavailableError:
        raise RateUnavailableError(
            code, USD, f"Не удалось получить курс для {code}→{USD}"
        ) from None


# ---------- сделки ----------


@log_action("BUY", verbose=True)
def buy(user_id: int, currency_code: str, amount) -> dict:
    """Покупка валюты: кошелёк создаётся автоматически, баланс растёт на amount."""
    code = validate_currency_code(currency_code)
    amount = validate_amount(amount)
    rate_info = _rate_to_usd(code)

    portfolio = _load_portfolio(user_id)
    wallet = portfolio.get_wallet(code) or portfolio.add_currency(code)
    before = wallet.balance
    wallet.deposit(amount)
    _save_portfolio(portfolio)
    return {
        "username": portfolio.user.username if portfolio.user else None,
        "currency_code": code,
        "amount": amount,
        "rate": rate_info["rate"],
        "base": USD,
        "before": before,
        "after": wallet.balance,
        "value": amount * rate_info["rate"],
        "stale": rate_info["stale"],
    }


@log_action("SELL", verbose=True)
def sell(user_id: int, currency_code: str, amount) -> dict:
    """Продажа валюты: списание с кошелька, выручка зачисляется на USD-кошелёк."""
    code = validate_currency_code(currency_code)
    amount = validate_amount(amount)

    portfolio = _load_portfolio(user_id)
    wallet = portfolio.get_wallet(code)
    if wallet is None:
        raise WalletNotFoundError(code)
    rate_info = _rate_to_usd(code)

    before = wallet.balance
    wallet.withdraw(amount)
    proceeds = amount * rate_info["rate"]
    if code != USD:
        usd_wallet = portfolio.get_wallet(USD) or portfolio.add_currency(USD)
        usd_wallet.deposit(proceeds)
    _save_portfolio(portfolio)
    return {
        "username": portfolio.user.username if portfolio.user else None,
        "currency_code": code,
        "amount": amount,
        "rate": rate_info["rate"],
        "base": USD,
        "before": before,
        "after": wallet.balance,
        "value": proceeds,
        "stale": rate_info["stale"],
    }


def show_portfolio(user_id: int, base: str | None = None) -> dict:
    """Кошельки пользователя и их стоимость в базовой валюте."""
    base = (base or _settings.get("default_base_currency")).strip().upper()
    get_currency(base)

    portfolio = _load_portfolio(user_id)
    wallets = portfolio.wallets
    username = portfolio.user.username if portfolio.user else str(user_id)
    if not wallets:
        return {"username": username, "base": base, "rows": [], "total": 0.0}

    rates, used = _usd_rates(list(wallets) + [base])
    missing = [code for code in list(wallets) + [base] if code not in rates]
    if missing:
        raise RateUnavailableError(missing[0], base)

    rows = [
        (code, wallet.balance, wallet.balance * rates[code] / rates[base])
        for code, wallet in wallets.items()
    ]
    return {
        "username": username,
        "base": base,
        "rows": rows,
        "total": portfolio.get_total_value(base, rates),
        "stale": not all(_is_fresh(info) for info in used),
    }


# ---------- Parser Service ----------


def update_rates(source: str | None = None) -> dict:
    """Немедленное обновление курсов из всех (или одного) источников."""
    result = build_updater().run_update(source)
    _last_refresh_attempt["at"] = time.monotonic()
    return result


def show_rates(currency: str | None = None, top=None, base: str | None = None):
    """Курсы из локального кеша с фильтрами --currency / --top / --base."""
    snapshot = _db.load_rates()
    pairs = snapshot.get("pairs", {})
    if not pairs:
        raise EmptyRatesCacheError()

    usd_values = {USD: 1.0}
    for pair, info in pairs.items():
        code, quote = pair.split("_", 1)
        if quote == USD:
            usd_values[code] = info["rate"]

    base = (base or USD).strip().upper()
    if base not in usd_values:
        raise CurrencyNotFoundError(base)
    rows = [
        (make_pair(code, base), value / usd_values[base])
        for code, value in usd_values.items()
        if code != base
    ]

    if currency:
        code = currency.strip().upper()
        rows = [row for row in rows if row[0].startswith(f"{code}_")]
        if not rows:
            raise RateUnavailableError(
                code, base, f"Курс для '{code}' не найден в кеше."
            )
    if top is not None:
        try:
            top = int(top)
        except (TypeError, ValueError):
            raise ValueError("'top' должен быть положительным целым числом") from None
        if top <= 0:
            raise ValueError("'top' должен быть положительным целым числом")
        rows = [row for row in rows if is_crypto(row[0].split("_")[0])]
        rows = sorted(rows, key=lambda row: row[1], reverse=True)[:top]
    else:
        rows.sort()
    return {"last_refresh": snapshot.get("last_refresh"), "rows": rows}
