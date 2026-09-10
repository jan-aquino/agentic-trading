"""Historical simulation for the proposal-first portfolio mandate.

The backtest uses point-in-time technical scorecards as a research proxy. It
does not claim to recreate the richer fundamental/catalyst packets gathered by
ChatGPT Work in production.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from agent.compliance import ComplianceEngine
from agent.market_analyzer import MarketAnalyzer
from config import StrategyConfig, DEFAULT_CONFIG

logger = logging.getLogger("agent.backtester")


@dataclass
class BacktestMetrics:
    """Comprehensive performance and risk analytics."""
    initial_capital: float
    final_value: float
    total_return_pct: float
    cagr_pct: float
    annualized_volatility_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown_pct: float
    calmar_ratio: float
    win_rate_pct: float
    profit_factor: float
    total_trades: int
    total_slippage_fees: float
    alpha_vs_spy_pct: float
    beta_vs_spy: float
    benchmark_spy_return_pct: float
    benchmark_qqq_return_pct: float


@dataclass
class BacktestResult:
    """Complete output of a backtest run."""
    strategy_name: str
    start_date: str
    end_date: str
    metrics: BacktestMetrics
    equity_curve: pd.DataFrame  # Columns: ['Portfolio_Value', 'Cash', 'SPY_Value', 'QQQ_Value', 'Drawdown_Pct']
    monthly_returns: pd.DataFrame
    trades_log: List[Dict[str, Any]]
    final_holdings: Dict[str, float]
    compliance_notes: str
    data_sources: Dict[str, str]
    methodology_notes: List[str]


class Backtester:
    """
    Event-driven backtesting engine with realistic fill modeling.
    """

    def __init__(
        self,
        strategy_config: Optional[StrategyConfig] = None,
        compliance: Optional[ComplianceEngine] = None,
        analyzer: Optional[MarketAnalyzer] = None,
        slippage_bps: float = 5.0,  # 5 bps
        sec_fee_rate: float = 0.0000278,
    ):
        self.config = strategy_config or DEFAULT_CONFIG.strategy
        self.compliance = compliance or ComplianceEngine()
        self.analyzer = analyzer or MarketAnalyzer(config=self.config)
        self.slippage_bps = slippage_bps
        self.sec_fee_rate = sec_fee_rate

    def run(
        self,
        start_date: str = "2023-01-01",
        end_date: str = "2026-06-30",
        initial_capital: float = 100000.0,
        rebalance_interval_days: int = 7,
        exclude_snow: bool = True,
        target_cash_weight: float = 0.10,
        maximum_position_weight: float = 0.20,
        maximum_positions: int = 10,
        minimum_candidate_score: float = 60.0,
        minimum_trade_notional: float = 5.0,
        allow_fractional_shares: bool = True,
    ) -> BacktestResult:
        """
        Executes a historical backtest from start_date to end_date.
        """
        if initial_capital <= 0:
            raise ValueError("initial_capital must be positive")
        if not 0.05 <= target_cash_weight <= 0.80:
            raise ValueError("target_cash_weight must be between 5% and 80%")
        if not 0.01 <= maximum_position_weight <= 0.20:
            raise ValueError("maximum_position_weight must be between 1% and 20%")
        if maximum_positions < 1:
            raise ValueError("maximum_positions must be positive")

        logger.info(f"Starting backtest from {start_date} to {end_date} (Initial: ${initial_capital:,.2f})")

        # 1. Gather all universe tickers + benchmarks
        universe_tickers = list(set(self.config.ai_infra_universe + self.config.core_diversified_universe + ["SPY", "QQQ", "SNOW"]))
        
        if exclude_snow:
            # Strictly filter SNOW from trading universe
            trading_universe = self.compliance.filter_universe(universe_tickers)
        else:
            trading_universe = universe_tickers

        # Fetch history before the requested period so indicators are warm on
        # day one without deleting the first 50 trading days from performance.
        requested_start = pd.Timestamp(start_date)
        requested_end = pd.Timestamp(end_date)
        if requested_end < requested_start:
            raise ValueError("end_date must not precede start_date")
        warmup_start = (requested_start - pd.Timedelta(days=370)).strftime("%Y-%m-%d")

        # Fetch historical price data for all tickers.
        price_data: Dict[str, pd.DataFrame] = {}
        for t in universe_tickers:
            df = self.analyzer.fetch_ohlcv(t, start_date=warmup_start, end_date=end_date)
            price_data[t] = df

        # Build master date index from SPY
        spy_df = price_data.get("SPY")
        if spy_df is None or spy_df.empty:
            raise RuntimeError("Failed to load benchmark SPY data.")

        all_dates = pd.DatetimeIndex(spy_df.index)
        eval_dates = all_dates[(all_dates >= requested_start) & (all_dates <= requested_end)]
        if eval_dates.empty:
            raise ValueError("No benchmark trading dates exist in the requested period")
        if len(spy_df.loc[:eval_dates[0]]) < 50:
            raise ValueError("Not enough pre-period data for indicator warmup")

        # Initialize simulation state
        cash = initial_capital
        holdings: Dict[str, float] = {}
        average_costs: Dict[str, float] = {}
        trailing_stops: Dict[str, float] = {}
        trades_log: List[Dict[str, Any]] = []
        equity_records: List[Dict[str, Any]] = []

        last_rebalance_date = eval_dates[0] - timedelta(days=999)

        # Initial benchmark prices for buy-and-hold scaling
        spy_start_price = float(price_data["SPY"].loc[eval_dates[0], "Close"])
        qqq_start_price = float(price_data["QQQ"].loc[eval_dates[0], "Close"])

        for current_date in eval_dates:
            # 1. Update current asset prices on this date
            current_prices: Dict[str, float] = {}
            for t in universe_tickers:
                df = price_data[t]
                if current_date in df.index:
                    current_prices[t] = float(df.loc[current_date, "Close"])
                elif not df.loc[:current_date].empty:
                    current_prices[t] = float(df.loc[:current_date, "Close"].iloc[-1])
                else:
                    current_prices[t] = 100.0

            # 2. Check trailing stop-losses on current positions
            for ticker in list(holdings.keys()):
                qty = holdings[ticker]
                if qty <= 0:
                    continue
                p = current_prices.get(ticker, 0.0)
                stop_p = trailing_stops.get(ticker, 0.0)

                if stop_p > 0 and p <= stop_p:
                    # Trailing stop triggered! Liquidate position
                    fill_price = p * (1 - self.slippage_bps / 10000.0)
                    gross = qty * fill_price
                    fee = gross * self.sec_fee_rate
                    slippage_cost = qty * max(0.0, p - fill_price)
                    net = gross - fee
                    realized_pnl = (fill_price - average_costs.get(ticker, fill_price)) * qty - fee
                    cash += net
                    trades_log.append({
                        "date": current_date.strftime("%Y-%m-%d"),
                        "ticker": ticker,
                        "action": "SELL_STOP_LOSS",
                        "shares": qty,
                        "price": round(fill_price, 2),
                        "total": round(net, 2),
                        "fee": round(fee, 6),
                        "slippage_cost": round(slippage_cost, 6),
                        "realized_pnl": round(realized_pnl, 6),
                        "reason": f"Trailing stop-loss hit @ ${p:.2f} <= ${stop_p:.2f}",
                    })
                    del holdings[ticker]
                    average_costs.pop(ticker, None)
                    del trailing_stops[ticker]

            # 3. Calculate current portfolio total equity
            stock_value = sum(holdings.get(t, 0) * current_prices.get(t, 0.0) for t in holdings)
            total_equity = cash + stock_value

            # 4. Check if rebalancing should occur
            days_since_rebalance = (current_date - last_rebalance_date).days
            if days_since_rebalance >= rebalance_interval_days:
                last_rebalance_date = current_date
                
                # Build subset price data sliced up to current_date for analysis (no lookahead bias)
                sliced_price_data: Dict[str, pd.DataFrame] = {}
                for t in trading_universe:
                    sliced = price_data[t].loc[:current_date]
                    if len(sliced) >= 30:
                        sliced_price_data[t] = sliced

                # Generate scorecards for AI infra and Core candidates
                scorecards = {}
                for t in trading_universe:
                    if t in ("SPY", "QQQ"):
                        continue
                    # Strict compliance filter
                    if exclude_snow and self.compliance.is_restricted(t):
                        continue

                    if t in sliced_price_data:
                        cat = "AI_INFRA" if t in self.config.ai_infra_universe else "CORE_DIVERSIFIED"
                        try:
                            card = self.analyzer.evaluate_security(t, category=cat, df=sliced_price_data[t])
                            scorecards[t] = card
                        except Exception:
                            pass

                ranked = sorted(
                    (
                        card for card in scorecards.values()
                        if card.composite_rank >= minimum_candidate_score
                        and card.signal in ("STRONG_BUY", "BUY", "HOLD")
                    ),
                    key=lambda card: card.composite_rank,
                    reverse=True,
                )[:maximum_positions]
                target_weights = self._allocate_capped_weights(
                    ranked, 1.0 - target_cash_weight, maximum_position_weight
                )
                # Unallocated capital stays in cash when too few candidates
                # qualify; the minimum score is never lowered to force exposure.
                target_weights["CASH"] = 1.0 - sum(target_weights.values())

                # Execute Rebalancing Trades
                # Sells first
                for t in list(holdings.keys()):
                    if t not in target_weights or target_weights[t] == 0:
                        qty = holdings[t]
                        p = current_prices.get(t, 0.0)
                        fill_p = p * (1 - self.slippage_bps / 10000.0)
                        gross = qty * fill_p
                        fee = gross * self.sec_fee_rate
                        slippage_cost = qty * max(0.0, p - fill_p)
                        net = gross - fee
                        realized_pnl = (fill_p - average_costs.get(t, fill_p)) * qty - fee
                        cash += net
                        trades_log.append({
                            "date": current_date.strftime("%Y-%m-%d"),
                            "ticker": t,
                            "action": "SELL_EXIT",
                            "shares": qty,
                            "price": round(fill_p, 2),
                            "total": round(net, 2),
                            "fee": round(fee, 6),
                            "slippage_cost": round(slippage_cost, 6),
                            "realized_pnl": round(realized_pnl, 6),
                            "reason": "Rebalance exit / rotation",
                        })
                        del holdings[t]
                        average_costs.pop(t, None)
                        if t in trailing_stops:
                            del trailing_stops[t]
                    elif t in target_weights:
                        tgt_val = target_weights[t] * total_equity
                        cur_val = holdings[t] * current_prices.get(t, 0.0)
                        if cur_val > tgt_val * 1.10:  # Trim if > 10% drift
                            excess_val = cur_val - tgt_val
                            p = current_prices.get(t, 0.0)
                            shares_to_trim = (
                                round(excess_val / p, 6) if allow_fractional_shares
                                else int(excess_val / p)
                            )
                            if shares_to_trim > 0:
                                fill_p = p * (1 - self.slippage_bps / 10000.0)
                                gross = shares_to_trim * fill_p
                                fee = gross * self.sec_fee_rate
                                slippage_cost = shares_to_trim * max(0.0, p - fill_p)
                                net = gross - fee
                                realized_pnl = (
                                    (fill_p - average_costs.get(t, fill_p)) * shares_to_trim - fee
                                )
                                cash += net
                                holdings[t] -= shares_to_trim
                                trades_log.append({
                                    "date": current_date.strftime("%Y-%m-%d"),
                                    "ticker": t,
                                    "action": "SELL_TRIM",
                                    "shares": shares_to_trim,
                                    "order_type": "market",
                                    "amount_type": "fractional_shares" if not float(shares_to_trim).is_integer() else "whole_shares",
                                    "market_hours": "regular_hours",
                                    "price": round(fill_p, 2),
                                    "total": round(net, 2),
                                    "fee": round(fee, 6),
                                    "slippage_cost": round(slippage_cost, 6),
                                    "realized_pnl": round(realized_pnl, 6),
                                    "reason": "Rebalance trim back to target weight",
                                })

                # Buys second
                for t, wt in target_weights.items():
                    if t == "CASH" or (exclude_snow and self.compliance.is_restricted(t)):
                        continue
                    tgt_val = wt * total_equity
                    cur_val = holdings.get(t, 0) * current_prices.get(t, 0.0)
                    if tgt_val > cur_val * 1.05:
                        needed_val = tgt_val - cur_val
                        p = current_prices.get(t, 0.0)
                        fill_p = p * (1 + self.slippage_bps / 10000.0)
                        shares_to_buy = (
                            round(needed_val / fill_p, 6)
                            if allow_fractional_shares and fill_p > 0
                            else int(needed_val / fill_p) if fill_p > 0 else 0
                        )
                        cost = shares_to_buy * fill_p

                        # Check available cash maintaining buffer
                        min_cash = total_equity * self.compliance.config.min_cash_buffer
                        if cost > (cash - min_cash):
                            affordable = max(0.0, cash - min_cash)
                            shares_to_buy = (
                                round(affordable / fill_p, 6)
                                if allow_fractional_shares
                                else int(affordable / fill_p)
                            )
                            cost = shares_to_buy * fill_p

                        if shares_to_buy > 0 and cost >= minimum_trade_notional:
                            cash -= cost
                            old_quantity = holdings.get(t, 0.0)
                            old_cost = average_costs.get(t, 0.0) * old_quantity
                            holdings[t] = old_quantity + shares_to_buy
                            average_costs[t] = (old_cost + cost) / holdings[t]
                            # Update dynamic trailing stop
                            card = scorecards.get(t)
                            trailing_stops[t] = card.target_stop_loss if card else round(p * 0.90, 2)
                            trades_log.append({
                                "date": current_date.strftime("%Y-%m-%d"),
                                "ticker": t,
                                "action": "BUY",
                                "shares": shares_to_buy,
                                "order_type": "market" if allow_fractional_shares else "limit",
                                "amount_type": "dollar_amount" if allow_fractional_shares else "whole_shares",
                                "requested_dollar_amount": round(cost, 2) if allow_fractional_shares else None,
                                "market_hours": "regular_hours",
                                "price": round(fill_p, 2),
                                "total": round(cost, 2),
                                "fee": 0.0,
                                "slippage_cost": round(shares_to_buy * max(0.0, fill_p - p), 6),
                                "reason": f"Target allocation {wt:.1%} (Score: {scorecards[t].composite_rank:.1f})" if t in scorecards else "Target allocation",
                            })

            # Recalculate end-of-day equity
            stock_value = sum(holdings.get(t, 0) * current_prices.get(t, 0.0) for t in holdings)
            total_equity = cash + stock_value

            # Benchmark performance tracking (scaled to initial capital)
            spy_curr = float(price_data["SPY"].loc[current_date, "Close"])
            qqq_curr = float(price_data["QQQ"].loc[current_date, "Close"])
            spy_val = initial_capital * (spy_curr / spy_start_price)
            qqq_val = initial_capital * (qqq_curr / qqq_start_price)

            equity_records.append({
                "Date": current_date,
                "Portfolio_Value": round(total_equity, 2),
                "Cash": round(cash, 2),
                "Stock_Value": round(stock_value, 2),
                "SPY_Value": round(spy_val, 2),
                "QQQ_Value": round(qqq_val, 2),
            })

        # Build equity curve dataframe
        equity_df = pd.DataFrame(equity_records).set_index("Date")
        equity_df["Daily_Return"] = equity_df["Portfolio_Value"].pct_change().fillna(0.0)
        equity_df["SPY_Daily_Return"] = equity_df["SPY_Value"].pct_change().fillna(0.0)
        equity_df["QQQ_Daily_Return"] = equity_df["QQQ_Value"].pct_change().fillna(0.0)

        # Drawdown calculation
        rolling_max = equity_df["Portfolio_Value"].cummax()
        equity_df["Drawdown_Pct"] = ((equity_df["Portfolio_Value"] - rolling_max) / rolling_max) * 100

        # Calculate performance analytics
        metrics = self._calculate_metrics(
            equity_df, initial_capital, trades_log, spy_start_price, price_data["SPY"].iloc[-1]["Close"],
            qqq_start_price, price_data["QQQ"].iloc[-1]["Close"]
        )

        # Monthly returns matrix
        monthly_df = self._compute_monthly_returns(equity_df["Portfolio_Value"])

        compliance_msg = (
            "COMPLIANCE STRICT PASSED: Snowflake (SNOW) was 100% excluded across all screening, "
            "allocation, rebalancing, and execution steps."
            if exclude_snow
            else "WARNING: SNOW included for comparative analysis baseline."
        )

        return BacktestResult(
            strategy_name=self.config.name + ("_NO_SNOW" if exclude_snow else "_WITH_SNOW"),
            start_date=start_date,
            end_date=end_date,
            metrics=metrics,
            equity_curve=equity_df,
            monthly_returns=monthly_df,
            trades_log=trades_log,
            final_holdings=holdings,
            compliance_notes=compliance_msg,
            data_sources=dict(self.analyzer.data_sources),
            methodology_notes=[
                "Point-in-time technical scorecards proxy for production research packets.",
                "The candidate universe is the configured historical test universe, not a survivorship-bias-free market-wide universe.",
                "Fractional buys simulate regular-hours dollar market orders with closing-price slippage.",
                "No broker review, approval timing, taxes, dividends, or intraday fill uncertainty is simulated.",
            ],
        )

    @staticmethod
    def _allocate_capped_weights(candidates: List[Any], budget: float, cap: float) -> Dict[str, float]:
        """Allocate by score without exceeding the mandate position cap."""
        weights: Dict[str, float] = {card.ticker: 0.0 for card in candidates}
        active = list(candidates)
        remaining = max(0.0, budget)
        while active and remaining > 1e-12:
            score_total = sum(max(0.0, card.composite_rank) for card in active)
            if score_total <= 0:
                break
            capped = []
            allocated = 0.0
            for card in active:
                room = cap - weights[card.ticker]
                share = remaining * card.composite_rank / score_total
                addition = min(room, share)
                weights[card.ticker] += addition
                allocated += addition
                if weights[card.ticker] >= cap - 1e-12:
                    capped.append(card)
            remaining -= allocated
            if not capped:
                break
            active = [card for card in active if card not in capped]
        return {ticker: weight for ticker, weight in weights.items() if weight > 0}

    def _calculate_metrics(
        self,
        equity_df: pd.DataFrame,
        initial_capital: float,
        trades_log: List[Dict[str, Any]],
        spy_start_p: float,
        spy_end_p: float,
        qqq_start_p: float,
        qqq_end_p: float,
    ) -> BacktestMetrics:
        """Computes statistical metrics (Sharpe, Sortino, Drawdown, Alpha, Beta)."""
        final_val = float(equity_df["Portfolio_Value"].iloc[-1])
        total_ret = ((final_val / initial_capital) - 1) * 100

        days = (equity_df.index[-1] - equity_df.index[0]).days
        years = max(0.1, days / 365.25)
        cagr = ((final_val / initial_capital) ** (1 / years) - 1) * 100

        daily_returns = equity_df["Daily_Return"]
        vol_ann = float(daily_returns.std() * np.sqrt(252) * 100)

        # Risk-free rate (4.0%)
        rf_daily = 0.04 / 252
        excess_returns = daily_returns - rf_daily
        sharpe = float((excess_returns.mean() / daily_returns.std()) * np.sqrt(252)) if daily_returns.std() > 0 else 0.0

        downside = daily_returns[daily_returns < 0]
        downside_std = downside.std() * np.sqrt(252)
        sortino = float((excess_returns.mean() * np.sqrt(252)) / downside_std) if downside_std > 0 else 0.0

        max_dd = float(equity_df["Drawdown_Pct"].min())  # negative number
        calmar = float(cagr / abs(max_dd)) if max_dd != 0 else 0.0

        # Benchmark returns
        spy_ret = ((spy_end_p / spy_start_p) - 1) * 100
        qqq_ret = ((qqq_end_p / qqq_start_p) - 1) * 100

        # Beta and Alpha vs SPY
        cov = np.cov(daily_returns, equity_df["SPY_Daily_Return"])[0, 1]
        spy_var = np.var(equity_df["SPY_Daily_Return"])
        beta = float(cov / spy_var) if spy_var > 0 else 1.0
        alpha = float((cagr - (4.0 + beta * (spy_ret * (1 / years) - 4.0))))

        # Trade metrics
        total_trades = len(trades_log)
        total_fees = sum(
            t.get("fee", 0.0) + t.get("slippage_cost", 0.0) for t in trades_log
        )

        realized = [
            float(t["realized_pnl"]) for t in trades_log if "realized_pnl" in t
        ]
        wins = [pnl for pnl in realized if pnl > 0]
        losses = [pnl for pnl in realized if pnl < 0]
        win_rate = (len(wins) / len(realized) * 100) if realized else 0.0
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else (float("inf") if gross_profit else 0.0)

        return BacktestMetrics(
            initial_capital=round(initial_capital, 2),
            final_value=round(final_val, 2),
            total_return_pct=round(total_ret, 2),
            cagr_pct=round(cagr, 2),
            annualized_volatility_pct=round(vol_ann, 2),
            sharpe_ratio=round(sharpe, 2),
            sortino_ratio=round(sortino, 2),
            max_drawdown_pct=round(max_dd, 2),
            calmar_ratio=round(calmar, 2),
            win_rate_pct=round(win_rate, 1),
            profit_factor=round(profit_factor, 2),
            total_trades=total_trades,
            total_slippage_fees=round(total_fees, 2),
            alpha_vs_spy_pct=round(alpha, 2),
            beta_vs_spy=round(beta, 2),
            benchmark_spy_return_pct=round(spy_ret, 2),
            benchmark_qqq_return_pct=round(qqq_ret, 2),
        )

    def _compute_monthly_returns(self, equity_series: pd.Series) -> pd.DataFrame:
        """Generates a Year x Month returns matrix."""
        monthly_equity = equity_series.resample("ME").last()
        monthly_ret = monthly_equity.pct_change().fillna(
            (monthly_equity.iloc[0] / equity_series.iloc[0]) - 1
        ) * 100

        df = pd.DataFrame({
            "Year": monthly_ret.index.year,
            "Month": monthly_ret.index.strftime("%b"),
            "Return": monthly_ret.values
        })
        piv = df.pivot(index="Year", columns="Month", values="Return")
        month_order = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        cols = [m for m in month_order if m in piv.columns]
        piv = piv[cols].round(2)
        piv["YTD"] = piv.sum(axis=1).round(2)
        return piv
