"""Планировщик периодического обновления курсов."""

import logging
import time

from valutatrade_hub.logging_config import PARSER_LOGGER
from valutatrade_hub.parser_service.updater import RatesUpdater


class RatesScheduler:
    """Запускает RatesUpdater.run_update() каждые interval_seconds секунд."""

    def __init__(self, updater: RatesUpdater, interval_seconds: int):
        if interval_seconds <= 0:
            raise ValueError("Интервал должен быть положительным числом секунд")
        self.updater = updater
        self.interval_seconds = interval_seconds
        self.logger = logging.getLogger(PARSER_LOGGER)

    def run(self, max_runs: int | None = None) -> int:
        """Блокирующий цикл обновлений (Ctrl+C — стоп). Возвращает число запусков."""
        runs = 0
        try:
            while max_runs is None or runs < max_runs:
                self.updater.run_update()
                runs += 1
                if max_runs is not None and runs >= max_runs:
                    break
                self.logger.info("Next update in %d s", self.interval_seconds)
                time.sleep(self.interval_seconds)
        except KeyboardInterrupt:
            self.logger.info("Scheduler stopped by user")
        return runs
