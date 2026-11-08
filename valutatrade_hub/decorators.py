"""Декоратор @log_action для логирования доменных операций."""

import functools
import inspect
import logging

from valutatrade_hub.logging_config import ACTIONS_LOGGER

RESULT_OK = "OK"
RESULT_ERROR = "ERROR"
AMOUNT_DECIMALS = 4
RATE_DECIMALS = 2
RAW_KEYS = ("result", "error_type")


def _format_fields(fields: dict) -> str:
    """Собирает строку key=value, строки — в кавычках, суммы — 4 знака, курс — 2."""
    parts = []
    for key, value in fields.items():
        if value is None:
            continue
        if isinstance(value, float):
            decimals = RATE_DECIMALS if key == "rate" else AMOUNT_DECIMALS
            parts.append(f"{key}={value:.{decimals}f}")
        elif key in RAW_KEYS:
            parts.append(f"{key}={value}")
        elif isinstance(value, str):
            parts.append(f"{key}='{value}'")
        else:
            parts.append(f"{key}={value}")
    return " ".join(parts)


def log_action(action: str, verbose: bool = False):
    """Логирует операцию (BUY/SELL/REGISTER/LOGIN) на уровне INFO.

    Исключения не глотаются: фиксируются в логе и пробрасываются дальше.
    verbose=True добавляет состояние кошелька «было → стало».
    """

    def decorator(func):
        signature = inspect.signature(func)

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            logger = logging.getLogger(ACTIONS_LOGGER)
            arguments = signature.bind_partial(*args, **kwargs).arguments
            fields = {
                "user": arguments.get("username"),
                "user_id": arguments.get("user_id"),
                "currency": arguments.get("currency_code"),
                "amount": arguments.get("amount"),
            }
            try:
                result = func(*args, **kwargs)
            except Exception as error:
                fields.update(
                    result=RESULT_ERROR,
                    error_type=type(error).__name__,
                    error_message=str(error),
                )
                logger.info("%s %s", action, _format_fields(fields))
                raise

            if isinstance(result, dict):
                fields["user"] = result.get("username", fields["user"])
                fields["currency"] = result.get("currency_code", fields["currency"])
                fields["amount"] = result.get("amount", fields["amount"])
                fields["rate"] = result.get("rate")
                fields["base"] = result.get("base")
                if verbose and "before" in result:
                    fields["before"] = result["before"]
                    fields["after"] = result["after"]
            fields["result"] = RESULT_OK
            logger.info("%s %s", action, _format_fields(fields))
            return result

        return wrapper

    return decorator
