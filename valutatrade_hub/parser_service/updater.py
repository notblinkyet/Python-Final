"""RatesUpdater — координация обновления курсов из всех источников."""

import logging

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.core.utils import to_iso_utc, utc_now
from valutatrade_hub.logging_config import PARSER_LOGGER
from valutatrade_hub.parser_service.api_clients import (
    BaseApiClient,
    CoinGeckoClient,
    ExchangeRateApiClient,
)
from valutatrade_hub.parser_service.config import ParserConfig
from valutatrade_hub.parser_service.storage import RatesStorage, make_history_record


class RatesUpdater:
    """Опрашивает клиентов, объединяет курсы и сохраняет их."""

    def __init__(self, clients: list[BaseApiClient], storage: RatesStorage):
        self.clients = clients
        self.storage = storage
        self.logger = logging.getLogger(PARSER_LOGGER)

    def run_update(self, source: str | None = None) -> dict:
        """Обновляет курсы; падение одного источника не останавливает остальные.

        Возвращает {'updated': int, 'errors': [...], 'last_refresh': str}.
        """
        clients = self.clients
        if source:
            clients = [c for c in self.clients if c.source_key == source.lower()]
            if not clients:
                names = ", ".join(c.source_key for c in self.clients)
                raise ValueError(f"Неизвестный источник '{source}'. Доступны: {names}")

        self.logger.info("Starting rates update...")
        pairs, history, errors = {}, [], []
        for client in clients:
            try:
                rates = client.fetch_rates()
            except ApiRequestError as error:
                self.logger.error(
                    "Failed to fetch from %s: %s", client.source_name, error.reason
                )
                errors.append(str(error))
                continue
            timestamp = to_iso_utc(utc_now())
            self.logger.info(
                "Fetching from %s... OK (%d rates)", client.source_name, len(rates)
            )
            for pair, rate in rates.items():
                pairs[pair] = {
                    "rate": rate,
                    "updated_at": timestamp,
                    "source": client.source_name,
                }
                history.append(
                    make_history_record(
                        pair, rate, timestamp, client.source_name, client.last_meta
                    )
                )

        last_refresh = to_iso_utc(utc_now())
        updated = 0
        if pairs:
            self.logger.info(
                "Writing %d rates to %s...", len(pairs), self.storage.rates_path
            )
            updated = self.storage.save_snapshot(pairs, last_refresh)
            self.storage.append_history(history)
        self.logger.info("Update finished: %d rates, %d errors", updated, len(errors))
        return {"updated": updated, "errors": errors, "last_refresh": last_refresh}


def build_updater(config: ParserConfig | None = None) -> RatesUpdater:
    """Собирает RatesUpdater со стандартными клиентами и хранилищем."""
    config = config or ParserConfig()
    return RatesUpdater(
        [CoinGeckoClient(config), ExchangeRateApiClient(config)],
        RatesStorage(config.RATES_FILE_PATH, config.HISTORY_FILE_PATH),
    )
