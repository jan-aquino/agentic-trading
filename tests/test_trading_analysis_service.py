"""Tests for the research-driven, proposal-only MCP boundary."""

import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agent.research_portfolio_pipeline import ResearchInputError
from agent.trading_analysis_service import AnalysisInputError, FilePlanStore, TradingAnalysisService


class TestTradingAnalysisService(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.now = datetime(2026, 9, 5, 14, 0, tzinfo=timezone.utc)
        self.service = TradingAnalysisService(
            store=FilePlanStore(Path(self.tmp.name)), clock=lambda: self.now,
            plan_ttl_seconds=600, max_snapshot_age_seconds=900, max_price_drift_bps=50,
            expired_plan_revalidation_grace_seconds=0,
        )
        self.account = {"account_id": "agentic", "portfolio_equity": 500,
                        "cash_balance": 500, "buying_power": 500}
        self.candidates = [self.candidate("ACME", "technology", 100),
                           self.candidate("BETA", "healthcare", 50)]

    def tearDown(self):
        self.tmp.cleanup()

    def candidate(self, symbol, sector, price):
        return {
            "symbol": symbol, "asset_type": "equity", "sector": sector,
            "tradable": True, "fractional_tradable": True, "price": price,
            "research_as_of": self.now.isoformat(), "thesis": f"Thesis for {symbol}",
            "agent_conviction": 80,
            "evidence": [
                {"title": "Filing", "url": f"https://example.com/{symbol}/filing", "observed_at": self.now.isoformat()},
                {"title": "Market data", "url": f"https://example.com/{symbol}/market", "observed_at": self.now.isoformat()},
            ],
            "fundamentals": {"revenue_growth": .30, "earnings_growth": .35,
                "free_cash_flow_margin": .25, "return_on_equity": .28,
                "forward_pe": 22, "peg_ratio": 1.2},
            "technical": {"return_20d": .08, "return_60d": .18, "above_sma_200": True},
            "catalysts": {"score": 75, "sentiment": .5},
            "risk": {"annualized_volatility": .28, "max_drawdown": -.18,
                "beta": 1.05, "average_dollar_volume": 50_000_000},
        }

    def make_plan(self, candidates=None, positions=None):
        return self.service.generate_trade_plan(
            self.account, positions or [], candidates or self.candidates, self.now.isoformat()
        )

    def validation_quotes(self, plan):
        return [{"symbol": item["symbol"], "price": item["limit_price"]}
                for item in plan["order_intents"]]

    def test_dynamic_candidates_and_fractional_500_account(self):
        plan = self.make_plan()
        self.assertEqual(set(plan["selected_symbols"]), {"ACME", "BETA"})
        self.assertNotIn("NVDA", plan["target_weights"])
        self.assertFalse(plan["abstained"])
        self.assertTrue(all(i["amount_type"] == "fractional_shares" for i in plan["order_intents"]))
        self.assertTrue(all(0 < i["estimated_notional"] <= 100 for i in plan["order_intents"]))

    def test_research_requirements_assign_source_authority(self):
        requirements = self.service.get_research_requirements()
        self.assertIn("price", requirements["source_authority"]["robinhood"])
        self.assertIn("fundamentals", requirements["source_authority"]["research_provider"])
        self.assertIn("agent_conviction", requirements["source_authority"]["chatgpt_work"])
        self.assertIn("not trade instructions", requirements["provider_guidance"]["rallies"])

    def test_next_market_open_accepts_close_and_filters_high_volatility(self):
        closing_time = self.now
        self.now += timedelta(hours=8)
        volatile = self.candidate("WILD", "technology", 25)
        volatile["risk"]["annualized_volatility"] = .80
        plan = self.service.generate_trade_plan(
            self.account, [], self.candidates + [volatile], closing_time.isoformat(),
            planning_mode="next_market_open",
        )
        self.assertEqual(plan["planning_mode"], "next_market_open")
        self.assertIn("AFTER_HOURS_REFERENCE_PRICES", plan["warnings"])
        self.assertGreater(
            datetime.fromisoformat(plan["expires_at"]) - datetime.fromisoformat(plan["created_at"]),
            timedelta(days=3),
        )
        wild = next(item for item in plan["ranked_candidates"] if item["symbol"] == "WILD")
        self.assertIn("EXCESSIVE_VOLATILITY", wild["rejection_reasons"])

    def test_immediate_mode_still_rejects_stale_snapshot(self):
        with self.assertRaisesRegex(AnalysisInputError, "market snapshot is stale"):
            self.service.generate_trade_plan(
                self.account, [], self.candidates,
                (self.now - timedelta(hours=1)).isoformat(),
            )

    def test_restricted_candidate_is_rejected(self):
        plan = self.make_plan(self.candidates + [self.candidate("SNOW", "technology", 40)])
        snow = next(item for item in plan["ranked_candidates"] if item["symbol"] == "SNOW")
        self.assertFalse(snow["eligible"])
        self.assertNotIn("SNOW", {item["symbol"] for item in plan["order_intents"]})

    def test_weak_universe_can_abstain(self):
        weak = self.candidate("WEAK", "industrials", 20)
        weak["agent_conviction"] = 0
        weak["fundamentals"] = {"revenue_growth": -.2, "earnings_growth": -.3,
            "free_cash_flow_margin": -.1, "return_on_equity": -.1,
            "forward_pe": 60, "peg_ratio": 4}
        weak["technical"] = {"return_20d": -.2, "return_60d": -.3, "above_sma_200": False}
        weak["catalysts"] = {"score": 0, "sentiment": -1}
        weak["risk"].update({"annualized_volatility": .9, "max_drawdown": -.65, "beta": 2})
        plan = self.make_plan([weak])
        self.assertTrue(plan["abstained"])
        self.assertEqual(plan["target_weights"], {"CASH": 1.0})

    def test_every_holding_requires_research(self):
        with self.assertRaisesRegex(ResearchInputError, "missing: HOLD"):
            self.make_plan(positions=[{"symbol": "HOLD", "quantity": 1, "current_price": 25}])

    def test_validation_and_price_drift(self):
        plan = self.make_plan()
        quotes = self.validation_quotes(plan)
        valid = self.service.validate_trade_plan(
            plan["plan_id"], self.account, [], quotes, self.now.isoformat())
        self.assertTrue(valid["execution_ready"])
        self.assertFalse(valid["can_execute_orders"])
        quotes[0]["price"] *= 1.01
        blocked = self.service.validate_trade_plan(
            plan["plan_id"], self.account, [], quotes, self.now.isoformat())
        self.assertFalse(blocked["execution_ready"])
        self.assertTrue(any(item.startswith("PRICE_DRIFT:") for item in blocked["blockers"]))

    def test_recently_expired_plan_can_pass_fresh_revalidation(self):
        self.service.expired_plan_revalidation_grace_seconds = 86_400
        plan = self.make_plan()
        self.now += timedelta(seconds=601)
        valid = self.service.validate_trade_plan(
            plan["plan_id"], self.account, [], self.validation_quotes(plan), self.now.isoformat()
        )
        self.assertTrue(valid["execution_ready"])
        self.assertNotIn("PLAN_EXPIRED", valid["blockers"])
        self.assertIn("PLAN_EXPIRED_WITHIN_REVALIDATION_GRACE", valid["warnings"])

    def test_expiry_staleness_and_tampering(self):
        plan = self.make_plan()
        quotes = self.validation_quotes(plan)
        path = Path(self.tmp.name) / f"{plan['plan_id']}.json"
        tampered = copy.deepcopy(plan)
        tampered["order_intents"][0]["quantity"] = 999
        path.write_text(json.dumps(tampered), encoding="utf-8")
        with self.assertRaises(RuntimeError):
            self.service.validate_trade_plan(
                plan["plan_id"], self.account, [], quotes, self.now.isoformat())
        second = self.make_plan()
        self.now += timedelta(seconds=601)
        expired = self.service.validate_trade_plan(
            second["plan_id"], self.account, [], self.validation_quotes(second), self.now.isoformat())
        self.assertIn("PLAN_EXPIRED", expired["blockers"])
        with self.assertRaises(AnalysisInputError):
            self.service.generate_trade_plan(
                self.account, [], self.candidates, (self.now - timedelta(hours=1)).isoformat())


if __name__ == "__main__":
    unittest.main()
