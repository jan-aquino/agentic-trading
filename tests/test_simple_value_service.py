import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agent.simple_value_service import SimpleValueService
from agent.trading_analysis_service import FilePlanStore


class TestSimpleValueService(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.now = datetime(2026, 9, 10, 15, tzinfo=timezone.utc)
        self.service = SimpleValueService(
            store=FilePlanStore(Path(self.temp.name)), clock=lambda: self.now
        )

    def tearDown(self):
        self.temp.cleanup()

    def candidate(self, symbol="ACME", eps=8, pe=12, growth=.15, price=100, target=125):
        return {
            "symbol": symbol, "company_name": symbol, "sector": "industrials",
            "price": price, "eps_ttm": eps, "pe_ttm": pe,
            "eps_growth_yoy": growth, "next_earnings_date": "2026-10-20",
            "analyst_target_mean": target, "analyst_consensus": "buy",
            "news_sentiment": .2, "tradable": True, "fractional_tradable": True,
            "research_as_of": self.now.isoformat(),
            "evidence": [{"title": "10-Q", "url": "https://sec.example/a"},
                         {"title": "Market data", "url": "https://market.example/a"}],
        }

    def test_shortlist_rejects_loss_maker_and_expensive_stock(self):
        result = self.service.shortlist([
            self.candidate("GOOD"), self.candidate("LOSS", eps=-1), self.candidate("PRICEY", pe=40)
        ])
        self.assertEqual([item["symbol"] for item in result["shortlist"]], ["GOOD"])

    def test_purchase_uses_cash_buffer_and_one_position(self):
        plan = self.service.propose_purchase(
            {"account_id": "acct", "portfolio_equity": 500, "cash_balance": 500, "buying_power": 500},
            [], [self.candidate("GOOD"), self.candidate("SECOND", eps=6, pe=15)],
        )
        self.assertEqual(len(plan["order_intents"]), 1)
        self.assertEqual(plan["order_intents"][0]["dollar_amount"], 100)

    def test_validation_blocks_price_drift(self):
        plan = self.service.propose_purchase(
            {"account_id": "acct", "portfolio_equity": 500, "cash_balance": 500, "buying_power": 500},
            [], [self.candidate("GOOD")],
        )
        result = self.service.validate_purchase(
            plan["plan_id"],
            {"account_id": "acct", "portfolio_equity": 500, "cash_balance": 500, "buying_power": 500},
            {"symbol": "GOOD", "price": 110},
        )
        self.assertFalse(result["execution_ready"])
        self.assertIn("PRICE_DRIFT_OVER_5_PERCENT", result["blockers"])

    def test_sell_review_requires_two_normal_or_one_severe_signal(self):
        base = {
            "symbol": "ACME", "price": 100, "eps_ttm": 4, "prior_eps_ttm": 5,
            "entry_price": 70, "peak_price_since_purchase": 105,
            "pe_ttm": 40, "sector_median_pe": 20, "last_earnings_surprise_pct": 0,
            "guidance_direction": "unchanged", "next_earnings_date": "2026-10-20",
            "analyst_target_mean": 120, "analyst_consensus": "hold", "news_sentiment": 0,
            "material_negative_news": False, "research_as_of": self.now.isoformat(),
            "evidence": [{"title": "10-Q", "url": "https://sec.example/a"},
                         {"title": "News", "url": "https://news.example/a"}],
        }
        result = self.service.evaluate_holdings([base])
        self.assertEqual(result["decisions"][0]["action"], "SELL_REVIEW")

    def test_twenty_percent_gain_only_triggers_reassessment(self):
        holding = {
            "symbol": "ACME", "price": 120, "entry_price": 100,
            "peak_price_since_purchase": 120, "eps_ttm": 6,
            "prior_eps_ttm": 5, "pe_ttm": 18, "sector_median_pe": 20,
            "last_earnings_surprise_pct": .05, "guidance_direction": "raised",
            "next_earnings_date": "2026-10-20", "analyst_target_mean": 140,
            "analyst_consensus": "buy", "news_sentiment": .3,
            "material_negative_news": False, "research_as_of": self.now.isoformat(),
            "evidence": [{"title": "10-Q", "url": "https://sec.example/a"},
                         {"title": "News", "url": "https://news.example/a"}],
        }
        decision = self.service.evaluate_holdings([holding])["decisions"][0]
        self.assertEqual(decision["action"], "WATCH")
        self.assertIn("PROFIT_TARGET_REACHED_REASSESS", decision["signals"])

    def test_trailing_drawdown_after_target_triggers_sell_review(self):
        holding = {
            "symbol": "ACME", "price": 110, "entry_price": 100,
            "peak_price_since_purchase": 130, "eps_ttm": 6,
            "prior_eps_ttm": 5, "pe_ttm": 18, "sector_median_pe": 20,
            "last_earnings_surprise_pct": .05, "guidance_direction": "unchanged",
            "next_earnings_date": "2026-10-20", "analyst_target_mean": 130,
            "analyst_consensus": "buy", "news_sentiment": .1,
            "material_negative_news": False, "research_as_of": self.now.isoformat(),
            "evidence": [{"title": "10-Q", "url": "https://sec.example/a"},
                         {"title": "News", "url": "https://news.example/a"}],
        }
        decision = self.service.evaluate_holdings([holding])["decisions"][0]
        self.assertEqual(decision["action"], "SELL_REVIEW")
        self.assertIn("PROFIT_PROTECTION_TRAILING_DRAWDOWN", decision["severe_signals"])


if __name__ == "__main__":
    unittest.main()
