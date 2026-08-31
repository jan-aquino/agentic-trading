"""
Unit tests for the Backtesting Engine and Benchmark Analytics.
"""

import unittest
from agent.backtester import Backtester
from config import DEFAULT_CONFIG


class TestBacktester(unittest.TestCase):

    def setUp(self):
        self.backtester = Backtester(slippage_bps=5.0)

    def test_backtest_run_and_metrics(self):
        """Verify backtest executes, computes metrics, and strictly excludes SNOW."""
        result = self.backtester.run(
            start_date="2023-01-01",
            end_date="2024-06-30",
            initial_capital=100000.0,
            rebalance_interval_days=7,
            exclude_snow=True,
        )

        m = result.metrics
        self.assertEqual(m.initial_capital, 100000.0)
        self.assertGreater(m.final_value, 50000.0)
        self.assertGreater(len(result.equity_curve), 50)
        self.assertIn("Portfolio_Value", result.equity_curve.columns)
        self.assertIn("SPY_Value", result.equity_curve.columns)
        self.assertIn("QQQ_Value", result.equity_curve.columns)

        # Verify no trade in trades_log was on SNOW
        for t in result.trades_log:
            self.assertNotEqual(t["ticker"], "SNOW")

        # Verify final holdings do not contain SNOW
        self.assertNotIn("SNOW", result.final_holdings)


if __name__ == "__main__":
    unittest.main()
