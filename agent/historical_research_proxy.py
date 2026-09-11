"""Point-in-time market-data discovery for proposal-pipeline backtests.

This module is deliberately separate from the live research contract. It never
invents historical fundamentals or catalysts; it scores only observable price,
volume, trend, and risk fields and labels every result as a proxy.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Mapping, Optional

import numpy as np
import pandas as pd

from agent.research_portfolio_pipeline import (
    InvestmentMandate,
    ResearchInputError,
    ResearchPortfolioPipeline,
    _clamp,
    _scale,
)
from agent.historical_fundamentals import HistoricalResearchProvider


SECTORS = {
    "AMD": "technology", "AMZN": "consumer_discretionary", "APH": "technology",
    "AVGO": "technology", "CI": "healthcare", "CRDO": "technology",
    "GOOGL": "communication_services", "JPM": "financials", "LDOS": "industrials",
    "LLY": "healthcare", "MRVL": "technology", "MSFT": "technology",
    "NBIS": "technology", "NVDA": "technology", "PGR": "financials",
    "UNH": "healthcare", "V": "financials",
}

CORE_ETF_SECTORS = {"SPY": "broad_market", "QQQ": "growth_index", "IWM": "small_cap_index"}


class HistoricalMarketProxyPipeline(ResearchPortfolioPipeline):
    """Use the real constructor with an explicitly reduced historical score."""

    research_mode = "historical_market_proxy_v1"

    def __init__(
        self,
        *args,
        core_targets: Optional[Mapping[str, float]] = None,
        minimum_holding_days: int = 42,
        maximum_one_way_turnover: float = .25,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.core_targets = dict(core_targets or {})
        self.minimum_holding_days = minimum_holding_days
        self.maximum_one_way_turnover = maximum_one_way_turnover
        self.holding_days: Dict[str, int] = {}

    def set_portfolio_context(self, holding_days: Mapping[str, int]) -> None:
        self.holding_days = dict(holding_days)

    def adjust_target_weights(self, target_weights, ranked, positions, portfolio_equity, mandate, now):
        adjusted = dict(target_weights)
        prices = {item["symbol"]: float(item["price"]) for item in ranked}
        current = {
            symbol: quantity * prices[symbol] / portfolio_equity
            for symbol, quantity in positions.items()
            if quantity > 0 and symbol in prices and portfolio_equity > 0
        }

        # A diversified ETF sleeve is a portfolio construction rule, independent
        # of individual-company fundamental ranks. Reserve its weight first and
        # rescale the scored stock sleeve into the remaining invested budget.
        adjusted.pop("CASH", None)
        core_symbols = {symbol for symbol in self.core_targets if symbol in prices}
        active_slots = max(0, mandate.maximum_positions - len(core_symbols))
        allowed_active = {
            item["symbol"] for item in ranked
            if item["eligible"] and item["symbol"] not in core_symbols
        }
        allowed_active = set(list(
            item["symbol"] for item in ranked
            if item["symbol"] in allowed_active
        )[:active_slots])
        adjusted = {
            symbol: weight for symbol, weight in adjusted.items()
            if symbol in core_symbols or symbol in allowed_active
        }
        core_budget = sum(
            min(float(weight), mandate.maximum_position_weight)
            for symbol, weight in self.core_targets.items() if symbol in prices
        )
        active_budget = max(0.0, 1.0 - mandate.target_cash_weight - core_budget)
        active_symbols = [symbol for symbol in adjusted if symbol not in self.core_targets]
        active_total = sum(adjusted[symbol] for symbol in active_symbols)
        if active_total > 0:
            for symbol in active_symbols:
                adjusted[symbol] *= active_budget / active_total
        for symbol, requested in self.core_targets.items():
            if symbol in prices:
                adjusted[symbol] = min(float(requested), mandate.maximum_position_weight)

        # Do not force a young holding out merely because its rank moved around.
        for symbol, weight in current.items():
            if self.holding_days.get(symbol, self.minimum_holding_days) < self.minimum_holding_days:
                adjusted[symbol] = max(adjusted.get(symbol, 0.0), weight)

        non_cash = sum(value for symbol, value in adjusted.items() if symbol != "CASH")
        if non_cash > 1.0 - mandate.target_cash_weight:
            scale = (1.0 - mandate.target_cash_weight) / non_cash
            adjusted = {symbol: value * scale for symbol, value in adjusted.items() if symbol != "CASH"}

        # Limit one-way turnover by blending the newly scored target toward the
        # current portfolio. This preserves rankings while avoiding wholesale
        # monthly replacement.
        symbols = set(current).union(adjusted)
        turnover = .5 * sum(abs(adjusted.get(symbol, 0.0) - current.get(symbol, 0.0)) for symbol in symbols)
        if turnover > self.maximum_one_way_turnover > 0:
            blend = self.maximum_one_way_turnover / turnover
            adjusted = {
                symbol: current.get(symbol, 0.0) + blend * (adjusted.get(symbol, 0.0) - current.get(symbol, 0.0))
                for symbol in symbols
            }
        # Next-open construction uses a 19% operating cap under the 20% hard
        # mandate. Compliance takes precedence over holding-period hysteresis.
        adjusted = {symbol: min(weight, .19) for symbol, weight in adjusted.items()}
        adjusted["CASH"] = max(mandate.target_cash_weight, 1.0 - sum(adjusted.values()))
        return adjusted

    def _score_candidate(
        self, raw: Mapping[str, Any], now: datetime, mandate: InvestmentMandate
    ) -> Dict[str, Any]:
        if raw.get("research_mode") not in {self.research_mode, "historical_point_in_time_v1"}:
            raise ResearchInputError("historical proxy candidate has an invalid research_mode")
        symbol = str(raw["symbol"]).upper()
        rejection_reasons = []
        if self.compliance.is_restricted(symbol):
            return {"symbol": symbol, "eligible": False, "rejection_reasons": ["RESTRICTED_SECURITY"]}
        if raw.get("leveraged_or_inverse") is not False:
            rejection_reasons.append("LEVERAGED_OR_INVERSE_PRODUCT")
        if raw.get("tradable") is not True:
            rejection_reasons.append("NOT_TRADABLE")
        if raw.get("asset_type") not in mandate.allowed_asset_types:
            rejection_reasons.append("ASSET_TYPE_NOT_ALLOWED")

        technical = raw["technical"]
        risk_fields = raw["risk"]
        momentum = (
            _scale(float(technical["return_20d"]), -.20, .25) * .45
            + _scale(float(technical["return_60d"]), -.30, .50) * .40
            + (100.0 if technical["above_sma_200"] else 0.0) * .15
        )
        risk = (
            _scale(float(risk_fields["annualized_volatility"]), .10, .90, inverse=True) * .40
            + _scale(abs(float(risk_fields["max_drawdown"])), .05, .65, inverse=True) * .35
            + _scale(float(risk_fields["beta"]), .5, 2.0, inverse=True) * .25
        )
        liquidity = _scale(float(risk_fields["average_dollar_volume"]), 5_000_000, 500_000_000)
        factors = {"momentum": momentum, "risk": risk, "liquidity": liquidity}
        unavailable = ["quality", "growth", "valuation", "catalyst"]
        fundamentals = raw.get("historical_fundamentals")
        if fundamentals:
            quality = (
                _scale(float(fundamentals["free_cash_flow_margin"]), -.10, .35) * .55
                + _scale(float(fundamentals["return_on_equity"]), -.10, .40) * .45
            )
            growth = (
                _scale(float(fundamentals["revenue_growth"]), -.20, .50) * .50
                + _scale(float(fundamentals["earnings_growth"]), -.30, .60) * .50
            )
            trailing_pe = float(fundamentals["trailing_pe"])
            trailing_peg = float(fundamentals["trailing_peg"])
            valuation = (
                _scale(trailing_pe if trailing_pe > 0 else 1000, 8, 60, inverse=True) * .60
                + _scale(trailing_peg if trailing_peg > 0 else 100, .5, 4, inverse=True) * .40
            )
            catalyst = (
                float(fundamentals["filing_recency_score"]) * .60
                + _scale(float(fundamentals["filing_sentiment"]), -1, 1) * .40
            )
            factors.update({"quality": quality, "growth": growth,
                            "valuation": valuation, "catalyst": catalyst})
            composite = (
                quality * .20 + growth * .20 + valuation * .15 + momentum * .20
                + catalyst * .10 + risk * .15
            )
            unavailable = []
        else:
            composite = momentum * .55 + risk * .35 + liquidity * .10
        conviction = float(raw["agent_conviction"])
        adjusted = composite * (.90 + .10 * conviction / 100.0)
        if float(risk_fields["average_dollar_volume"]) < mandate.minimum_average_dollar_volume:
            rejection_reasons.append("INSUFFICIENT_LIQUIDITY")
        if float(risk_fields["annualized_volatility"]) > mandate.maximum_annualized_volatility:
            rejection_reasons.append("EXCESSIVE_VOLATILITY")
        if adjusted < mandate.minimum_candidate_score:
            rejection_reasons.append("BELOW_MINIMUM_SCORE")

        return {
            "symbol": symbol,
            "asset_type": raw["asset_type"],
            "sector": raw["sector"],
            "price": round(float(raw["price"]), 6),
            "fractional_tradable": bool(raw["fractional_tradable"]),
            "eligible": not rejection_reasons,
            "rejection_reasons": rejection_reasons,
            "factor_scores": {name: round(value, 2) for name, value in factors.items()},
            "composite_score": round(composite, 2),
            "confidence": 1.0,
            "adjusted_score": round(adjusted, 2),
            "thesis": raw["thesis"],
            "evidence": raw["evidence"],
            "research_as_of": raw["research_as_of"],
            "research_mode": raw["research_mode"],
            "unavailable_factors": unavailable,
        }


class HistoricalDiscoveryAgent:
    """Build walk-forward proxy packets from data visible at one decision time."""

    def __init__(
        self,
        discovery_limit: int = 15,
        fundamentals_provider: Optional[HistoricalResearchProvider] = None,
        always_include: Optional[set[str]] = None,
    ):
        self.discovery_limit = discovery_limit
        self.fundamentals_provider = fundamentals_provider
        self.always_include = set(always_include or set())

    def discover(
        self,
        price_data: Mapping[str, pd.DataFrame],
        as_of: pd.Timestamp,
        observed_at: str,
        held_symbols: Optional[set[str]] = None,
    ) -> list[Dict[str, Any]]:
        spy = price_data["SPY"].loc[:as_of]
        packets = []
        for symbol, frame in price_data.items():
            if symbol in {"SPY", "QQQ", "SNOW"}:
                continue
            history = frame.loc[:as_of].dropna()
            if len(history) < 61:
                continue
            close = history["Close"]
            returns = close.pct_change().dropna()
            recent = returns.tail(60)
            annualized_volatility = float(recent.std() * np.sqrt(252))
            rolling_peak = close.tail(252).cummax()
            max_drawdown = float(((close.tail(252) - rolling_peak) / rolling_peak).min())
            aligned = pd.concat([returns.tail(252), spy["Close"].pct_change().dropna().tail(252)], axis=1).dropna()
            beta = 1.0
            if len(aligned) > 20 and aligned.iloc[:, 1].var() > 0:
                beta = float(aligned.cov().iloc[0, 1] / aligned.iloc[:, 1].var())
            adv = float((history["Close"] * history["Volume"]).tail(20).mean())
            return_20d = float(close.iloc[-1] / close.iloc[-21] - 1)
            return_60d = float(close.iloc[-1] / close.iloc[-61] - 1)
            above_sma = bool(close.iloc[-1] > close.tail(min(200, len(close))).mean())
            trend_strength = _clamp(
                50 + return_20d * 120 + return_60d * 70
                - max(0.0, annualized_volatility - .30) * 35
            )
            fundamental_snapshot = (
                self.fundamentals_provider.snapshot(symbol, as_of.date(), float(close.iloc[-1]))
                if self.fundamentals_provider else None
            )
            packet = {
                "symbol": symbol,
                "asset_type": "etf" if symbol in CORE_ETF_SECTORS else "equity",
                "sector": CORE_ETF_SECTORS.get(symbol, SECTORS.get(symbol, "unknown")),
                "tradable": True,
                "fractional_tradable": True,
                "leveraged_or_inverse": False,
                "price": float(close.iloc[-1]),
                "research_as_of": observed_at,
                "research_mode": (
                    "historical_point_in_time_v1" if fundamental_snapshot
                    else HistoricalMarketProxyPipeline.research_mode
                ),
                "agent_conviction": round(trend_strength, 2),
                "thesis": (
                    f"Historical market proxy: 20-day return {return_20d:.1%}, "
                    f"60-day return {return_60d:.1%}, volatility {annualized_volatility:.1%}."
                ),
                "evidence": [
                    {"title": f"{symbol} point-in-time OHLCV", "url": f"dataset://market/{symbol}/daily", "observed_at": observed_at},
                    {"title": f"{symbol} derived proxy indicators", "url": f"dataset://proxy/{symbol}/historical_market_proxy_v1", "observed_at": observed_at},
                ],
                "fundamentals": {},
                "catalysts": {},
                "technical": {"return_20d": return_20d, "return_60d": return_60d, "above_sma_200": above_sma},
                "risk": {
                    "annualized_volatility": annualized_volatility,
                    "max_drawdown": max_drawdown,
                    "beta": beta,
                    "average_dollar_volume": adv,
                },
                "_discovery_score": trend_strength,
            }
            if fundamental_snapshot:
                packet["historical_fundamentals"] = fundamental_snapshot.to_dict()
                packet["evidence"].append({
                    "title": f"{symbol} SEC filing {fundamental_snapshot.accession_number}",
                    "url": fundamental_snapshot.filing_url,
                    "observed_at": f"{fundamental_snapshot.filed_at}T21:00:00+00:00",
                })
                packet["thesis"] = (
                    f"Point-in-time SEC and market synthesis: revenue growth "
                    f"{fundamental_snapshot.revenue_growth:.1%}, earnings growth "
                    f"{fundamental_snapshot.earnings_growth:.1%}, 60-day return {return_60d:.1%}."
                )
                # Discovery itself now includes fundamental quality rather than
                # selecting solely on recent price strength.
                packet["_discovery_score"] = _clamp(
                    trend_strength * .50
                    + _scale(fundamental_snapshot.revenue_growth, -.20, .50) * .25
                    + _scale(fundamental_snapshot.free_cash_flow_margin, -.10, .35) * .25
                )
            packets.append(packet)
        held_symbols = (held_symbols or set()).union(self.always_include)
        selected = sorted(packets, key=lambda item: item["_discovery_score"], reverse=True)[:self.discovery_limit]
        selected_symbols = {item["symbol"] for item in selected}
        selected.extend(item for item in packets if item["symbol"] in held_symbols - selected_symbols)
        for item in selected:
            item.pop("_discovery_score", None)
        return selected
