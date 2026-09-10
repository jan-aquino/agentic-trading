"""Tests for the isolated historical market-only research mode."""

import unittest
from datetime import datetime, timezone

from agent.historical_research_proxy import HistoricalMarketProxyPipeline
from agent.research_portfolio_pipeline import ResearchInputError, ResearchPortfolioPipeline


class TestHistoricalResearchProxy(unittest.TestCase):
    def packet(self):
        observed = datetime(2026, 1, 2, 21, tzinfo=timezone.utc).isoformat()
        return {
            "symbol": "NVDA", "asset_type": "equity", "sector": "technology",
            "tradable": True, "fractional_tradable": True,
            "leveraged_or_inverse": False, "price": 100,
            "research_as_of": observed, "research_mode": "historical_market_proxy_v1",
            "agent_conviction": 80, "thesis": "Historical market proxy",
            "evidence": [], "fundamentals": {}, "catalysts": {},
            "technical": {"return_20d": .10, "return_60d": .20, "above_sma_200": True},
            "risk": {"annualized_volatility": .25, "max_drawdown": -.15,
                     "beta": 1.1, "average_dollar_volume": 100_000_000},
        }

    def test_proxy_acceptance_does_not_relax_live_research_contract(self):
        now = datetime(2026, 1, 2, 21, tzinfo=timezone.utc)
        result = HistoricalMarketProxyPipeline().screen_candidates([self.packet()], None, now)
        self.assertEqual(result["ranked_candidates"][0]["research_mode"], "historical_market_proxy_v1")
        with self.assertRaises(ResearchInputError):
            ResearchPortfolioPipeline().screen_candidates([self.packet()], None, now)


if __name__ == "__main__":
    unittest.main()
