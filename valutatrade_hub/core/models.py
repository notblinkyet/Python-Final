"""Доменные модели: пользователь, кошелёк и портфель."""

import hashlib
import secrets
from datetime import datetime

from valutatrade_hub.core.exceptions import (
    CurrencyNotFoundError,
    InsufficientFundsError,
)

MIN_PASSWORD_LENGTH = 4
SALT_BYTES = 8
DEFAULT_BASE_CURRENCY = "USD"
AMOUNT_ERROR = "'amount' должен быть положительным числом"

# Заглушка курсов (стоимость 1 единицы валюты в USD) на случай,
# если реальные курсы не переданы в Portfolio.get_total_value().
FALLBACK_USD_RATES = {
    "USD": 1.0,
    "EUR": 1.0786,
    "GBP": 1.2361,
    "RUB": 0.01016,
    "BTC": 59337.21,
    "ETH": 3720.0,
    "SOL": 145.12,
}


def hash_password(password: str, salt: str) -> str:
    """Односторонний хеш пароля: sha256(password + salt)."""
    return hashlib.sha256((password + salt).encode("utf-8")).hexdigest()


def validate_password(password) -> str:
    """Проверяет, что пароль — строка длиной не менее 4 символов."""
    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Пароль должен быть не короче {MIN_PASSWORD_LENGTH} символов")
    return password


class User:
    """Пользователь системы."""

    def __init__(
        self,
        user_id: int,
        username: str,
        hashed_password: str,
        salt: str,
        registration_date: datetime,
    ):
        self._user_id = user_id
        self.username = username
        self._hashed_password = hashed_password
        self._salt = salt
        self._registration_date = registration_date

    @classmethod
    def create(cls, user_id: int, username: str, password: str) -> "User":
        """Создаёт нового пользователя с солью и хешем пароля."""
        validate_password(password)
        salt = secrets.token_hex(SALT_BYTES)
        return cls(
            user_id,
            username,
            hash_password(password, salt),
            salt,
            datetime.now().replace(microsecond=0),
        )

    @property
    def user_id(self) -> int:
        """Уникальный идентификатор."""
        return self._user_id

    @property
    def username(self) -> str:
        """Имя пользователя."""
        return self._username

    @username.setter
    def username(self, value: str):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Имя пользователя не может быть пустым")
        self._username = value.strip()

    @property
    def hashed_password(self) -> str:
        """Хеш пароля."""
        return self._hashed_password

    @property
    def salt(self) -> str:
        """Соль пользователя."""
        return self._salt

    @property
    def registration_date(self) -> datetime:
        """Дата регистрации."""
        return self._registration_date

    def get_user_info(self) -> str:
        """Информация о пользователе без пароля."""
        return (
            f"ID: {self._user_id}, имя: {self._username}, "
            f"зарегистрирован: {self._registration_date.isoformat()}"
        )

    def change_password(self, new_password: str) -> None:
        """Меняет пароль: генерирует новую соль и хеширует пароль."""
        validate_password(new_password)
        self._salt = secrets.token_hex(SALT_BYTES)
        self._hashed_password = hash_password(new_password, self._salt)

    def verify_password(self, password: str) -> bool:
        """Проверяет пароль на совпадение с сохранённым хешем."""
        candidate = hash_password(password, self._salt)
        return secrets.compare_digest(candidate, self._hashed_password)

    def to_dict(self) -> dict:
        """Сериализация для users.json."""
        return {
            "user_id": self._user_id,
            "username": self._username,
            "hashed_password": self._hashed_password,
            "salt": self._salt,
            "registration_date": self._registration_date.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "User":
        """Восстанавливает пользователя из словаря users.json."""
        return cls(
            data["user_id"],
            data["username"],
            data["hashed_password"],
            data["salt"],
            datetime.fromisoformat(data["registration_date"]),
        )


class Wallet:
    """Кошелёк пользователя для одной валюты."""

    def __init__(self, currency_code: str, balance: float = 0.0):
        self.currency_code = currency_code
        self.balance = balance

    @property
    def balance(self) -> float:
        """Текущий баланс."""
        return self._balance

    @balance.setter
    def balance(self, value):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("Баланс должен быть числом")
        if value < 0:
            raise ValueError("Баланс не может быть отрицательным")
        self._balance = float(value)

    @staticmethod
    def _check_amount(amount) -> float:
        """Проверяет, что сумма операции — положительное число."""
        if (
            isinstance(amount, bool)
            or not isinstance(amount, (int, float))
            or amount <= 0
        ):
            raise ValueError(AMOUNT_ERROR)
        return float(amount)

    def deposit(self, amount: float) -> None:
        """Пополняет баланс."""
        self.balance = self._balance + self._check_amount(amount)

    def withdraw(self, amount: float) -> None:
        """Снимает средства, если баланса достаточно."""
        amount = self._check_amount(amount)
        if amount > self._balance:
            raise InsufficientFundsError(self._balance, amount, self.currency_code)
        self.balance = self._balance - amount

    def get_balance_info(self) -> str:
        """Строка с текущим балансом."""
        return f"{self.currency_code}: {self._balance:.4f}"

    def to_dict(self) -> dict:
        """Сериализация для portfolios.json."""
        return {"currency_code": self.currency_code, "balance": self._balance}


class Portfolio:
    """Все кошельки одного пользователя."""

    def __init__(self, user_id: int, wallets: dict | None = None, user=None):
        self._user_id = user_id
        self._wallets: dict[str, Wallet] = dict(wallets or {})
        self._user = user

    @property
    def user_id(self) -> int:
        """Идентификатор владельца."""
        return self._user_id

    @property
    def user(self):
        """Объект пользователя-владельца (только для чтения)."""
        return self._user

    @property
    def wallets(self) -> dict:
        """Копия словаря кошельков."""
        return dict(self._wallets)

    def add_currency(self, currency_code: str) -> Wallet:
        """Добавляет новый пустой кошелёк, если его ещё нет."""
        if currency_code in self._wallets:
            raise ValueError(f"Кошелёк '{currency_code}' уже существует")
        wallet = Wallet(currency_code)
        self._wallets[currency_code] = wallet
        return wallet

    def get_wallet(self, currency_code: str) -> Wallet | None:
        """Возвращает кошелёк по коду валюты или None."""
        return self._wallets.get(currency_code)

    def get_total_value(
        self, base_currency: str = DEFAULT_BASE_CURRENCY, exchange_rates=None
    ) -> float:
        """Общая стоимость кошельков в base_currency.

        exchange_rates — словарь {код: стоимость 1 единицы в USD}.
        """
        rates = exchange_rates or FALLBACK_USD_RATES
        if base_currency not in rates:
            raise CurrencyNotFoundError(base_currency)
        total_usd = 0.0
        for code, wallet in self._wallets.items():
            if code not in rates:
                raise CurrencyNotFoundError(code)
            total_usd += wallet.balance * rates[code]
        return total_usd / rates[base_currency]

    def to_dict(self) -> dict:
        """Сериализация для portfolios.json."""
        return {
            "user_id": self._user_id,
            "wallets": {code: w.to_dict() for code, w in self._wallets.items()},
        }

    @classmethod
    def from_dict(cls, data: dict, user=None) -> "Portfolio":
        """Восстанавливает портфель из словаря portfolios.json."""
        wallets = {
            code: Wallet(code, info.get("balance", 0.0))
            for code, info in data.get("wallets", {}).items()
        }
        return cls(data["user_id"], wallets, user)
