import shlex

from prettytable import PrettyTable

from valutatrade_hub.core import usecases
from valutatrade_hub.core.currencies import get_supported_codes
from valutatrade_hub.core.exceptions import (
    ApiRequestError,
    CurrencyNotFoundError,
    InsufficientFundsError,
    ValutaTradeError,
)
from valutatrade_hub.core.utils import (
    format_amount,
    format_money,
    format_rate,
    format_timestamp,
)
from valutatrade_hub.logging_config import setup_logging
from valutatrade_hub.parser_service.config import ParserConfig
from valutatrade_hub.parser_service.scheduler import RatesScheduler
from valutatrade_hub.parser_service.updater import build_updater

PROMPT = "> "
FLAG_PREFIX = "--"
SEPARATOR_LINE = "-" * 33
EXIT_COMMANDS = ("exit", "quit")
NOT_LOGGED_IN = "Сначала выполните login"

COMMANDS = [
    ("register --username <str> --password <str>", "регистрация"),
    ("login --username <str> --password <str>", "вход в систему"),
    ("logout", "выход из аккаунта"),
    ("show-portfolio [--base <str>]", "портфель и итоговая стоимость"),
    ("buy --currency <str> --amount <float>", "купить валюту"),
    ("sell --currency <str> --amount <float>", "продать валюту"),
    ("get-rate --from <str> --to <str>", "курс одной валюты к другой"),
    ("update-rates [--source coingecko|exchangerate]", "обновить курсы"),
    ("show-rates [--currency <str>] [--top <int>] [--base <str>]", "курсы из кеша"),
    ("schedule-updates [--interval <сек>] [--runs <int>]", "периодическое обновление"),
    ("help", "справка"),
    ("exit", "выход из программы"),
]

session = {"user_id": None, "username": None}


class CliUsageError(ValueError):
    """Ошибка в аргументах команды."""


def parse_flags(tokens: list[str], required=(), optional=()) -> dict:
    """Разбирает '--key value' в словарь и проверяет набор аргументов."""
    flags, index = {}, 0
    allowed = set(required) | set(optional)
    while index < len(tokens):
        token = tokens[index]
        if not token.startswith(FLAG_PREFIX):
            raise CliUsageError(f"Неожиданный аргумент '{token}'")
        name = token[len(FLAG_PREFIX) :]
        if name not in allowed:
            raise CliUsageError(f"Неизвестный аргумент '{token}'")
        if index + 1 >= len(tokens):
            raise CliUsageError(f"Не указано значение для '{token}'")
        flags[name] = tokens[index + 1]
        index += 2
    missing = [f"{FLAG_PREFIX}{name}" for name in required if name not in flags]
    if missing:
        raise CliUsageError(f"Не указаны обязательные аргументы: {', '.join(missing)}")
    return flags


def require_login() -> int:
    """Возвращает user_id текущей сессии или сообщает о необходимости входа."""
    if session["user_id"] is None:
        raise CliUsageError(NOT_LOGGED_IN)
    return session["user_id"]


def print_stale_warning(stale: bool) -> None:
    """Предупреждает, что использованы устаревшие курсы."""
    if stale:
        print(
            "Внимание: курсы в кеше устарели, а обновить их не удалось. "
            "Выполните 'update-rates'."
        )


# ---------- команды ----------


def cmd_register(tokens):
    """register --username <str> --password <str>."""
    flags = parse_flags(tokens, required=("username", "password"))
    result = usecases.register(flags["username"], flags["password"])
    print(
        f"Пользователь '{result['username']}' зарегистрирован "
        f"(id={result['user_id']}). "
        f"Войдите: login --username {result['username']} --password ****"
    )


def cmd_login(tokens):
    """login --username <str> --password <str>."""
    flags = parse_flags(tokens, required=("username", "password"))
    result = usecases.login(flags["username"], flags["password"])
    session.update(user_id=result["user_id"], username=result["username"])
    print(f"Вы вошли как '{result['username']}'")


def cmd_logout(tokens):
    """logout."""
    parse_flags(tokens)
    require_login()
    print(f"Вы вышли из аккаунта '{session['username']}'")
    session.update(user_id=None, username=None)


def cmd_show_portfolio(tokens):
    """show-portfolio [--base <str>]."""
    flags = parse_flags(tokens, optional=("base",))
    user_id = require_login()
    try:
        result = usecases.show_portfolio(user_id, flags.get("base"))
    except CurrencyNotFoundError as error:
        print(f"Неизвестная базовая валюта '{error.code}'")
        return
    base = result["base"]
    if not result["rows"]:
        print(f"Портфель пользователя '{result['username']}' пуст.")
        return
    print(f"Портфель пользователя '{result['username']}' (база: {base}):")
    for code, balance, value in result["rows"]:
        print(
            f"- {code}: {format_amount(balance, code)}  → {format_money(value)} {base}"
        )
    print(SEPARATOR_LINE)
    print(f"ИТОГО: {format_money(result['total'])} {base}")
    print_stale_warning(result.get("stale", False))


def _print_trade(result: dict, title: str, value_label: str):
    code = result["currency_code"]
    print(
        f"{title}: {format_amount(result['amount'], code)} {code} "
        f"по курсу {format_rate(result['rate'])} {result['base']}/{code}"
    )
    print("Изменения в портфеле:")
    print(
        f"- {code}: было {format_amount(result['before'], code)} "
        f"→ стало {format_amount(result['after'], code)}"
    )
    print(f"{value_label}: {format_money(result['value'])} {result['base']}")
    print_stale_warning(result["stale"])


def cmd_buy(tokens):
    """buy --currency <str> --amount <float>."""
    flags = parse_flags(tokens, required=("currency", "amount"))
    user_id = require_login()
    result = usecases.buy(user_id, flags["currency"], flags["amount"])
    _print_trade(result, "Покупка выполнена", "Оценочная стоимость покупки")


def cmd_sell(tokens):
    """sell --currency <str> --amount <float>."""
    flags = parse_flags(tokens, required=("currency", "amount"))
    user_id = require_login()
    result = usecases.sell(user_id, flags["currency"], flags["amount"])
    _print_trade(result, "Продажа выполнена", "Оценочная выручка")


def cmd_get_rate(tokens):
    """get-rate --from <str> --to <str>."""
    flags = parse_flags(tokens, required=("from", "to"))
    result = usecases.get_rate(flags["from"], flags["to"])
    from_code, to_code = flags["from"].upper(), flags["to"].upper()
    print(
        f"Курс {from_code}→{to_code}: {format_rate(result['rate'])} "
        f"(обновлено: {format_timestamp(result['updated_at'])})"
    )
    print(f"Обратный курс {to_code}→{from_code}: {format_rate(result['inverse'])}")
    print_stale_warning(result["stale"])


def cmd_update_rates(tokens):
    """update-rates [--source coingecko|exchangerate]."""
    flags = parse_flags(tokens, optional=("source",))
    result = usecases.update_rates(flags.get("source"))
    if result["errors"]:
        print("Update completed with errors. Check logs/parser.log for details.")
    else:
        print(
            f"Update successful. Total rates updated: {result['updated']}. "
            f"Last refresh: {result['last_refresh']}"
        )


def cmd_show_rates(tokens):
    """show-rates [--currency <str>] [--top <int>] [--base <str>]."""
    flags = parse_flags(tokens, optional=("currency", "top", "base"))
    result = usecases.show_rates(
        flags.get("currency"), flags.get("top"), flags.get("base")
    )
    print(f"Rates from cache (updated at {result['last_refresh']}):")
    for pair, rate in result["rows"]:
        print(f"- {pair}: {format_rate(rate)}")


def cmd_schedule_updates(tokens):
    """schedule-updates [--interval <сек>] [--runs <int>] (Ctrl+C — остановить)."""
    flags = parse_flags(tokens, optional=("interval", "runs"))
    try:
        interval = int(flags.get("interval", ParserConfig().UPDATE_INTERVAL_SECONDS))
        runs = int(flags["runs"]) if "runs" in flags else None
    except ValueError:
        raise CliUsageError("'interval' и 'runs' должны быть целыми числами") from None
    done = RatesScheduler(build_updater(), interval).run(runs)
    print(f"Планировщик остановлен. Выполнено обновлений: {done}")


def cmd_help(tokens):
    """help."""
    table = PrettyTable(["Команда", "Описание"])
    table.align = "l"
    for usage, description in COMMANDS:
        table.add_row([usage, description])
    print(table)
    print(f"Поддерживаемые валюты: {', '.join(get_supported_codes())}")


HANDLERS = {
    "register": cmd_register,
    "login": cmd_login,
    "logout": cmd_logout,
    "show-portfolio": cmd_show_portfolio,
    "buy": cmd_buy,
    "sell": cmd_sell,
    "get-rate": cmd_get_rate,
    "update-rates": cmd_update_rates,
    "show-rates": cmd_show_rates,
    "schedule-updates": cmd_schedule_updates,
    "help": cmd_help,
}


def execute(line: str) -> bool:
    """Выполняет одну команду. Возвращает False, если нужно завершить работу."""
    try:
        tokens = shlex.split(line)
    except ValueError:
        print("Ошибка разбора команды: проверьте кавычки")
        return True
    if not tokens:
        return True
    command, args = tokens[0].lower(), tokens[1:]
    if command in EXIT_COMMANDS:
        return False
    handler = HANDLERS.get(command)
    if handler is None:
        print(f"Неизвестная команда '{command}'. Введите 'help' для справки.")
        return True

    try:
        handler(args)
    except InsufficientFundsError as error:
        print(error)
    except CurrencyNotFoundError as error:
        print(
            f"{error}. Поддерживаемые коды: {', '.join(get_supported_codes())}. "
            "Подробнее: help"
        )
    except ApiRequestError as error:
        print(f"{error}. Повторите попытку позже или проверьте сеть.")
    except (ValutaTradeError, ValueError) as error:
        print(error)
    return True


def main():
    """Интерактивный цикл CLI."""
    setup_logging()
    print("ValutaTrade Hub. Введите 'help' для списка команд, 'exit' — для выхода.")
    while True:
        try:
            line = input(PROMPT)
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not execute(line):
            break
