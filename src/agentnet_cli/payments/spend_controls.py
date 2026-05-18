from __future__ import annotations

import fcntl
import json
import sys
import time
from pathlib import Path

from ..paths import agentnet_home


class SpendController:
    def __init__(
        self,
        *,
        daily_limit_usd: float = 100.0,
        single_tx_limit_usd: float = 25.0,
    ) -> None:
        self._daily_limit = daily_limit_usd
        self._single_tx_limit = single_tx_limit_usd
        self._log_path = agentnet_home() / "spend_log.json"

    def check_allowed(self, *, amount_usd: float) -> bool:
        if amount_usd > self._single_tx_limit:
            return False
        if self.daily_spent_usd() + amount_usd > self._daily_limit:
            return False
        return True

    def record_spend(self, *, amount_usd: float, receipt_ref: str) -> None:
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._log_path, "a+") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                f.seek(0)
                raw = f.read()
                try:
                    data = json.loads(raw) if raw.strip() else {"entries": []}
                except json.JSONDecodeError:
                    print(
                        f"WARNING: Corrupted spend log at {self._log_path}, resetting",
                        file=sys.stderr,
                    )
                    data = {"entries": []}

                cutoff = time.time() - 86400
                entries = [e for e in data.get("entries", []) if e.get("timestamp", 0) > cutoff]
                entries.append({
                    "amount_usd": amount_usd,
                    "receipt_ref": receipt_ref,
                    "timestamp": time.time(),
                })

                f.seek(0)
                f.truncate()
                f.write(json.dumps({"entries": entries}, indent=2) + "\n")
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    def daily_spent_usd(self) -> float:
        return sum(e["amount_usd"] for e in self._load_today_entries())

    def _load_today_entries(self) -> list[dict]:
        if not self._log_path.exists():
            return []
        try:
            data = json.loads(self._log_path.read_text())
        except json.JSONDecodeError:
            print(
                f"WARNING: Corrupted spend log at {self._log_path}",
                file=sys.stderr,
            )
            return []
        except OSError:
            return []
        cutoff = time.time() - 86400
        return [e for e in data.get("entries", []) if e.get("timestamp", 0) > cutoff]

    def _save_entries(self, entries: list[dict]) -> None:
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log_path.write_text(json.dumps({"entries": entries}, indent=2) + "\n")
