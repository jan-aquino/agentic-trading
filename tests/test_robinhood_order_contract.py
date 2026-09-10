"""Parity tests for the shared Robinhood equity-order contract."""

import unittest

from agent.robinhood_order_contract import OrderContractError, select_cent_limit, validate_equity_order


class TestRobinhoodOrderContract(unittest.TestCase):
    def assert_review_and_place_reject(self, order):
        with self.assertRaises(OrderContractError):
            validate_equity_order(order)
        with self.assertRaises(OrderContractError):
            validate_equity_order({**order, "idempotency_key": "reject-key"}, require_idempotency=True)

    def assert_review_and_place_accept(self, order, key):
        review = validate_equity_order(order)
        placement = validate_equity_order(
            {**order, "idempotency_key": key}, require_idempotency=True
        )
        self.assertEqual(review.symbol, placement.symbol)
        self.assertEqual(placement.idempotency_key, key)

    def test_fractional_limit_rejected_by_review_and_placement(self):
        self.assert_review_and_place_reject({
            "symbol": "NVDA", "action": "buy", "quantity": .5,
            "order_type": "limit", "price": 227.33, "market_hours": "regular_hours",
        })

    def test_whole_limit_accepted_by_review_and_placement(self):
        self.assert_review_and_place_accept({
            "symbol": "NVDA", "action": "buy", "quantity": 1,
            "order_type": "limit", "price": 227.33, "market_hours": "regular_hours",
        }, "whole-limit")

    def test_fractional_market_accepted_during_regular_hours(self):
        self.assert_review_and_place_accept({
            "symbol": "NVDA", "action": "buy", "quantity": .25,
            "order_type": "market", "reference_price": 227.33,
            "market_hours": "regular_hours",
        }, "fractional-market")

    def test_dollar_market_accepted_during_regular_hours(self):
        self.assert_review_and_place_accept({
            "symbol": "NVDA", "action": "buy", "dollar_amount": 100,
            "order_type": "market", "reference_price": 227.33,
            "market_hours": "regular_hours",
        }, "dollar-market")

    def test_dollar_limit_rejected(self):
        self.assert_review_and_place_reject({
            "symbol": "NVDA", "action": "buy", "dollar_amount": 100,
            "order_type": "limit", "price": 227.33, "market_hours": "regular_hours",
        })

    def test_subpenny_limit_above_one_rejected(self):
        self.assert_review_and_place_reject({
            "symbol": "NVDA", "action": "buy", "quantity": 1,
            "order_type": "limit", "price": 227.685, "market_hours": "regular_hours",
        })

    def test_fractional_outside_regular_hours_rejected(self):
        self.assert_review_and_place_reject({
            "symbol": "NVDA", "action": "buy", "quantity": .25,
            "order_type": "market", "reference_price": 227.33,
            "market_hours": "extended_hours",
        })

    def test_cent_price_selection(self):
        for raw, expected in [(227.685, 227.69), (270.425, 270.43), (129.855, 129.86), (227.33, 227.33)]:
            self.assertEqual(select_cent_limit(raw, "buy"), expected)
        self.assertEqual(select_cent_limit(227.685, "sell"), 227.68)

    def test_placement_requires_a_persisted_idempotency_key(self):
        order = {
            "symbol": "NVDA", "action": "buy", "dollar_amount": 100,
            "order_type": "market", "reference_price": 227.33,
            "market_hours": "regular_hours",
        }
        with self.assertRaisesRegex(OrderContractError, "idempotency_key"):
            validate_equity_order(order, require_idempotency=True)
        first = validate_equity_order(
            {**order, "idempotency_key": "same-logical-order"}, require_idempotency=True
        )
        retry = validate_equity_order(
            {**order, "idempotency_key": "same-logical-order"}, require_idempotency=True
        )
        self.assertEqual(first.as_dict(), retry.as_dict())


if __name__ == "__main__":
    unittest.main()
