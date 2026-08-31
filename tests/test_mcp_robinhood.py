"""
Unit tests for Robinhood MCP Client and Safety Execution Guards.
"""

import unittest
from agent.compliance import ComplianceEngine, ComplianceViolationError
from agent.mcp_robinhood import LiveBrokerUnavailableError, RobinhoodMCPClient
from config import RobinhoodMCPConfig, DEFAULT_CONFIG


class TestRobinhoodMCP(unittest.TestCase):

    def setUp(self):
        self.compliance = ComplianceEngine()
        self.config = RobinhoodMCPConfig(use_mock=True)
        self.client = RobinhoodMCPClient(config=self.config, compliance=self.compliance, initial_cash=50000.0)

    def test_account_and_positions_initial_state(self):
        """Verify initial mock balances."""
        account = self.client.get_account_summary()
        self.assertEqual(account.cash_balance, 50000.0)
        self.assertEqual(account.portfolio_equity, 50000.0)
        self.assertEqual(len(self.client.get_positions()), 0)

    def test_unconfirmed_order_rejected(self):
        """Verify order fails if human confirmation was not provided."""
        res = self.client.execute_order(
            ticker="CRDO",
            action="BUY",
            quantity=10,
            limit_price=80.0,
            user_confirmed=False,  # Unconfirmed!
        )
        self.assertEqual(res.status, "REJECTED")
        self.assertIn("HUMAN_CONFIRMATION_REQUIRED", res.rejection_reason)

    def test_restricted_security_snow_rejected(self):
        """Verify SNOW is rejected by compliance check even if marked confirmed."""
        res = self.client.execute_order(
            ticker="SNOW",
            action="BUY",
            quantity=10,
            limit_price=130.0,
            user_confirmed=True,
        )
        self.assertEqual(res.status, "REJECTED")
        self.assertIn("COMPLIANCE RESTRICTION", res.rejection_reason)

    def test_successful_buy_and_sell_cycle(self):
        """Verify confirmed order execution in mock broker."""
        # 1. Execute BUY
        buy_res = self.client.execute_order(
            ticker="NVDA",
            action="BUY",
            quantity=20,
            limit_price=120.0,
            user_confirmed=True,
        )
        self.assertEqual(buy_res.status, "FILLED")
        self.assertGreater(buy_res.executed_price, 0)

        # Check updated positions and cash
        positions = self.client.get_positions()
        self.assertEqual(len(positions), 1)
        self.assertEqual(positions[0].ticker, "NVDA")
        self.assertEqual(positions[0].quantity, 20)
        self.assertLess(self.client.get_account_summary().cash_balance, 50000.0)

        # 2. Execute SELL
        sell_res = self.client.execute_order(
            ticker="NVDA",
            action="SELL",
            quantity=20,
            limit_price=130.0,
            user_confirmed=True,
        )
        self.assertEqual(sell_res.status, "FILLED")
        self.assertEqual(len(self.client.get_positions()), 0)

    def test_live_mode_fails_closed_without_unofficial_broker_login(self):
        """A live call must never be fabricated when no broker result exists."""
        live_client = RobinhoodMCPClient(
            config=RobinhoodMCPConfig(use_mock=False),
            compliance=self.compliance,
        )
        with self.assertRaises(LiveBrokerUnavailableError):
            live_client.get_account_summary()


if __name__ == "__main__":
    unittest.main()
