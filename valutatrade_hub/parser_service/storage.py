"""Хранилище Parser Service: снимок rates.json и история exchange_rates.json."""

from valutatrade_hub.core.utils import parse_iso
from valutatrade_hub.infra.database import read_json, write_json_atomic

PAIR_SEPARATOR = "_"


class RatesStorage:
    """Чтение и атомарная запись курсов."""

    def __init__(self, rates_path: str, history_path: str):
        self.rates_path = rates_path
        self.history_path = history_path

    def load_snapshot(self) -> dict:
        """Текущий снимок {'pairs': {...}, 'last_refresh': ...}."""
        snapshot = read_json(self.rates_path, {})
        snapshot.setdefault("pairs", {})
        return snapshot

    def save_snapshot(self, new_pairs: dict, last_refresh: str) -> int:
        """Сливает новые курсы со снимком: пара обновляется, только если свежее.

        Возвращает число обновлённых пар.
        """
        snapshot = self.load_snapshot()
        pairs = snapshot["pairs"]
        updated = 0
        for pair, info in new_pairs.items():
            current = pairs.get(pair)
            if current is None or parse_iso(info["updated_at"]) >= parse_iso(
                current["updated_at"]
            ):
                pairs[pair] = info
                updated += 1
        snapshot["last_refresh"] = last_refresh
        write_json_atomic(self.rates_path, snapshot)
        return updated

    def append_history(self, records: list[dict]) -> int:
        """Добавляет замеры в историю без дублей по id. Возвращает число новых."""
        history = read_json(self.history_path, [])
        known_ids = {record["id"] for record in history}
        fresh = [record for record in records if record["id"] not in known_ids]
        if fresh:
            write_json_atomic(self.history_path, history + fresh)
        return len(fresh)


def make_history_record(pair: str, rate: float, timestamp: str, source: str, meta):
    """Запись истории с id вида BTC_USD_2025-10-10T12:00:00Z."""
    from_code, to_code = pair.split(PAIR_SEPARATOR, 1)
    return {
        "id": f"{pair}{PAIR_SEPARATOR}{timestamp}",
        "from_currency": from_code,
        "to_currency": to_code,
        "rate": rate,
        "timestamp": timestamp,
        "source": source,
        "meta": meta,
    }
