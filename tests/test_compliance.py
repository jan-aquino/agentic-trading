"""
Unit tests for the Compliance and Security Exclusion Engine.
Validates strict exclusion of Snowflake (SNOW) across screening, allocation, and execution.
"""

import unittest
from agent.compliance import ComplianceEngine, ComplianceViolationError
from config import ComplianceConfig


class TestComplianceEngine(unittest.TestCase):

    def setUp(self):
        self.config = ComplianceConfig(
            restricted_tickers=["SNOW"],
            max_position_weight=0.25,
            min_cash_buffer=0.05,
            enable_strict_mode=True,
        )
        self.compliance = ComplianceEngine(self.config)

    def test_is_restricted(self):
        """Verify SNOW is recognized as restricted in any casing."""
        self.assertTrue(self.compliance.is_restricted("SNOW"))
        self.assertTrue(self.compliance.is_restricted("snow"))
        self.assertTrue(self.compliance.is_restricted(" SNOW "))
        self.assertFalse(self.compliance.is_restricted("NVDA"))
        self.assertFalse(self.compliance.is_restricted("CRDO"))
        self.assertFalse(self.compliance.is_restricted("GOOGL"))

    def test_filter_universe(self):
        """Verify filter_universe strips SNOW cleanly."""
        universe = ["CRDO", "NBIS", "SNOW", "GOOGL", "snow", "NVDA"]
        filtered = self.compliance.filter_universe(universe)
        self.assertNotIn("SNOW", filtered)
        self.assertNotIn("snow", filtered)
        self.assertEqual(filtered, ["CRDO", "NBIS", "GOOGL", "NVDA"])

    def test_sanitize_target_weights_redistribution(self):
        """Verify SNOW weight is cleanly stripped and redistributed to approved assets."""
        raw_weights = {
            "CRDO": 0.20,
            "NBIS": 0.20,
            "SNOW": 0.20,  # Restricted
            "GOOGL": 0.20,
            "CASH": 0.20,
        }
        sanitized = self.compliance.sanitize_target_weights(raw_weights)
        self.assertNotIn("SNOW", sanitized)
        self.assertAlmostEqual(sum(sanitized.values()), 1.0, places=4)
        # CRDO, NBIS, GOOGL should have received proportional share of the 20% SNOW budget
        self.assertGreater(sanitized["CRDO"], 0.20)
        self.assertGreater(sanitized["NBIS"], 0.20)
        self.assertGreater(sanitized["GOOGL"], 0.20)

    def test_validate_order_blocks_snow(self):
        """Verify order validation strictly raises ComplianceViolationError on SNOW."""
        with self.assertRaises(ComplianceViolationError):
            self.compliance.validate_order(
                ticker="SNOW",
                action="BUY",
                quantity=10,
                price=130.0,
                portfolio_value=100000.0,
            )

        with self.assertRaises(ComplianceViolationError):
            self.compliance.validate_order(
                ticker="snow",
                action="SELL",
                quantity=5,
                price=130.0,
                portfolio_value=100000.0,
            )

    def test_validate_order_concentration_limit(self):
        """Verify orders exceeding 25% single-stock concentration are flagged."""
        self.compliance.config.enable_strict_mode = False
        res = self.compliance.validate_order(
            ticker="CRDO",
            action="BUY",
            quantity=500,
            price=100.0,  # $50,000 order on $100,000 portfolio (50% > 25%)
            portfolio_value=100000.0,
            current_holding_value=0.0,
        )
        self.assertFalse(res.is_compliant)
        self.assertIn("CONCENTRATION LIMIT", res.reasons[0])


if __name__ == "__main__":
    unittest.main()
