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

    def test_turnaround_growth_above_one_thousand_percent_is_preserved(self):
        candidate = self.candidate("TURN", eps=44.17, pe=22.13, growth=13.6845)
        result = self.service.shortlist([candidate])
        self.assertEqual(result["shortlist"][0]["eps_growth_yoy"], 13.6845)

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

    def test_purchase_floors_cap_and_accepts_lower_requested_amount(self):
        account = dict(account_id='acct', portfolio_equity=493.249,
                       cash_balance=493.249, buying_power=493.249)
        plan = self.service.propose_purchase(account, [], [self.candidate()])
        self.assertEqual(plan['order_intents'][0]['dollar_amount'], 98.64)
        account['portfolio_equity'] = 493.50
        plan = self.service.propose_purchase(account, [], [self.candidate()], 98.64)
        self.assertEqual(plan['order_intents'][0]['dollar_amount'], 98.64)
        plan = self.service.propose_purchase(account, [], [self.candidate()], 200)
        self.assertEqual(plan['order_intents'][0]['dollar_amount'], 98.70)
        account['portfolio_equity'] = 493.20
        result = self.service.validate_purchase(plan['plan_id'], account,
                                                dict(symbol='ACME', price=100))
        self.assertIn('POSITION_CAP_EXCEEDED', result['blockers'])

    def test_purchase_floors_cash_headroom(self):
        account = dict(account_id='acct', portfolio_equity=500,
                       cash_balance=55.009, buying_power=55.009)
        plan = self.service.propose_purchase(account, [], [self.candidate()])
        self.assertEqual(plan['order_intents'][0]['dollar_amount'], 5.00)

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

    def test_dashboard_snapshot_compares_purchase_metrics_with_current_research(self):
        current = {
            "symbol": "ACME", "company_name": "Acme Industries", "price": 110,
            "entry_price": 100, "peak_price_since_purchase": 115,
            "eps_ttm": 6, "prior_eps_ttm": 5, "pe_ttm": 18,
            "sector_median_pe": 20, "last_earnings_surprise_pct": .05,
            "guidance_direction": "unchanged", "next_earnings_date": "2026-10-20",
            "analyst_target_mean": 130, "analyst_consensus": "buy",
            "news_sentiment": .2, "material_negative_news": False,
            "research_as_of": self.now.isoformat(),
            "recent_news": [{"title": "Quarterly results", "publisher": "Acme",
                             "url": "https://example.com/results", "impact": "positive"}],
            "evidence": [{"title": "10-Q", "url": "https://sec.example/a"},
                         {"title": "News", "url": "https://news.example/a"}],
        }
        result = self.service.build_dashboard_snapshot(
            {"account_id": "account-5837", "portfolio_equity": 500,
             "cash_balance": 390, "buying_power": 390},
            [{"symbol": "ACME", "quantity": 1, "average_buy_price": 100, "price": 110}],
            [current],
            [{"symbol": "ACME", "company_name": "Acme Industries",
              "purchased_at": "2026-08-01", "thesis": "Profitable at a reasonable valuation.",
              "eps_ttm": 5, "pe_ttm": 20, "analyst_target_mean": 120}],
        )
        self.assertEqual(result["schema_version"], "portfolio-dashboard-v1")
        self.assertEqual(result["account"]["account_suffix"], "5837")
        self.assertEqual(result["account"]["invested_value"], 110)
        self.assertEqual(result["holdings"][0]["status"], "HOLD")
        self.assertEqual(result["holdings"][0]["metrics"]["eps_ttm"]["change"], .2)
        self.assertEqual(result["holdings"][0]["recent_news"][0]["title"], "Quarterly results")

    def test_dashboard_snapshot_keeps_holding_when_purchase_history_is_missing(self):
        current = {
            "symbol": "ACME", "price": 110, "entry_price": 100,
            "peak_price_since_purchase": 115, "eps_ttm": 6,
            "prior_eps_ttm": 5, "pe_ttm": 18, "sector_median_pe": 20,
            "last_earnings_surprise_pct": 0, "guidance_direction": "unchanged",
            "next_earnings_date": "2026-10-20", "analyst_target_mean": 130,
            "analyst_consensus": "buy", "news_sentiment": 0,
            "material_negative_news": False, "research_as_of": self.now.isoformat(),
            "evidence": [{"title": "10-Q", "url": "https://sec.example/a"},
                         {"title": "News", "url": "https://news.example/a"}],
        }
        result = self.service.build_dashboard_snapshot(
            {"account_id": "account-5837", "portfolio_equity": 500,
             "cash_balance": 390},
            [{"symbol": "ACME", "quantity": 1, "average_buy_price": 100, "price": 110}],
            [current], [],
        )
        holding = result["holdings"][0]
        self.assertFalse(holding["purchase_record_available"])
        self.assertIsNone(holding["metrics"]["eps_ttm"]["at_purchase"])
        self.assertIsNone(holding["metrics"]["pe_ttm"]["change"])
        self.assertEqual(holding["current_price"], 110)


if __name__ == "__main__":
    unittest.main()
