"""Point-in-time guarantees for SEC-derived historical research."""

import unittest
from datetime import date

from agent.historical_fundamentals import SecEdgarFundamentalsProvider


class TestSecEdgarFundamentals(unittest.TestCase):
    def test_future_filing_is_not_visible(self):
        facts = {"facts": {"us-gaap": {"Revenues": {"units": {"USD": [
            {"end": "2022-12-31", "filed": "2023-02-15", "form": "10-K", "fp": "FY", "accn": "old", "val": 100},
            {"end": "2023-12-31", "filed": "2024-02-15", "form": "10-K", "fp": "FY", "accn": "known", "val": 120},
            {"end": "2024-12-31", "filed": "2025-02-15", "form": "10-K", "fp": "FY", "accn": "future", "val": 500},
        ]}}}}}
        rows = SecEdgarFundamentalsProvider._annual_series(
            facts, ("Revenues",), date(2024, 9, 1)
        )
        self.assertEqual([row["accn"] for row in rows], ["old", "known"])

    def test_latest_known_amendment_wins_for_same_period(self):
        facts = {"facts": {"us-gaap": {"Revenues": {"units": {"USD": [
            {"end": "2023-12-31", "filed": "2024-02-01", "form": "10-K", "fp": "FY", "accn": "original", "val": 100},
            {"end": "2023-12-31", "filed": "2024-03-01", "form": "10-K/A", "fp": "FY", "accn": "amended", "val": 101},
        ]}}}}}
        rows = SecEdgarFundamentalsProvider._annual_series(
            facts, ("Revenues",), date(2024, 4, 1)
        )
        self.assertEqual(rows[-1]["value"], 101)
        self.assertEqual(rows[-1]["accn"], "amended")


if __name__ == "__main__":
    unittest.main()
