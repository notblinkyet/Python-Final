# ValutaTrade Hub

Консольная платформа для отслеживания и симуляции торговли валютами.
Пользователь регистрируется, ведёт виртуальный портфель фиатных (USD, EUR, GBP, RUB)
и криптовалют (BTC, ETH, SOL), покупает и продаёт валюту и смотрит актуальные курсы.

Система состоит из двух частей:

- **Core Service** — CLI, пользователи, портфели, сделки (`valutatrade_hub/core`, `cli`);
- **Parser Service** — получает курсы из CoinGecko и ExchangeRate-API и складывает их
  в локальный кеш (`valutatrade_hub/parser_service`).

## Структура

```text
├── data/
│   ├── users.json            # пользователи
│   ├── portfolios.json       # портфели и кошельки
│   ├── rates.json            # кеш текущих курсов (читает Core Service)
│   └── exchange_rates.json   # история замеров Parser Service
├── valutatrade_hub/
│   ├── logging_config.py     # формат логов и ротация
│   ├── decorators.py         # @log_action
│   ├── core/
│   │   ├── currencies.py     # Currency → FiatCurrency / CryptoCurrency, get_currency()
│   │   ├── exceptions.py     # доменные исключения
│   │   ├── models.py         # User, Wallet, Portfolio
│   │   ├── usecases.py       # бизнес-логика
│   │   └── utils.py          # валидация и форматирование
│   ├── infra/
│   │   ├── settings.py       # SettingsLoader (Singleton)
│   │   └── database.py       # DatabaseManager (Singleton), атомарная запись JSON
│   ├── parser_service/
│   │   ├── config.py         # ParserConfig: API, валюты, пути, таймауты
│   │   ├── api_clients.py    # BaseApiClient, CoinGeckoClient, ExchangeRateApiClient
│   │   ├── updater.py        # RatesUpdater
│   │   ├── storage.py        # запись rates.json и exchange_rates.json
│   │   └── scheduler.py      # периодическое обновление
│   └── cli/interface.py      # команды
├── main.py
├── Makefile
└── pyproject.toml
```

## Установка и запуск

Нужен [uv](https://docs.astral.sh/uv/).

```bash
make install          # uv sync
make project          # uv run project — запуск CLI
make lint             # uv run ruff check .
make build            # uv build
make publish          # сборка + проверка метаданных (uvx twine check)
make package-install  # uv tool install dist/*.whl → команда `project` глобально
```

Запускать нужно из корня проекта: оттуда читаются `pyproject.toml` (настройки)
и папка `data/`.

## Команды CLI

```text
> register --username alice --password 1234
Пользователь 'alice' зарегистрирован (id=1). Войдите: login --username alice --password ****

> login --username alice --password 1234
Вы вошли как 'alice'

> buy --currency BTC --amount 0.05
Покупка выполнена: 0.0500 BTC по курсу 59337.21 USD/BTC
Изменения в портфеле:
- BTC: было 0.0000 → стало 0.0500
Оценочная стоимость покупки: 2,966.86 USD

> sell --currency BTC --amount 0.01
Продажа выполнена: 0.0100 BTC по курсу 59337.21 USD/BTC
Изменения в портфеле:
- BTC: было 0.0500 → стало 0.0400
Оценочная выручка: 593.37 USD

> show-portfolio --base USD
Портфель пользователя 'alice' (база: USD):
- BTC: 0.0400  → 2,373.49 USD
- USD: 593.37  → 593.37 USD
---------------------------------
ИТОГО: 2,966.86 USD

> get-rate --from USD --to BTC
Курс USD→BTC: 0.00001685 (обновлено: 2025-10-10 12:00:00)
Обратный курс BTC→USD: 59337.21

> update-rates
INFO: Starting rates update...
INFO: Fetching from CoinGecko... OK (3 rates)
INFO: Fetching from ExchangeRate-API... OK (3 rates)
INFO: Writing 6 rates to data/rates.json...
Update successful. Total rates updated: 6. Last refresh: 2025-10-10T15:30:00Z

> show-rates --top 2
Rates from cache (updated at 2025-10-10T15:30:00Z):
- BTC_USD: 59337.21
- ETH_USD: 3720.00
```

Также есть `logout`, `help`, `exit` и `show-rates --currency <код> | --base <код>`.
Команда `schedule-updates --interval 300 [--runs N]` запускает периодическое
обновление курсов (Ctrl+C — остановить).

Логика сделок: `buy` создаёт кошелёк автоматически и увеличивает его баланс;
`sell` списывает валюту и зачисляет выручку в USD-кошелёк.

### Ошибки

| Ситуация | Сообщение |
|---|---|
| нет входа | `Сначала выполните login` |
| неверная сумма | `'amount' должен быть положительным числом` |
| нет кошелька | `У вас нет кошелька 'BTC'. Добавьте валюту: ...` |
| мало средств | `Недостаточно средств: доступно 0.0400 BTC, требуется 0.0500 BTC` |
| неизвестная валюта | `Неизвестная валюта 'ABC'` + список поддерживаемых кодов |
| нет курса | `Курс USD→BTC недоступен. Повторите попытку позже.` |
| сбой API | `Ошибка при обращении к внешнему API: ...` |

## Курсы, кеш и TTL

- `data/rates.json` — снимок «последний курс для каждой пары» (`BTC_USD`, `EUR_USD`, …)
  с `updated_at`, `source` и общим `last_refresh`. Пара перезаписывается,
  только если новое значение свежее.
- `data/exchange_rates.json` — история замеров; `id` = `<FROM>_<TO>_<ISO-время>`,
  дубли не записываются. Все файлы пишутся атомарно (временный файл → `os.replace`).
- TTL кеша — `rates_ttl_seconds` в `[tool.valutatrade]` (по умолчанию 300 с).
  Если нужный курс старше TTL, Core Service пытается обновить кеш через Parser Service;
  если не получилось — использует последний известный курс и предупреждает,
  что он устарел.

## Parser Service и API-ключ

CoinGecko работает без ключа. Для ExchangeRate-API получите бесплатный ключ на
<https://www.exchangerate-api.com/> и передайте его через переменную окружения
(в коде и в git ключ не хранится):

```bash
export EXCHANGERATE_API_KEY=ваш_ключ
make project
> update-rates                    # оба источника
> update-rates --source coingecko # только криптовалюты
```

Если один источник недоступен, данные второго всё равно сохраняются,
а ошибка пишется в `logs/parser.log`.

## Настройки

Секция `[tool.valutatrade]` в `pyproject.toml` (читает `SettingsLoader`):
пути к данным (`data_dir`, `users_file`, …), `rates_ttl_seconds`,
`default_base_currency`, `log_dir`, `log_level`, параметры ротации логов.

## Логи

- `logs/actions.log` — операции `REGISTER`, `LOGIN`, `BUY`, `SELL` (декоратор `@log_action`):

  ```text
  INFO 2025-10-09T12:05:22 BUY user='alice' user_id=1 currency='BTC' amount=0.0500 rate=59337.21 base='USD' before=0.0000 after=0.0500 result=OK
  ```

- `logs/parser.log` — шаги обновления курсов.

Ротация по размеру (1 МБ, 3 архивных файла), уровень по умолчанию — `INFO`.

## Демонстрация

<!-- Замените на свою запись asciinema -->
[![asciicast](https://asciinema.org/a/ВАШ_ID.svg)](https://asciinema.org/a/ВАШ_ID)
