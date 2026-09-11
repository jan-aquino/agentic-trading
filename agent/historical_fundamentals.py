"""Point-in-time historical fundamentals providers for backtesting.

SEC facts are filtered by their public filing date. A value filed after the
simulated decision date is never visible to the strategy.
"""

from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any, Dict, Optional, Protocol


@dataclass(frozen=True)
class FundamentalSnapshot:
    symbol: str
    as_of: str
    revenue_growth: float
    earnings_growth: float
    free_cash_flow_margin: float
    return_on_equity: float
    trailing_pe: float
    trailing_peg: float
    filing_recency_score: float
    filing_sentiment: float
    filed_at: str
    accession_number: str
    filing_url: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class HistoricalResearchProvider(Protocol):
    def snapshot(self, symbol: str, as_of: date, price: float) -> Optional[FundamentalSnapshot]: ...


class SecEdgarFundamentalsProvider:
    """Derive annual point-in-time factors from SEC Company Facts."""

    TAGS = {
        "revenue": ("RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet"),
        "income": ("NetIncomeLoss", "ProfitLoss"),
        "operating_cash": ("NetCashProvidedByUsedInOperatingActivities",),
        "capex": ("PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsForAdditionsToPropertyPlantAndEquipment"),
        "equity": ("StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"),
        "eps": ("EarningsPerShareDiluted", "EarningsPerShareBasic"),
    }

    def __init__(self, cache_dir: Optional[Path] = None, user_agent: Optional[str] = None):
        self.cache_dir = Path(cache_dir or "data/cache/sec_companyfacts")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.user_agent = user_agent or os.getenv(
            "SEC_USER_AGENT", "AgenticTrading research contact@example.com"
        )
        self._tickers: Optional[Dict[str, int]] = None
        self._facts: Dict[str, Dict[str, Any]] = {}

    def snapshot(self, symbol: str, as_of: date, price: float) -> Optional[FundamentalSnapshot]:
        symbol = symbol.upper()
        cik = self._ticker_map().get(symbol)
        if cik is None:
            return None
        facts = self._company_facts(symbol, cik)
        series = {name: self._annual_series(facts, tags, as_of) for name, tags in self.TAGS.items()}
        if any(len(series[name]) < 2 for name in ("revenue", "income")):
            return None
        if any(not series[name] for name in ("operating_cash", "capex", "equity", "eps")):
            return None
        revenue, prior_revenue = series["revenue"][-1], series["revenue"][-2]
        income, prior_income = series["income"][-1], series["income"][-2]
        ocf, capex, equity, eps = (series[name][-1] for name in ("operating_cash", "capex", "equity", "eps"))
        if not all(item["value"] is not None for item in (revenue, prior_revenue, income, prior_income, ocf, capex, equity, eps)):
            return None
        revenue_growth = self._growth(revenue["value"], prior_revenue["value"])
        earnings_growth = self._growth(income["value"], prior_income["value"])
        fcf_margin = (ocf["value"] - abs(capex["value"])) / revenue["value"] if revenue["value"] else 0.0
        roe = income["value"] / equity["value"] if equity["value"] else 0.0
        trailing_pe = price / eps["value"] if eps["value"] > 0 else -1.0
        trailing_peg = trailing_pe / (earnings_growth * 100) if trailing_pe > 0 and earnings_growth > 0 else -1.0
        filed = max(item["filed"] for item in (revenue, income, ocf, equity, eps))
        days_since = max(0, (as_of - date.fromisoformat(filed)).days)
        accession = revenue["accn"]
        accession_compact = accession.replace("-", "")
        filing_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_compact}/{accession}-index.html"
        return FundamentalSnapshot(
            symbol=symbol, as_of=as_of.isoformat(), revenue_growth=revenue_growth,
            earnings_growth=earnings_growth, free_cash_flow_margin=fcf_margin,
            return_on_equity=roe, trailing_pe=trailing_pe, trailing_peg=trailing_peg,
            filing_recency_score=max(0.0, 100.0 - days_since / 3.65),
            filing_sentiment=max(-1.0, min(1.0, earnings_growth)), filed_at=filed,
            accession_number=accession, filing_url=filing_url,
        )

    @staticmethod
    def _growth(current: float, prior: float) -> float:
        return (current / abs(prior) - 1.0) if prior else 0.0

    def _ticker_map(self) -> Dict[str, int]:
        if self._tickers is None:
            raw = self._get_json("https://www.sec.gov/files/company_tickers.json", self.cache_dir / "company_tickers.json")
            self._tickers = {str(row["ticker"]).upper(): int(row["cik_str"]) for row in raw.values()}
        return self._tickers

    def _company_facts(self, symbol: str, cik: int) -> Dict[str, Any]:
        if symbol not in self._facts:
            path = self.cache_dir / f"{symbol}_{cik:010d}.json"
            self._facts[symbol] = self._get_json(
                f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json", path
            )
        return self._facts[symbol]

    def _get_json(self, url: str, cache_path: Path) -> Dict[str, Any]:
        if cache_path.exists():
            return json.loads(cache_path.read_text(encoding="utf-8"))
        request = urllib.request.Request(url, headers={"User-Agent": self.user_agent, "Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
        cache_path.write_text(json.dumps(data), encoding="utf-8")
        return data

    @staticmethod
    def _annual_series(facts: Dict[str, Any], tags: tuple[str, ...], as_of: date) -> list[Dict[str, Any]]:
        us_gaap = facts.get("facts", {}).get("us-gaap", {})
        records = []
        for tag in tags:
            concept = us_gaap.get(tag)
            if not concept:
                continue
            for unit_records in concept.get("units", {}).values():
                for row in unit_records:
                    if row.get("form") not in {"10-K", "10-K/A"} or row.get("fp") != "FY":
                        continue
                    if not row.get("filed") or date.fromisoformat(row["filed"]) > as_of:
                        continue
                    records.append({"end": row.get("end"), "filed": row["filed"],
                                    "accn": row.get("accn", ""), "value": row.get("val")})
            if records:
                break
        by_period: Dict[str, Dict[str, Any]] = {}
        for row in records:
            end = row.get("end")
            if end and (end not in by_period or row["filed"] > by_period[end]["filed"]):
                by_period[end] = row
        return sorted(by_period.values(), key=lambda row: row["end"])
