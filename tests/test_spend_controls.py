"""Tests for spend control enforcement."""
from __future__ import annotations

import json
import time
from pathlib import Path

from agentnet_cli.payments.spend_controls import SpendController


class TestSpendController:
    def test_allows_spend_under_limits(self, fake_home):
        ctrl = SpendController(daily_limit_usd=100.0, single_tx_limit_usd=25.0)
        assert ctrl.check_allowed(amount_usd=10.0) is True

    def test_rejects_over_single_tx_limit(self, fake_home):
        ctrl = SpendController(daily_limit_usd=100.0, single_tx_limit_usd=25.0)
        assert ctrl.check_allowed(amount_usd=30.0) is False

    def test_rejects_over_daily_limit(self, fake_home):
        ctrl = SpendController(daily_limit_usd=20.0, single_tx_limit_usd=25.0)
        ctrl.record_spend(amount_usd=15.0, receipt_ref="tx_1")
        assert ctrl.check_allowed(amount_usd=10.0) is False

    def test_allows_up_to_daily_limit(self, fake_home):
        ctrl = SpendController(daily_limit_usd=20.0, single_tx_limit_usd=25.0)
        ctrl.record_spend(amount_usd=15.0, receipt_ref="tx_1")
        assert ctrl.check_allowed(amount_usd=5.0) is True

    def test_record_and_read_back(self, fake_home):
        ctrl = SpendController(daily_limit_usd=100.0, single_tx_limit_usd=50.0)
        ctrl.record_spend(amount_usd=12.50, receipt_ref="pi_abc")
        ctrl.record_spend(amount_usd=7.50, receipt_ref="0xtx")
        assert ctrl.daily_spent_usd() == 20.0

    def test_spend_log_persists_to_disk(self, fake_home):
        ctrl1 = SpendController(daily_limit_usd=100.0, single_tx_limit_usd=50.0)
        ctrl1.record_spend(amount_usd=33.0, receipt_ref="ref_1")

        ctrl2 = SpendController(daily_limit_usd=100.0, single_tx_limit_usd=50.0)
        assert ctrl2.daily_spent_usd() == 33.0

    def test_resets_after_day_boundary(self, fake_home):
        ctrl = SpendController(daily_limit_usd=100.0, single_tx_limit_usd=50.0)
        log_path = Path(fake_home) / ".agentnet" / "spend_log.json"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        yesterday = time.time() - 86400 - 1
        log_path.write_text(json.dumps({
            "entries": [{"amount_usd": 99.0, "receipt_ref": "old", "timestamp": yesterday}],
        }))
        assert ctrl.check_allowed(amount_usd=50.0) is True
