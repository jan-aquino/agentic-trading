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


SECTORS = {
    "AMD": "technology", "AMZN": "consumer_discretionary", "APH": "technology",
    "AVGO": "technology", "CI": "healthcare", "CRDO": "technology",
    "GOOGL": "communication_services", "JPM": "financials", "LDOS": "industrials",
    "LLY": "healthcare", "MRVL": "technology", "MSFT": "technology",
    "NBIS": "technology", "NVDA": "technology", "PGR": "financials",
    "UNH": "healthcare", "V": "financials",
}


class HistoricalMarketProxyPipeline(ResearchPortfolioPipeline):
    """Use the real constructor with an explicitly reduced historical score."""

    research_mode = "historical_market_proxy_v1"

    def _score_candidate(
        self, raw: Mapping[str, Any], now: datetime, mandate: InvestmentMandate
    ) -> Dict[str, Any]:
        if raw.get("research_mode") != self.research_mode:
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
            "factor_scores": {
                "momentum": round(momentum, 2),
                "risk": round(risk, 2),
                "liquidity": round(liquidity, 2),
            },
            "composite_score": round(composite, 2),
            "confidence": 1.0,
            "adjusted_score": round(adjusted, 2),
            "thesis": raw["thesis"],
            "evidence": raw["evidence"],
            "research_as_of": raw["research_as_of"],
            "research_mode": self.research_mode,
            "unavailable_factors": ["quality", "growth", "valuation", "catalyst"],
        }


class HistoricalDiscoveryAgent:
    """Build walk-forward proxy packets from data visible at one decision time."""

    def __init__(self, discovery_limit: int = 15):
        self.discovery_limit = discovery_limit

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
            packets.append({
                "symbol": symbol,
                "asset_type": "equity",
                "sector": SECTORS.get(symbol, "unknown"),
                "tradable": True,
                "fractional_tradable": True,
                "leveraged_or_inverse": False,
                "price": float(close.iloc[-1]),
                "research_as_of": observed_at,
                "research_mode": HistoricalMarketProxyPipeline.research_mode,
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
            })
        held_symbols = held_symbols or set()
        selected = sorted(packets, key=lambda item: item["_discovery_score"], reverse=True)[:self.discovery_limit]
        selected_symbols = {item["symbol"] for item in selected}
        selected.extend(item for item in packets if item["symbol"] in held_symbols - selected_symbols)
        for item in selected:
            item.pop("_discovery_score", None)
        return selected
