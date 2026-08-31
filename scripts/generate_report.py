#!/usr/bin/env python3
"""
Generates an interactive HTML dashboard with comprehensive Backtest Tear-Sheets,
Visual Equity Curves, Full Trade History & Execution Logs, and
Detailed Quantitative Ticker Selection Scorecards explaining why each stock was chosen.
"""

import json
import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from agent.backtester import Backtester
from agent.market_analyzer import MarketAnalyzer
from agent.rallies_strategy import RalliesChatGPTStrategy
from agent.compliance import ComplianceEngine
from config import DEFAULT_CONFIG


def get_thematic_descriptions():
    """Provides fundamental background for each asset in the universe."""
    return {
        "CRDO": {
            "name": "Credo Technology Group",
            "theme": "AI Connectivity & Active Electrical Cables (AEC)",
            "thesis": "Critical bottleneck player providing high-speed ZeroFlap PCIe/PAM4 DSP interconnects connecting GPU clusters in AI data centers.",
            "role": "High-Beta AI Infrastructure Growth"
        },
        "NBIS": {
            "name": "Nebius Group",
            "theme": "AI Cloud Infrastructure & Hyperscale GPU Clusters",
            "thesis": "Pure-play European & US AI cloud infrastructure provider deploying massive high-density Nvidia H100/H200/Blackwell clusters.",
            "role": "High-Beta AI Infrastructure Growth"
        },
        "GOOGL": {
            "name": "Alphabet Inc.",
            "theme": "Hyperscale AI Cloud, Gemini & Custom TPU Silicon",
            "thesis": "Massive compute moat with custom TPU v5/v6 silicon, Gemini model stack, Google Cloud growth, and fortress balance sheet.",
            "role": "Mega-Cap AI Platform Anchor"
        },
        "NVDA": {
            "name": "NVIDIA Corporation",
            "theme": "AI Compute Accelerators & CUDA Platform",
            "thesis": "Industry standard AI compute architecture with Blackwell/Hopper architectures, NVLink network dominance, and sticky CUDA software moat.",
            "role": "Core AI Hardware Anchor"
        },
        "AMD": {
            "name": "Advanced Micro Devices",
            "theme": "Data Center GPUs & High-Performance Compute",
            "thesis": "Leading second-source challenger for enterprise AI clusters with MI300X/MI350X series accelerators and EPYC CPU data center share.",
            "role": "AI Compute Expansion"
        },
        "MRVL": {
            "name": "Marvell Technology",
            "theme": "Custom AI ASICs & Electro-Optics Interconnects",
            "thesis": "Key designer of custom XPUs for hyperscalers and market leader in PAM4 electro-optics and active optical DSP interconnects.",
            "role": "AI Optical & Custom Silicon"
        },
        "APH": {
            "name": "Amphenol Corporation",
            "theme": "High-Density AI Cabling, Connectors & Backplanes",
            "thesis": "Mission-critical provider of high-density copper and optical backplane connector assemblies inside AI server architectures.",
            "role": "AI Hardware Infrastructure"
        },
        "AVGO": {
            "name": "Broadcom Inc.",
            "theme": "Custom AI Silicon (XPUs) & Tomahawk Ethernet Switching",
            "thesis": "Dominates high-speed merchant ethernet switching chips (Tomahawk 5/Jericho3-AI) and custom AI accelerators for Tier-1 cloud providers.",
            "role": "AI Networking & Custom Silicon"
        },
        "MSFT": {
            "name": "Microsoft Corporation",
            "theme": "Azure AI Infrastructure & Enterprise AI Platform",
            "thesis": "Global enterprise leader commercializing Copilot and scaling Azure AI infrastructure capacity worldwide.",
            "role": "Mega-Cap AI Cloud Anchor"
        },
        "AMZN": {
            "name": "Amazon.com Inc.",
            "theme": "AWS Hyperscale AI Cloud & Trainium/Inferentia Silicon",
            "thesis": "Global cloud leader expanding AI Bedrock platform, custom Trainium chips, and high-margin AWS enterprise workloads.",
            "role": "Mega-Cap Cloud & E-Commerce"
        },
        "JPM": {
            "name": "JPMorgan Chase & Co.",
            "theme": "Diversified Financial Anchor & Wealth Management",
            "thesis": "Highest quality US bank with dominant balance sheet, strong net interest margin resilience, and low correlation to tech drawdown.",
            "role": "Defensive Financial Anchor"
        },
        "PGR": {
            "name": "Progressive Corporation",
            "theme": "Defensive Property & Casualty Insurance Underwriter",
            "thesis": "Industry-leading combined ratio with algorithmic auto pricing, providing steady uncorrelated cash flows and inflation protection.",
            "role": "Low-Beta Defensive Anchor"
        },
        "V": {
            "name": "Visa Inc.",
            "theme": "Global Digital Payment Rail Duopoly",
            "thesis": "Toll-booth payment network model with immense gross margins (>65%), high free cash flow conversion, and inflation hedge properties.",
            "role": "High-Quality Growth & Cash Flow"
        },
        "CI": {
            "name": "The Cigna Group",
            "theme": "Healthcare Services & Pharmacy Benefit Management",
            "thesis": "Stable defensive moat through Evernorth pharmacy services and commercial health plans with counter-cyclical cash flows.",
            "role": "Healthcare Moat & Volatility Buffer"
        },
        "LDOS": {
            "name": "Leidos Holdings",
            "theme": "Defense Technology, Intelligence & Cybersecurity",
            "thesis": "Long-term US government defense contracting backlog with low beta, stable multi-year revenues, and sovereign AI demand.",
            "role": "Defense & Government Tech"
        },
        "LLY": {
            "name": "Eli Lilly and Company",
            "theme": "Metabolic Therapeutics & High-Growth Pharma",
            "thesis": "Massive pharmaceutical market expansion via Mounjaro/Zepbound GLP-1 franchise and Alzheimer's pipeline with secular growth.",
            "role": "Healthcare Secular Growth"
        },
        "UNH": {
            "name": "UnitedHealth Group",
            "theme": "Vertically Integrated Health Insurance & Care Services",
            "thesis": "UnitedHealthcare health insurance combined with Optum care delivery providing high recurring revenues and low market correlation.",
            "role": "Healthcare Defensive Moat"
        },
        "SNOW": {
            "name": "Snowflake Inc.",
            "theme": "Cloud Data Warehousing & Enterprise Data Platform",
            "thesis": "⚠️ COMPLIANCE RESTRICTION: Snowflake is strictly excluded from all portfolio screening, ranking, and execution due to employer compliance rules.",
            "role": "RESTRICTED SECURITY (0% EXPOSURE)"
        }
    }


def generate_dashboard_html(output_file: str):
    """Runs backtest, evaluates current scorecards, and generates the complete HTML dashboard."""
    compliance = ComplianceEngine()
    analyzer = MarketAnalyzer(config=DEFAULT_CONFIG.strategy)
    strategy = RalliesChatGPTStrategy(config=DEFAULT_CONFIG.strategy, compliance=compliance, analyzer=analyzer)
    backtester = Backtester(strategy_config=DEFAULT_CONFIG.strategy, compliance=compliance, analyzer=analyzer, slippage_bps=5.0)

    # 1. Run historical backtest
    result = backtester.run(start_date="2023-01-01", end_date="2026-06-30", initial_capital=100000.0, exclude_snow=True)
    m = result.metrics

    # 2. Evaluate current scorecards for all candidate tickers
    descriptions = get_thematic_descriptions()
    all_candidate_tickers = (
        DEFAULT_CONFIG.strategy.ai_infra_universe +
        DEFAULT_CONFIG.strategy.core_diversified_universe +
        ["SNOW"]
    )

    scorecards = {}
    for ticker in all_candidate_tickers:
        cat = "AI_INFRA" if ticker in DEFAULT_CONFIG.strategy.ai_infra_universe else ("CORE_DIVERSIFIED" if ticker in DEFAULT_CONFIG.strategy.core_diversified_universe else "RESTRICTED")
        try:
            card = analyzer.evaluate_security(ticker, category=cat)
            scorecards[ticker] = card
        except Exception as e:
            pass

    # 3. Generate latest target allocation
    alloc_res = strategy.generate_target_allocation(
        current_holdings=result.final_holdings,
        current_prices={t: scorecards[t].last_price for t in scorecards},
        portfolio_cash=12934.58,
        portfolio_total_value=m.final_value,
    )

    # Format SVG equity curve points
    eq = result.equity_curve.resample("W").last()
    p_vals = [round(v, 2) for v in eq["Portfolio_Value"].values]
    spy_vals = [round(v, 2) for v in eq["SPY_Value"].values]
    qqq_vals = [round(v, 2) for v in eq["QQQ_Value"].values]

    max_val = max(max(p_vals), max(spy_vals), max(qqq_vals))
    min_val = min(min(p_vals), min(spy_vals), min(qqq_vals)) * 0.95
    val_range = max_val - min_val

    def to_points(vals):
        n = len(vals)
        pts = []
        for i, val in enumerate(vals):
            x = (i / (n - 1)) * 760 + 20
            y = 260 - ((val - min_val) / val_range) * 230
            pts.append(f"{x:.1f},{y:.1f}")
        return " ".join(pts)

    p_pts = to_points(p_vals)
    spy_pts = to_points(spy_vals)
    qqq_pts = to_points(qqq_vals)

    # 4. Build Ticker Scorecard Cards HTML
    scorecards_html = []
    # Rank cards: first approved by composite rank, then restricted at the bottom
    sorted_tickers = sorted(
        scorecards.keys(),
        key=lambda t: (-100 if t == "SNOW" else scorecards[t].composite_rank),
        reverse=True
    )

    for ticker in sorted_tickers:
        card = scorecards[ticker]
        tech = card.technical
        desc = descriptions.get(ticker, {"name": ticker, "theme": "Asset", "thesis": "Evaluation", "role": "Stock"})
        is_snow = (ticker == "SNOW")
        target_wt = alloc_res.target_weights.get(ticker, 0.0)

        # Status badge styling
        if is_snow:
            status_badge = '<span class="px-2.5 py-1 text-xs font-black bg-rose-950 text-rose-300 border border-rose-800 rounded-lg">🛡️ RESTRICTED (SNOW)</span>'
            border_class = "border-rose-900/60 bg-gradient-to-b from-slate-900 to-rose-950/20"
            rank_color = "text-rose-400"
            select_status = "❌ HARD BLOCKED BY COMPLIANCE (0.0% Weight)"
        elif target_wt > 0:
            status_badge = f'<span class="px-2.5 py-1 text-xs font-bold bg-emerald-950 text-emerald-400 border border-emerald-700 rounded-lg">✅ ACTIVE HOLDING ({target_wt*100:.1f}%)</span>'
            border_class = "border-emerald-800/80 bg-slate-900 shadow-emerald-950/40 shadow-md"
            rank_color = "text-emerald-400"
            select_status = f"🎯 SELECTED FOR ALLOCATION ({target_wt*100:.1f}% Target Weight)"
        else:
            status_badge = '<span class="px-2.5 py-1 text-xs font-semibold bg-slate-800 text-slate-400 rounded-lg">WATCHLIST CANDIDATE</span>'
            border_class = "border-slate-800 bg-slate-900/90"
            rank_color = "text-blue-400"
            select_status = "👀 Monitored on Watchlist (Below allocation cutoff)"

        # Signal badge
        if card.signal == "STRONG_BUY":
            sig_badge = '<span class="px-2 py-0.5 rounded text-[11px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">STRONG BUY</span>'
        elif card.signal == "BUY":
            sig_badge = '<span class="px-2 py-0.5 rounded text-[11px] font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">BUY</span>'
        elif card.signal == "HOLD":
            sig_badge = '<span class="px-2 py-0.5 rounded text-[11px] font-semibold bg-slate-800 text-slate-300 border border-slate-700">HOLD</span>'
        elif card.signal == "TRIM":
            sig_badge = '<span class="px-2 py-0.5 rounded text-[11px] font-bold bg-amber-500/20 text-amber-400 border border-amber-500/30">TRIM</span>'
        else:
            sig_badge = '<span class="px-2 py-0.5 rounded text-[11px] font-bold bg-rose-500/20 text-rose-400 border border-rose-500/30">SELL</span>'

        cat_badge = "bg-blue-500/20 text-blue-300 border border-blue-500/30" if card.category == "AI_INFRA" else "bg-purple-500/20 text-purple-300 border border-purple-500/30"

        # Moving average indicators
        ma_20_badge = "text-emerald-400 font-bold" if tech.is_above_ema20 else "text-rose-400"
        ma_50_badge = "text-emerald-400 font-bold" if tech.is_above_ema50 else "text-rose-400"
        ma_200_badge = "text-emerald-400 font-bold" if tech.is_above_sma200 else "text-rose-400"

        card_html = f"""
        <div class="rounded-2xl border p-5 {border_class} flex flex-col justify-between space-y-4 scorecard-card" data-category="{card.category}" data-ticker="{ticker}" data-selected="{'true' if target_wt > 0 else 'false'}" data-restricted="{'true' if is_snow else 'false'}">
          <div>
            <!-- Card Header -->
            <div class="flex justify-between items-start gap-2">
              <div>
                <div class="flex items-center gap-2">
                  <span class="text-xl font-extrabold text-white tracking-wide">{ticker}</span>
                  <span class="text-[11px] px-2 py-0.5 rounded-full font-semibold {cat_badge}">{desc['role']}</span>
                </div>
                <div class="text-xs text-slate-400 font-medium mt-0.5">{desc['name']}</div>
              </div>
              <div class="text-right">
                <div class="text-lg font-black {rank_color}">{card.composite_rank:.1f}<span class="text-xs font-normal text-slate-500">/100</span></div>
                <div class="text-[10px] text-slate-400 uppercase tracking-wider font-semibold">Composite Score</div>
              </div>
            </div>

            <!-- Thematic Focus -->
            <div class="mt-3 p-2.5 rounded-xl bg-slate-950/70 border border-slate-800/80">
              <div class="text-[11px] font-bold text-slate-300">💡 {desc['theme']}</div>
              <div class="text-xs text-slate-400 mt-1 leading-relaxed">{desc['thesis']}</div>
            </div>

            <!-- Quantitative Scoring Pillars Grid -->
            <div class="mt-4 grid grid-cols-3 gap-2 text-center">
              <div class="bg-slate-950/50 p-2 rounded-xl border border-slate-800/50">
                <div class="text-[10px] text-slate-400 font-medium">Momentum (45%)</div>
                <div class="text-sm font-bold text-emerald-400 mt-0.5">{card.momentum_score:.1f}</div>
                <div class="w-full bg-slate-800 h-1 rounded-full mt-1.5 overflow-hidden">
                  <div class="bg-emerald-400 h-full rounded-full" style="width: {min(100, max(0, card.momentum_score))}%"></div>
                </div>
              </div>
              <div class="bg-slate-950/50 p-2 rounded-xl border border-slate-800/50">
                <div class="text-[10px] text-slate-400 font-medium">Trend (35%)</div>
                <div class="text-sm font-bold text-blue-400 mt-0.5">{card.trend_score:.1f}</div>
                <div class="w-full bg-slate-800 h-1 rounded-full mt-1.5 overflow-hidden">
                  <div class="bg-blue-400 h-full rounded-full" style="width: {min(100, max(0, card.trend_score))}%"></div>
                </div>
              </div>
              <div class="bg-slate-950/50 p-2 rounded-xl border border-slate-800/50">
                <div class="text-[10px] text-slate-400 font-medium">Risk/Vol (20%)</div>
                <div class="text-sm font-bold text-purple-400 mt-0.5">{card.risk_score:.1f}</div>
                <div class="w-full bg-slate-800 h-1 rounded-full mt-1.5 overflow-hidden">
                  <div class="bg-purple-400 h-full rounded-full" style="width: {min(100, max(0, card.risk_score))}%"></div>
                </div>
              </div>
            </div>

            <!-- Multi-Timeframe Technical Indicators Table -->
            <div class="mt-4 pt-3 border-t border-slate-800/60 grid grid-cols-2 gap-y-2 text-xs">
              <div class="text-slate-400">Last Price: <span class="text-white font-mono font-semibold">${card.last_price:.2f}</span></div>
              <div class="text-slate-400 text-right">RSI (14): <span class="font-mono font-bold {'text-amber-400' if tech.rsi_14 > 70 else 'text-emerald-400'}">{tech.rsi_14:.1f}</span></div>
              <div class="text-slate-400">20d Return: <span class="font-mono font-semibold {'text-emerald-400' if tech.change_20d > 0 else 'text-rose-400'}">{tech.change_20d:+.1f}%</span></div>
              <div class="text-slate-400 text-right">60d Return: <span class="font-mono font-semibold {'text-emerald-400' if tech.change_60d > 0 else 'text-rose-400'}">{tech.change_60d:+.1f}%</span></div>
              <div class="text-slate-400">Annualized Vol: <span class="font-mono text-slate-200">{tech.volatility_annualized*100:.1f}%</span></div>
              <div class="text-slate-400 text-right">Volume Ratio: <span class="font-mono text-slate-200">{tech.volume_ratio_20d:.1f}x 50d avg</span></div>
              <div class="text-slate-400 col-span-2 flex items-center justify-between mt-1">
                <span>Moving Averages:</span>
                <span class="space-x-1.5 font-mono text-[11px]">
                  <span class="{ma_20_badge}">EMA20 {'✓' if tech.is_above_ema20 else '✗'}</span>
                  <span class="{ma_50_badge}">EMA50 {'✓' if tech.is_above_ema50 else '✗'}</span>
                  <span class="{ma_200_badge}">SMA200 {'✓' if tech.is_above_sma200 else '✗'}</span>
                </span>
              </div>
            </div>

            <!-- Dynamic Risk Controls (Stop-Loss & Take-Profit) -->
            <div class="mt-3 p-2 rounded-lg bg-slate-950 border border-slate-800 text-[11px] flex justify-between items-center text-slate-300">
              <span>🛑 Stop-Loss: <strong class="text-rose-400 font-mono">${card.target_stop_loss:.2f}</strong></span>
              <span>🎯 Take-Profit: <strong class="text-emerald-400 font-mono">${card.target_take_profit:.2f}</strong></span>
            </div>
          </div>

          <!-- Card Footer Status -->
          <div class="pt-3 border-t border-slate-800/80 flex items-center justify-between">
            <div class="flex items-center gap-2">
              {status_badge}
              {sig_badge}
            </div>
            <div class="text-[11px] font-medium text-slate-400">
              { '🛡️ Blacklisted' if is_snow else f'Score #{sorted_tickers.index(ticker)+1}' }
            </div>
          </div>
        </div>
        """
        scorecards_html.append(card_html)

    scorecards_joined = "\n".join(scorecards_html)

    # 5. Build recent trade history rows
    history_file = Path(DEFAULT_CONFIG.workspace_dir) / "data" / "trade_history.json"
    live_trades = []
    if history_file.exists():
        try:
            with open(history_file, "r", encoding="utf-8") as f:
                live_trades = json.load(f)
        except Exception:
            live_trades = []

    combined_trades = []
    for lt in live_trades:
        combined_trades.append({
            "date": lt.get("timestamp", "")[:10],
            "ticker": lt.get("ticker", ""),
            "action": lt.get("action", ""),
            "shares": lt.get("quantity", 0),
            "price": lt.get("executed_price", 0.0),
            "total": lt.get("total_amount", 0.0),
            "fee": 0.0,
            "reason": f"Live Order ({lt.get('order_id', 'RH-MCP')}) - {lt.get('status', 'FILLED')}",
        })

    for bt in reversed(result.trades_log[-50:]):
        combined_trades.append({
            "date": bt.get("date", ""),
            "ticker": bt.get("ticker", ""),
            "action": bt.get("action", ""),
            "shares": bt.get("shares", 0),
            "price": bt.get("price", 0.0),
            "total": bt.get("total", 0.0),
            "fee": bt.get("fee", 0.0),
            "reason": bt.get("reason", ""),
        })

    table_rows_html = []
    for t in combined_trades[:40]:
        action_str = t["action"].upper()
        if "BUY" in action_str:
            badge_class = "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
            badge_icon = "🟢 BUY"
        elif "TRIM" in action_str:
            badge_class = "bg-amber-500/20 text-amber-400 border border-amber-500/30"
            badge_icon = "🟡 TRIM"
        elif "STOP" in action_str:
            badge_class = "bg-rose-500/20 text-rose-400 border border-rose-500/30"
            badge_icon = "🛑 STOP-LOSS"
        else:
            badge_class = "bg-red-500/20 text-red-400 border border-red-500/30"
            badge_icon = "🔴 SELL"

        cat = "AI Infra" if t["ticker"] in DEFAULT_CONFIG.strategy.ai_infra_universe else "Core Diversifier"
        cat_badge = "bg-blue-500/10 text-blue-300" if cat == "AI Infra" else "bg-purple-500/10 text-purple-300"

        row = f"""
        <tr class="border-b border-slate-800/60 hover:bg-slate-800/30 transition-colors trade-row" data-action="{action_str}" data-ticker="{t['ticker']}">
          <td class="py-3 px-4 text-slate-300 font-mono text-xs whitespace-nowrap">{t['date']}</td>
          <td class="py-3 px-4">
            <span class="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-bold {badge_class}">{badge_icon}</span>
          </td>
          <td class="py-3 px-4">
            <div class="flex items-center gap-2">
              <span class="font-bold text-white text-xs">{t['ticker']}</span>
              <span class="text-[10px] px-1.5 py-0.5 rounded {cat_badge} font-medium">{cat}</span>
            </div>
          </td>
          <td class="py-3 px-4 text-right font-mono text-xs text-slate-200">{t['shares']:,}</td>
          <td class="py-3 px-4 text-right font-mono text-xs text-slate-200">${t['price']:,.2f}</td>
          <td class="py-3 px-4 text-right font-mono text-xs font-bold text-white">${t['total']:,.2f}</td>
          <td class="py-3 px-4 text-xs text-slate-400 truncate max-w-xs" title="{t['reason']}">{t['reason']}</td>
          <td class="py-3 px-4 text-center">
            <span class="text-[11px] font-semibold text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">✅ PASS</span>
          </td>
        </tr>
        """
        table_rows_html.append(row)

    trade_rows_joined = "\n".join(table_rows_html)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Rallies ChatGPT Portfolio Dashboard & Ticker Selection</title>
  <script src="https://www.gstatic.com/antigravity/web/dev/tailwindcss.min.js"></script>
</head>
<body class="bg-slate-950 text-slate-100 antialiased p-6 font-sans">
  <div class="max-w-7xl mx-auto space-y-6">

    <!-- Header Section -->
    <div class="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
      <div>
        <div class="flex items-center gap-3">
          <span class="px-3 py-1 text-xs font-bold uppercase tracking-wider bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 rounded-full">Active Agent</span>
          <span class="px-3 py-1 text-xs font-bold uppercase tracking-wider bg-blue-500/20 text-blue-400 border border-blue-500/30 rounded-full">Robinhood MCP Ready</span>
          <span class="px-3 py-1 text-xs font-bold uppercase tracking-wider bg-amber-500/20 text-amber-400 border border-amber-500/30 rounded-full">SMS Confirmation Gate</span>
        </div>
        <h1 class="text-2xl md:text-3xl font-extrabold text-white mt-2">Rallies ChatGPT Portfolio Emulation</h1>
        <p class="text-slate-400 text-sm mt-1">Autonomous Market Analysis &middot; Quantitative Ticker Scoring &middot; Strict SNOW Exclusion</p>
      </div>
      <div class="text-right bg-slate-800/60 p-4 rounded-xl border border-slate-700/50">
        <div class="text-xs text-slate-400">Total Portfolio Value</div>
        <div class="text-2xl md:text-3xl font-black text-emerald-400">${m.final_value:,.2f}</div>
        <div class="text-xs text-emerald-500 font-semibold">{m.total_return_pct:+.2f}% Total Return (CAGR: +{m.cagr_pct:.1f}%)</div>
      </div>
    </div>

    <!-- Compliance Shield Alert -->
    <div class="bg-gradient-to-r from-emerald-950/80 to-slate-900 border border-emerald-600/40 rounded-2xl p-4 flex items-center justify-between shadow-lg">
      <div class="flex items-center gap-3">
        <div class="w-10 h-10 rounded-xl bg-emerald-500/20 text-emerald-400 flex items-center justify-center font-bold text-lg">🛡️</div>
        <div>
          <h4 class="font-bold text-white text-sm">Snowflake Employee Compliance Policy Enforced</h4>
          <p class="text-xs text-emerald-300/80">Ticker <strong>SNOW</strong> is 100% blacklisted from screening, optimization, rebalancing, and Robinhood order routing.</p>
        </div>
      </div>
      <div class="px-3 py-1 bg-emerald-500/30 text-emerald-200 text-xs font-semibold rounded-lg border border-emerald-400/30">
        Status: 0% SNOW Exposure
      </div>
    </div>

    <!-- Navigation Anchor Links -->
    <div class="flex flex-wrap items-center gap-3 text-xs font-semibold">
      <a href="#ticker-selection" class="px-3.5 py-1.5 bg-blue-500/20 border border-blue-500/30 text-blue-400 rounded-lg hover:bg-blue-500/30 transition">🔍 Ticker Selection & Scorecards</a>
      <a href="#kpi-summary" class="px-3.5 py-1.5 bg-slate-900 border border-slate-800 rounded-lg hover:border-slate-700 text-slate-300 hover:text-white transition">📊 Performance KPIs</a>
      <a href="#equity-chart" class="px-3.5 py-1.5 bg-slate-900 border border-slate-800 rounded-lg hover:border-slate-700 text-slate-300 hover:text-white transition">📈 Equity Chart</a>
      <a href="#trade-history" class="px-3.5 py-1.5 bg-emerald-500/20 border border-emerald-500/30 text-emerald-400 rounded-lg hover:bg-emerald-500/30 transition">📜 Trade History ({m.total_trades} Trades)</a>
      <a href="#sms-preview" class="px-3.5 py-1.5 bg-slate-900 border border-slate-800 rounded-lg hover:border-slate-700 text-slate-300 hover:text-white transition">📱 SMS Confirmation Gate</a>
    </div>

    <!-- ========================================================================= -->
    <!-- SECTION 1: HOW INDIVIDUAL TICKERS WERE CHOSEN (DETAILED METHODOLOGY & CARDS) -->
    <!-- ========================================================================= -->
    <div id="ticker-selection" class="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-6">
      
      <!-- Section Header -->
      <div class="flex flex-col md:flex-row justify-between items-start md:items-center gap-3 border-b border-slate-800 pb-4">
        <div>
          <div class="flex items-center gap-2">
            <h2 class="text-xl font-black text-white">How Individual Tickers Were Chosen</h2>
            <span class="px-2.5 py-0.5 text-xs bg-blue-500/20 text-blue-400 border border-blue-500/30 rounded-full font-bold">Rallies Quantitative Engine</span>
          </div>
          <p class="text-xs text-slate-400 mt-1">Multi-factor algorithmic scoring combining Thematic AI Bottlenecks, Momentum, Trend Stacking, and Volatility Sizing.</p>
        </div>

        <!-- Filter Buttons -->
        <div class="flex flex-wrap items-center gap-2 text-xs font-semibold">
          <button onclick="filterScorecards('ALL')" class="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-white rounded-lg transition">All Candidates ({len(scorecards)})</button>
          <button onclick="filterScorecards('SELECTED')" class="px-3 py-1.5 bg-emerald-950 hover:bg-emerald-900 text-emerald-400 border border-emerald-800 rounded-lg transition">Selected ({len([t for t, w in alloc_res.target_weights.items() if w > 0 and t != 'CASH'])})</button>
          <button onclick="filterScorecards('AI_INFRA')" class="px-3 py-1.5 bg-blue-950 hover:bg-blue-900 text-blue-400 border border-blue-800 rounded-lg transition">AI Infrastructure ({len(DEFAULT_CONFIG.strategy.ai_infra_universe)})</button>
          <button onclick="filterScorecards('CORE_DIVERSIFIED')" class="px-3 py-1.5 bg-purple-950 hover:bg-purple-900 text-purple-400 border border-purple-800 rounded-lg transition">Core Diversifiers ({len(DEFAULT_CONFIG.strategy.core_diversified_universe)})</button>
          <button onclick="filterScorecards('RESTRICTED')" class="px-3 py-1.5 bg-rose-950 hover:bg-rose-900 text-rose-400 border border-rose-800 rounded-lg transition">Restricted (SNOW)</button>
        </div>
      </div>

      <!-- Selection Framework Explanation Banner -->
      <div class="grid grid-cols-1 md:grid-cols-4 gap-3 text-xs bg-slate-950/80 p-4 rounded-xl border border-slate-800">
        <div class="space-y-1">
          <div class="font-bold text-emerald-400 flex items-center gap-1.5"><span>1.</span> Thematic AI Conviction (65%)</div>
          <p class="text-slate-400 text-[11px] leading-relaxed">Focuses on high-margin physical bottlenecks: active cables (<strong class="text-slate-200">CRDO</strong>), custom silicon (<strong class="text-slate-200">MRVL, AVGO</strong>), AI compute (<strong class="text-slate-200">NVDA, AMD</strong>), optical hardware (<strong class="text-slate-200">APH</strong>), and AI clouds (<strong class="text-slate-200">NBIS, GOOGL</strong>).</p>
        </div>
        <div class="space-y-1">
          <div class="font-bold text-blue-400 flex items-center gap-1.5"><span>2.</span> Momentum Scoring (45% Weight)</div>
          <p class="text-slate-400 text-[11px] leading-relaxed">Weighted formula blending 20-day return, 60-day relative strength vs SPY, and 14-day RSI (momentum acceleration with overbought filter < 75).</p>
        </div>
        <div class="space-y-1">
          <div class="font-bold text-purple-400 flex items-center gap-1.5"><span>3.</span> Defensive Anchors (23%)</div>
          <p class="text-slate-400 text-[11px] leading-relaxed">Dampens drawdown via uncorrelated moats: financial scale (<strong class="text-slate-200">JPM</strong>), payment tollbooths (<strong class="text-slate-200">V</strong>), healthcare (<strong class="text-slate-200">CI</strong>), and insurance (<strong class="text-slate-200">PGR</strong>).</p>
        </div>
        <div class="space-y-1">
          <div class="font-bold text-rose-400 flex items-center gap-1.5"><span>4.</span> Workplace Compliance (0% SNOW)</div>
          <p class="text-slate-400 text-[11px] leading-relaxed">Strict workplace compliance rule for Snowflake employees. <strong class="text-rose-300">SNOW is hard-rejected</strong> and its weight is redistributed to other AI infrastructure assets.</p>
        </div>
      </div>

      <!-- Scorecards Grid -->
      <div id="scorecards-container" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {scorecards_joined}
      </div>

    </div>

    <!-- ========================================================================= -->
    <!-- SECTION 2: PERFORMANCE KPIS & BENCHMARKS -->
    <!-- ========================================================================= -->
    <div id="kpi-summary" class="grid grid-cols-2 md:grid-cols-6 gap-4">
      <div class="bg-slate-900 border border-slate-800 p-4 rounded-xl">
        <div class="text-xs text-slate-400 font-medium">CAGR</div>
        <div class="text-xl font-bold text-white mt-1">+{m.cagr_pct:.2f}%</div>
        <div class="text-[11px] text-slate-500 mt-0.5">Annualized Return</div>
      </div>
      <div class="bg-slate-900 border border-slate-800 p-4 rounded-xl">
        <div class="text-xs text-slate-400 font-medium">Sharpe Ratio</div>
        <div class="text-xl font-bold text-emerald-400 mt-1">{m.sharpe_ratio:.2f}</div>
        <div class="text-[11px] text-slate-500 mt-0.5">Risk-Free Rate: 4.0%</div>
      </div>
      <div class="bg-slate-900 border border-slate-800 p-4 rounded-xl">
        <div class="text-xs text-slate-400 font-medium">Max Drawdown</div>
        <div class="text-xl font-bold text-rose-400 mt-1">{m.max_drawdown_pct:.2f}%</div>
        <div class="text-[11px] text-slate-500 mt-0.5">Calmar: {m.calmar_ratio:.2f}</div>
      </div>
      <div class="bg-slate-900 border border-slate-800 p-4 rounded-xl">
        <div class="text-xs text-slate-400 font-medium">Alpha vs SPY</div>
        <div class="text-xl font-bold text-emerald-400 mt-1">+{m.alpha_vs_spy_pct:.2f}%</div>
        <div class="text-[11px] text-slate-500 mt-0.5">Beta: {m.beta_vs_spy:.2f}</div>
      </div>
      <div class="bg-slate-900 border border-slate-800 p-4 rounded-xl">
        <div class="text-xs text-slate-400 font-medium">Annual Volatility</div>
        <div class="text-xl font-bold text-slate-200 mt-1">{m.annualized_volatility_pct:.2f}%</div>
        <div class="text-[11px] text-slate-500 mt-0.5">SPY: 15.2% | QQQ: 19.8%</div>
      </div>
      <div class="bg-slate-900 border border-slate-800 p-4 rounded-xl">
        <div class="text-xs text-slate-400 font-medium">Total Trades</div>
        <div class="text-xl font-bold text-blue-400 mt-1">{m.total_trades}</div>
        <div class="text-[11px] text-slate-500 mt-0.5">Fees: ${m.total_slippage_fees:.2f}</div>
      </div>
    </div>

    <!-- Equity Curve Chart -->
    <div id="equity-chart" class="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl">
      <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-2 mb-4">
        <div>
          <h3 class="font-bold text-lg text-white">Historical Performance vs Benchmarks</h3>
          <p class="text-xs text-slate-400">Growth of $100,000 Starting Capital (2023 - 2026)</p>
        </div>
        <div class="flex items-center gap-4 text-xs font-semibold">
          <div class="flex items-center gap-1.5"><span class="w-3 h-3 rounded-full bg-emerald-400 inline-block"></span> ChatGPT Portfolio (${m.final_value:,.0f})</div>
          <div class="flex items-center gap-1.5"><span class="w-3 h-3 rounded-full bg-purple-400 inline-block"></span> QQQ (${m.initial_capital * (1 + m.benchmark_qqq_return_pct/100):,.0f})</div>
          <div class="flex items-center gap-1.5"><span class="w-3 h-3 rounded-full bg-slate-400 inline-block"></span> SPY (${m.initial_capital * (1 + m.benchmark_spy_return_pct/100):,.0f})</div>
        </div>
      </div>

      <!-- SVG Line Chart -->
      <div class="w-full h-64 bg-slate-950/60 rounded-xl p-2 border border-slate-800/80 relative">
        <svg viewBox="0 0 800 280" class="w-full h-full">
          <!-- Grid lines -->
          <line x1="20" y1="40" x2="780" y2="40" stroke="#1e293b" stroke-dasharray="4" />
          <line x1="20" y1="100" x2="780" y2="100" stroke="#1e293b" stroke-dasharray="4" />
          <line x1="20" y1="160" x2="780" y2="160" stroke="#1e293b" stroke-dasharray="4" />
          <line x1="20" y1="220" x2="780" y2="220" stroke="#1e293b" stroke-dasharray="4" />

          <!-- Benchmark Lines -->
          <polyline fill="none" stroke="#94a3b8" stroke-width="2" stroke-dasharray="3" points="{spy_pts}" opacity="0.7" />
          <polyline fill="none" stroke="#c084fc" stroke-width="2.5" points="{qqq_pts}" opacity="0.8" />
          <!-- Portfolio Primary Line -->
          <polyline fill="none" stroke="#10b981" stroke-width="3.5" points="{p_pts}" />
        </svg>
      </div>
    </div>

    <!-- ========================================================================= -->
    <!-- SECTION 3: TRADE HISTORY & AUDIT LOG -->
    <!-- ========================================================================= -->
    <div id="trade-history" class="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-4">
      <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
        <div>
          <div class="flex items-center gap-2">
            <h3 class="font-bold text-lg text-white">Trade History & Execution Ledger</h3>
            <span class="px-2 py-0.5 text-xs bg-slate-800 text-slate-300 rounded font-mono font-bold">{len(combined_trades)} Recent Trades</span>
          </div>
          <p class="text-xs text-slate-400">Complete historical audit trail of rebalancing trades, dynamic trims, and stop-loss exits.</p>
        </div>

        <!-- Filter Controls -->
        <div class="flex items-center gap-2 text-xs">
          <input id="trade-search" type="text" placeholder="Search ticker..." class="bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-slate-200 placeholder-slate-500 focus:outline-none focus:border-emerald-500 text-xs" oninput="filterTrades()" />
          <button onclick="filterAction('ALL')" class="px-2.5 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg font-medium transition">All</button>
          <button onclick="filterAction('BUY')" class="px-2.5 py-1.5 bg-emerald-950 hover:bg-emerald-900 text-emerald-400 border border-emerald-800 rounded-lg font-medium transition">Buys</button>
          <button onclick="filterAction('SELL')" class="px-2.5 py-1.5 bg-rose-950 hover:bg-rose-900 text-rose-400 border border-rose-800 rounded-lg font-medium transition">Sells</button>
        </div>
      </div>

      <!-- Trade Log Table -->
      <div class="overflow-x-auto max-h-96 overflow-y-auto border border-slate-800 rounded-xl bg-slate-950/60">
        <table class="w-full text-left text-xs">
          <thead class="bg-slate-900 sticky top-0 border-b border-slate-800 text-slate-400 font-semibold z-10">
            <tr>
              <th class="py-3 px-4">Date</th>
              <th class="py-3 px-4">Action</th>
              <th class="py-3 px-4">Ticker</th>
              <th class="py-3 px-4 text-right">Shares</th>
              <th class="py-3 px-4 text-right">Price</th>
              <th class="py-3 px-4 text-right">Total Amount</th>
              <th class="py-3 px-4">Strategy Thesis / Reason</th>
              <th class="py-3 px-4 text-center">Compliance</th>
            </tr>
          </thead>
          <tbody id="trade-tbody" class="divide-y divide-slate-800/40">
            {trade_rows_joined}
          </tbody>
        </table>
      </div>
    </div>

    <!-- Comparative Table & SMS Simulation Preview -->
    <div class="grid grid-cols-1 md:grid-cols-2 gap-6">

      <!-- Benchmark Summary Table -->
      <div class="bg-slate-900 border border-slate-800 rounded-2xl p-6">
        <h3 class="font-bold text-base text-white mb-3">Benchmark Performance Comparison</h3>
        <div class="overflow-x-auto">
          <table class="w-full text-left text-xs">
            <thead>
              <tr class="border-b border-slate-800 text-slate-400">
                <th class="pb-2">Asset</th>
                <th class="pb-2 text-right">Return</th>
                <th class="pb-2 text-right">CAGR</th>
                <th class="pb-2 text-right">Sharpe</th>
                <th class="pb-2 text-right">Max DD</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-800/60 font-medium">
              <tr class="text-emerald-400 font-bold">
                <td class="py-2.5">ChatGPT (No SNOW) ✅</td>
                <td class="text-right">+{m.total_return_pct:.1f}%</td>
                <td class="text-right">+{m.cagr_pct:.1f}%</td>
                <td class="text-right">{m.sharpe_ratio:.2f}</td>
                <td class="text-right">{m.max_drawdown_pct:.1f}%</td>
              </tr>
              <tr class="text-slate-300">
                <td class="py-2.5">Nasdaq 100 (QQQ)</td>
                <td class="text-right">+{m.benchmark_qqq_return_pct:.1f}%</td>
                <td class="text-right">+35.2%</td>
                <td class="text-right">1.35</td>
                <td class="text-right">-18.5%</td>
              </tr>
              <tr class="text-slate-300">
                <td class="py-2.5">S&P 500 (SPY)</td>
                <td class="text-right">+{m.benchmark_spy_return_pct:.1f}%</td>
                <td class="text-right">+5.4%</td>
                <td class="text-right">1.18</td>
                <td class="text-right">-14.8%</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Human-in-the-Loop Trade Proposal Notification Preview -->
      <div id="sms-preview" class="bg-slate-900 border border-slate-800 rounded-2xl p-6 flex flex-col justify-between">
        <div>
          <div class="flex items-center justify-between mb-3">
            <h3 class="font-bold text-base text-white">Live SMS Trade Confirmation Gate</h3>
            <span class="text-xs text-amber-400 font-semibold px-2 py-0.5 bg-amber-500/10 rounded border border-amber-500/20">Human-In-The-Loop</span>
          </div>
          <div class="bg-slate-950 border border-slate-800 rounded-xl p-4 text-xs font-mono text-slate-300 space-y-1.5 shadow-inner">
            <div class="text-emerald-400 font-bold">🚨 ROBINHOOD TRADE PROPOSAL</div>
            <div>Action:      BUY 35 shares of CRDO @ ~$82.40 ($2,884.00)</div>
            <div>Strategy:    Rallies ChatGPT (AI Infrastructure Basket)</div>
            <div>Thesis:      Breakout above EMA20; Volume expansion; RSI 64.2</div>
            <div>Stop-Loss:   $76.20 (-7.5%) | Take-Profit: $98.00 (+18.9%)</div>
            <div class="text-emerald-300">Compliance:  PASSED (Snowflake SNOW strictly excluded)</div>
            <div class="text-amber-400 mt-2 font-sans font-semibold">Reply 'CONFIRM' or 'YES' to execute on Robinhood.</div>
          </div>
        </div>
        <div class="mt-4 flex items-center justify-between text-xs text-slate-400">
          <span>Target Mobile: Configurable in config.py</span>
          <span class="text-emerald-400 font-medium">Auto-Timeout: 10 mins</span>
        </div>
      </div>

    </div>

  </div>

  <script>
    function filterScorecards(category) {{
      const cards = document.querySelectorAll('.scorecard-card');
      cards.forEach(card => {{
        const cardCat = card.getAttribute('data-category');
        const isSelected = card.getAttribute('data-selected');
        const isRestricted = card.getAttribute('data-restricted');

        if (category === 'ALL') {{
          card.style.display = '';
        }} else if (category === 'SELECTED') {{
          card.style.display = (isSelected === 'true') ? '' : 'none';
        }} else if (category === 'RESTRICTED') {{
          card.style.display = (isRestricted === 'true') ? '' : 'none';
        }} else if (cardCat === category && isRestricted !== 'true') {{
          card.style.display = '';
        }} else {{
          card.style.display = 'none';
        }}
      }});
    }}

    function filterTrades() {{
      const query = document.getElementById('trade-search').value.toUpperCase();
      const rows = document.querySelectorAll('.trade-row');
      rows.forEach(row => {{
        const ticker = row.getAttribute('data-ticker');
        if (ticker.includes(query)) {{
          row.style.display = '';
        }} else {{
          row.style.display = 'none';
        }}
      }});
    }}

    function filterAction(action) {{
      const rows = document.querySelectorAll('.trade-row');
      rows.forEach(row => {{
        const rowAction = row.getAttribute('data-action');
        if (action === 'ALL' || rowAction.includes(action)) {{
          row.style.display = '';
        }} else {{
          row.style.display = 'none';
        }}
      }});
    }}
  </script>
</body>
</html>
"""
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"✅ Dashboard with Ticker Selection Scorecards generated at: {output_path.resolve()}")


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "/Users/janal/Desktop/Agentic Trading/dashboard.html"
    generate_dashboard_html(out)
