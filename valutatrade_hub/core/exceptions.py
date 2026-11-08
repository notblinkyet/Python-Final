"""Пользовательские исключения ValutaTrade Hub."""


class ValutaTradeError(Exception):
    """Базовое исключение приложения."""


class InsufficientFundsError(ValutaTradeError):
    """Недостаточно средств на кошельке."""

    def __init__(self, available, required, code):
        self.available = available
        self.required = required
        self.code = code
        super().__init__(
            f"Недостаточно средств: доступно {available:.4f} {code}, "
            f"требуется {required:.4f} {code}"
        )


class CurrencyNotFoundError(ValutaTradeError):
    """Неизвестный код валюты."""

    def __init__(self, code):
        self.code = code
        super().__init__(f"Неизвестная валюта '{code}'")


class ApiRequestError(ValutaTradeError):
    """Сбой при обращении к внешнему API."""

    def __init__(self, reason):
        self.reason = reason
        super().__init__(f"Ошибка при обращении к внешнему API: {reason}")


class RateUnavailableError(ValutaTradeError):
    """Курс для пары валют получить не удалось."""

    def __init__(self, from_code, to_code, message=None):
        self.from_code = from_code
        self.to_code = to_code
        super().__init__(
            message
            or f"Курс {from_code}→{to_code} недоступен. Повторите попытку позже."
        )


class UsernameTakenError(ValutaTradeError):
    """Имя пользователя уже занято."""

    def __init__(self, username):
        super().__init__(f"Имя пользователя '{username}' уже занято")


class UserNotFoundError(ValutaTradeError):
    """Пользователь не найден."""

    def __init__(self, username):
        super().__init__(f"Пользователь '{username}' не найден")


class InvalidPasswordError(ValutaTradeError):
    """Неверный пароль."""

    def __init__(self):
        super().__init__("Неверный пароль")


class WalletNotFoundError(ValutaTradeError):
    """У пользователя нет кошелька в указанной валюте."""

    def __init__(self, code):
        self.code = code
        super().__init__(
            f"У вас нет кошелька '{code}'. Добавьте валюту: "
            "она создаётся автоматически при первой покупке."
        )


class EmptyRatesCacheError(ValutaTradeError):
    """Локальный кеш курсов пуст."""

    def __init__(self):
        super().__init__(
            "Локальный кеш курсов пуст. "
            "Выполните 'update-rates', чтобы загрузить данные."
        )
