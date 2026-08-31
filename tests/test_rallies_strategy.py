"""
Unit tests for the Rallies ChatGPT Portfolio Strategy Engine.
"""

import unittest
from agent.compliance import ComplianceEngine
from agent.market_analyzer import MarketAnalyzer
from agent.rallies_strategy import RalliesChatGPTStrategy
from config import DEFAULT_CONFIG


class TestRalliesStrategy(unittest.TestCase):

    def setUp(self):
        self.compliance = ComplianceEngine()
        self.analyzer = MarketAnalyzer()
        self.strategy = RalliesChatGPTStrategy(
            config=DEFAULT_CONFIG.strategy,
            compliance=self.compliance,
            analyzer=self.analyzer,
        )

    def test_allocation_generation(self):
        """Test target allocation generation and verify SNOW is absent."""
        current_holdings = {"GOOGL": 50, "JPM": 30}
        current_prices = {"GOOGL": 180.0, "JPM": 210.0}
        total_equity = 100000.0
        cash = 84700.0

        res = self.strategy.generate_target_allocation(
            current_holdings=current_holdings,
            current_prices=current_prices,
            portfolio_cash=cash,
            portfolio_total_value=total_equity,
        )

        self.assertNotIn("SNOW", res.target_weights)
        self.assertIn("CASH", res.target_weights)
        self.assertGreaterEqual(res.target_weights["CASH"], 0.05)
        self.assertAlmostEqual(sum(res.target_weights.values()), 1.0, places=3)
        self.assertGreater(len(res.scorecards), 0)

        # Check proposal parameters
        for p in res.proposals:
            self.assertNotEqual(p.ticker, "SNOW")
            self.assertGreater(p.estimated_price, 0)
            self.assertGreater(p.quantity, 0)
            self.assertGreater(p.take_profit, p.stop_loss)


if __name__ == "__main__":
    unittest.main()
