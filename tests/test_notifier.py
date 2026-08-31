"""
Unit tests for the Text Notification and Confirmation Engine.
"""

import unittest
from agent.notifier import TextNotifier
from agent.rallies_strategy import TradeProposal
from config import NotifierConfig


class TestTextNotifier(unittest.TestCase):

    def setUp(self):
        self.config = NotifierConfig(
            primary_channel="cli",
            phone_number="+15551234567",
            confirmation_timeout_seconds=5,
            auto_approve_dry_run=True,
        )
        self.notifier = TextNotifier(self.config)

    def test_format_proposal_message(self):
        """Verify formatted SMS / iMessage trade proposal includes all risk & thesis parameters."""
        proposal = TradeProposal(
            ticker="CRDO",
            action="BUY",
            quantity=30,
            estimated_price=82.50,
            total_cost=2475.0,
            current_weight=0.0,
            target_weight=0.08,
            weight_delta=0.08,
            strategy_bucket="AI_INFRASTRUCTURE",
            thesis="High-speed optical breakout above 20-day EMA.",
            stop_loss=76.20,
            take_profit=98.00,
            risk_reward_ratio=2.5,
        )

        msg = self.notifier.format_proposal_message(proposal, portfolio_equity=100000.0)
        self.assertIn("CRDO", msg)
        self.assertIn("BUY 30 shares", msg)
        self.assertIn("$82.50", msg)
        self.assertIn("$2,475.00", msg)
        self.assertIn("Stop-Loss:   $76.20", msg)
        self.assertIn("Take-Profit: $98.00", msg)
        self.assertIn("PASSED (SNOW strict exclusion active)", msg)
        self.assertIn("Reply 'CONFIRM' or 'YES'", msg)

    def test_auto_approve_dry_run(self):
        """Verify non-interactive / dry-run confirmation passes."""
        proposal = TradeProposal(
            ticker="NBIS",
            action="BUY",
            quantity=50,
            estimated_price=35.0,
            total_cost=1750.0,
            current_weight=0.0,
            target_weight=0.05,
            weight_delta=0.05,
            strategy_bucket="AI_INFRASTRUCTURE",
            thesis="AI cloud infrastructure momentum rank 92.",
            stop_loss=31.50,
            take_profit=44.00,
            risk_reward_ratio=2.6,
        )
        decision = self.notifier.request_trade_confirmation(proposal, interactive=False)
        self.assertTrue(decision.approved)
        self.assertFalse(decision.timed_out)


if __name__ == "__main__":
    unittest.main()
