"""Walk-forward backtest through actual TradingAnalysisService plan generation."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from datetime import datetime, time, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

from agent.backtester import BacktestMetrics, Backtester
from agent.historical_research_proxy import HistoricalDiscoveryAgent, HistoricalMarketProxyPipeline
from agent.historical_fundamentals import HistoricalResearchProvider
from agent.market_analyzer import MarketAnalyzer
from agent.trading_analysis_service import FilePlanStore, TradingAnalysisService
from config import DEFAULT_CONFIG, SystemConfig


@dataclass
class ProposalBacktestResult:
    metrics: BacktestMetrics
    equity_curve: pd.DataFrame
    plan_log: list[Dict[str, Any]]
    trades_log: list[Dict[str, Any]]
    final_holdings: Dict[str, float]
    final_cash: float
    data_sources: Dict[str, str]


class ProposalPipelineBacktester:
    """Simulate discovery → immutable plan → next-open validation → fills."""

    def __init__(
        self,
        config: Optional[SystemConfig] = None,
        analyzer: Optional[MarketAnalyzer] = None,
        slippage_bps: float = 5.0,
        fundamentals_provider: Optional[HistoricalResearchProvider] = None,
        core_satellite: bool = True,
        minimum_holding_days: int = 42,
        maximum_one_way_turnover: float = .25,
    ):
        self.config = config or DEFAULT_CONFIG
        self.analyzer = analyzer or MarketAnalyzer(config=self.config.strategy)
        self.slippage_bps = slippage_bps
        self.fundamentals_provider = fundamentals_provider
        self.core_targets = {"SPY": .19, "QQQ": .19, "IWM": .10} if core_satellite else {}
        self.discovery = HistoricalDiscoveryAgent(
            fundamentals_provider=fundamentals_provider,
            always_include=set(self.core_targets),
        )
        self.minimum_holding_days = minimum_holding_days
        self.maximum_one_way_turnover = maximum_one_way_turnover

    def run(
        self,
        start_date: str,
        end_date: str,
        initial_capital: float,
        rebalance_interval_days: int = 21,
    ) -> ProposalBacktestResult:
        requested_start = pd.Timestamp(start_date)
        requested_end = pd.Timestamp(end_date)
        warmup_start = (requested_start - pd.Timedelta(days=370)).strftime("%Y-%m-%d")
        universe = sorted(set(
            self.config.strategy.ai_infra_universe
            + self.config.strategy.core_diversified_universe
            + ["SPY", "QQQ", "IWM", "SNOW"]
        ))
        price_data = {
            symbol: self.analyzer.fetch_ohlcv(symbol, warmup_start, end_date)
            for symbol in universe
        }
        dates = pd.DatetimeIndex(price_data["SPY"].index)
        dates = dates[(dates >= requested_start) & (dates <= requested_end)]
        if len(dates) < 2:
            raise ValueError("requested period requires at least two trading sessions")

        cash = float(initial_capital)
        holdings: Dict[str, float] = {}
        average_costs: Dict[str, float] = {}
        acquired_dates: Dict[str, pd.Timestamp] = {}
        plan_log: list[Dict[str, Any]] = []
        trades: list[Dict[str, Any]] = []
        equity_records = []
        mutable_clock = [datetime.combine(dates[0].date(), time(21), tzinfo=timezone.utc)]

        with tempfile.TemporaryDirectory() as plan_dir:
            pipeline = HistoricalMarketProxyPipeline(
                config=self.config, core_targets=self.core_targets,
                minimum_holding_days=self.minimum_holding_days,
                maximum_one_way_turnover=self.maximum_one_way_turnover,
            )
            service = TradingAnalysisService(
                config=self.config,
                store=FilePlanStore(Path(plan_dir)),
                pipeline=pipeline,
                clock=lambda: mutable_clock[0],
            )
            pending: Optional[Dict[str, Any]] = None
            last_decision: Optional[pd.Timestamp] = None

            for date_index, current_date in enumerate(dates):
                close_prices = {
                    symbol: price
                    for symbol, frame in price_data.items()
                    if (price := self._price_on_optional(frame, current_date, "Close")) is not None
                }

                if pending is not None:
                    mutable_clock[0] = datetime.combine(current_date.date(), time(14, 30), tzinfo=timezone.utc)
                    open_prices = {
                        symbol: self._price_on(price_data[symbol], current_date, "Open")
                        for symbol in {intent["symbol"] for intent in pending["order_intents"]}
                    }
                    open_equity = cash + sum(
                        quantity * self._price_on(price_data[symbol], current_date, "Open")
                        for symbol, quantity in holdings.items()
                    )
                    positions = [
                        {"symbol": symbol, "quantity": quantity,
                         "current_price": self._price_on(price_data[symbol], current_date, "Open")}
                        for symbol, quantity in holdings.items()
                    ]
                    validation = service.validate_trade_plan(
                        pending["plan_id"],
                        {"account_id": "historical-simulation", "portfolio_equity": open_equity,
                         "cash_balance": cash, "buying_power": cash},
                        positions,
                        [{"symbol": symbol, "price": price} for symbol, price in open_prices.items()],
                        mutable_clock[0].isoformat(),
                        market_session="regular_hours",
                    )
                    entry = next(item for item in plan_log if item["plan_id"] == pending["plan_id"])
                    entry["validation"] = validation
                    if validation["execution_ready"]:
                        self._execute(
                            validation["broker_review_intents"], open_prices, current_date,
                            holdings, average_costs, acquired_dates, trades, cash_box := [cash]
                        )
                        cash = cash_box[0]
                        entry["status"] = "SIMULATED_FILLED"
                    else:
                        entry["status"] = "VALIDATION_BLOCKED"
                    pending = None

                stock_value = sum(quantity * close_prices[symbol] for symbol, quantity in holdings.items())
                total_equity = cash + stock_value
                should_decide = (
                    date_index < len(dates) - 1
                    and pending is None
                    and (last_decision is None or (current_date - last_decision).days >= rebalance_interval_days)
                )
                if should_decide:
                    mutable_clock[0] = datetime.combine(current_date.date(), time(21), tzinfo=timezone.utc)
                    packets = self.discovery.discover(
                        price_data, current_date, mutable_clock[0].isoformat(), set(holdings)
                    )
                    positions = [
                        {"symbol": symbol, "quantity": quantity, "current_price": close_prices[symbol]}
                        for symbol, quantity in holdings.items()
                    ]
                    pipeline.set_portfolio_context({
                        symbol: max(0, (current_date - acquired_dates.get(symbol, current_date)).days)
                        for symbol in holdings
                    })
                    plan = service.generate_trade_plan(
                        {"account_id": "historical-simulation", "portfolio_equity": total_equity,
                         "cash_balance": cash, "buying_power": cash},
                        positions,
                        packets,
                        mutable_clock[0].isoformat(),
                        mandate={
                            "objective": "long_term_total_return", "risk_tolerance": "moderate",
                            "time_horizon_months": 36, "target_cash_weight": .10,
                            "maximum_position_weight": .20, "maximum_sector_weight": .35,
                            "maximum_positions": 10, "minimum_candidate_score": 60,
                            "minimum_trade_notional": 5, "minimum_average_dollar_volume": 5_000_000,
                            "allow_fractional_shares": True, "allowed_asset_types": ["equity", "etf"],
                            "excluded_sectors": [],
                        },
                        planning_mode="next_market_open",
                        market_session="closed",
                    )
                    plan_log.append({
                        "plan_id": plan["plan_id"], "decision_date": current_date.strftime("%Y-%m-%d"),
                        "status": "ABSTAINED" if plan["abstained"] else "PROPOSED",
                        "candidate_count": len(packets), "selected_symbols": plan["selected_symbols"],
                        "intent_count": len(plan["order_intents"]), "target_weights": plan["target_weights"],
                    })
                    if plan["order_intents"]:
                        pending = plan
                    last_decision = current_date

                spy_value = initial_capital * close_prices["SPY"] / self._price_on(price_data["SPY"], dates[0], "Close")
                qqq_value = initial_capital * close_prices["QQQ"] / self._price_on(price_data["QQQ"], dates[0], "Close")
                equity_records.append({"Date": current_date, "Portfolio_Value": total_equity,
                                       "Cash": cash, "Stock_Value": stock_value,
                                       "SPY_Value": spy_value, "QQQ_Value": qqq_value})

        equity = pd.DataFrame(equity_records).set_index("Date")
        equity["Daily_Return"] = equity["Portfolio_Value"].pct_change().fillna(0.0)
        equity["SPY_Daily_Return"] = equity["SPY_Value"].pct_change().fillna(0.0)
        equity["QQQ_Daily_Return"] = equity["QQQ_Value"].pct_change().fillna(0.0)
        equity["Drawdown_Pct"] = (equity["Portfolio_Value"] - equity["Portfolio_Value"].cummax()) / equity["Portfolio_Value"].cummax() * 100
        metric_engine = Backtester(slippage_bps=self.slippage_bps)
        metrics = metric_engine._calculate_metrics(
            equity, initial_capital, trades,
            self._price_on(price_data["SPY"], dates[0], "Close"), self._price_on(price_data["SPY"], dates[-1], "Close"),
            self._price_on(price_data["QQQ"], dates[0], "Close"), self._price_on(price_data["QQQ"], dates[-1], "Close"),
        )
        sources = dict(self.analyzer.data_sources)
        if self.fundamentals_provider:
            sources["fundamentals"] = "SEC EDGAR Company Facts (filing-date filtered)"
        return ProposalBacktestResult(metrics, equity, plan_log, trades, holdings, cash, sources)

    @staticmethod
    def _price_on(frame: pd.DataFrame, date: pd.Timestamp, column: str) -> float:
        if date in frame.index:
            return float(frame.loc[date, column])
        return float(frame.loc[:date, column].iloc[-1])

    @staticmethod
    def _price_on_optional(frame: pd.DataFrame, date: pd.Timestamp, column: str) -> Optional[float]:
        history = frame.loc[:date, column]
        return float(history.iloc[-1]) if not history.empty else None

    def _execute(self, intents, open_prices, current_date, holdings, average_costs, acquired_dates, trades, cash_box):
        for intent in sorted(intents, key=lambda item: item["side"] != "sell"):
            symbol = intent["symbol"]
            market_price = open_prices[symbol]
            if intent["side"] == "sell":
                quantity = min(float(intent["quantity"]), holdings.get(symbol, 0.0))
                fill = market_price * (1 - self.slippage_bps / 10_000)
                gross = quantity * fill
                fee = gross * .0000278
                pnl = (fill - average_costs.get(symbol, fill)) * quantity - fee
                cash_box[0] += gross - fee
                holdings[symbol] = max(0.0, holdings.get(symbol, 0.0) - quantity)
                if holdings[symbol] < 1e-8:
                    holdings.pop(symbol, None)
                    average_costs.pop(symbol, None)
                    acquired_dates.pop(symbol, None)
                trades.append({"date": current_date.strftime("%Y-%m-%d"), "ticker": symbol,
                               "action": "SELL", "shares": quantity, "price": fill,
                               "fee": fee, "slippage_cost": quantity * (market_price - fill),
                               "realized_pnl": pnl, "plan_id": intent["intent_id"].split(":")[0]})
            else:
                dollars = min(float(intent["dollar_amount"]), cash_box[0])
                fill = market_price * (1 + self.slippage_bps / 10_000)
                quantity = dollars / fill
                old_quantity = holdings.get(symbol, 0.0)
                if old_quantity <= 0:
                    acquired_dates[symbol] = current_date
                average_costs[symbol] = (average_costs.get(symbol, 0.0) * old_quantity + dollars) / (old_quantity + quantity)
                holdings[symbol] = old_quantity + quantity
                cash_box[0] -= dollars
                trades.append({"date": current_date.strftime("%Y-%m-%d"), "ticker": symbol,
                               "action": "BUY", "shares": quantity, "price": fill,
                               "fee": 0.0, "slippage_cost": quantity * (fill - market_price),
                               "plan_id": intent["intent_id"].split(":")[0]})
