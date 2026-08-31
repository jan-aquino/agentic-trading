"""
Configuration module for the Agentic Trading System.
Handles environment variables, default settings, Robinhood MCP configs,
notification preferences, and strict compliance restrictions.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# Automatically load .env file if present
def _load_env_file():
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("'").strip('"')
                    if k and k not in os.environ:
                        os.environ[k] = v

_load_env_file()


@dataclass
class ComplianceConfig:
    """Compliance rules and restricted security lists."""
    # Snowflake (SNOW) is strictly restricted due to employment policy
    restricted_tickers: List[str] = field(default_factory=lambda: ["SNOW"])
    max_position_weight: float = 0.25  # Max 25% allocation to any single stock
    min_cash_buffer: float = 0.05      # Minimum 5% cash buffer at all times
    target_cash_buffer: float = 0.12   # Target ~12% cash buffer like Rallies model
    enable_strict_mode: bool = True    # Raise exceptions on any compliance violation


@dataclass
class StrategyConfig:
    """Strategy parameters emulating the Rallies ChatGPT portfolio."""
    name: str = "Rallies_ChatGPT_Emulation"
    description: str = (
        "AI Infrastructure growth leaders blended with high-conviction core "
        "defensive anchors, momentum filtering, and dynamic rebalancing."
    )
    # AI Infrastructure thematic universe
    ai_infra_universe: List[str] = field(
        default_factory=lambda: [
            "CRDO",  # Credo Technology Group (High-speed AI connectivity)
            "NBIS",  # Nebius Group (AI Cloud infrastructure)
            "GOOGL", # Alphabet (Core AI & Cloud)
            "NVDA",  # NVIDIA (AI Accelerators)
            "AMD",   # Advanced Micro Devices (AI & Compute)
            "MRVL",  # Marvell Technology (AI optical/interconnect)
            "APH",   # Amphenol (AI cabling/connectors)
            "AVGO",  # Broadcom (AI ASICs & Networking)
            "MSFT",  # Microsoft (AI Platform & Cloud)
            "AMZN",  # Amazon (AWS AI infrastructure)
        ]
    )
    # Diversified core resilient anchors (low-beta / financial / health / defense)
    core_diversified_universe: List[str] = field(
        default_factory=lambda: [
            "JPM",   # JPMorgan Chase (Financial anchor)
            "PGR",   # Progressive (Defensive insurance)
            "V",     # Visa (Payment network moat)
            "CI",    # Cigna (Healthcare anchor)
            "LDOS",  # Leidos Holdings (Defense & tech services)
            "LLY",   # Eli Lilly (Healthcare growth)
            "UNH",   # UnitedHealth Group (Healthcare moat)
        ]
    )
    # Target allocation split between AI Infra and Core Diversified
    ai_infra_target_weight: float = 0.65
    core_diversified_target_weight: float = 0.23
    cash_target_weight: float = 0.12

    # Technical & momentum filters
    rsi_period: int = 14
    rsi_overbought: float = 75.0
    rsi_oversold: float = 35.0
    ema_fast: int = 20
    ema_slow: int = 50
    sma_trend: int = 200
    atr_period: int = 14
    trailing_stop_atr_mult: float = 2.5
    rebalance_frequency_days: int = 7  # Weekly rebalancing check


@dataclass
class NotifierConfig:
    """Notification configuration for human-in-the-loop trade confirmation."""
    primary_channel: str = os.getenv("NOTIFICATION_CHANNEL", "imessage")  # 'imessage', 'twilio', or 'cli'
    phone_number: str = os.getenv("PHONE_NUMBER", os.getenv("NOTIFICATION_PHONE_NUMBER", "+15551234567"))
    twilio_account_sid: str = os.getenv("TWILIO_ACCOUNT_SID", "")
    twilio_auth_token: str = os.getenv("TWILIO_AUTH_TOKEN", "")
    twilio_from_number: str = os.getenv("TWILIO_FROM_NUMBER", "")
    confirmation_timeout_seconds: int = int(os.getenv("CONFIRMATION_TIMEOUT_SECONDS", "600"))
    auto_approve_dry_run: bool = os.getenv("AUTO_APPROVE_DRY_RUN", "false").lower() in ("1", "true", "yes")


@dataclass
class RobinhoodMCPConfig:
    """Official Robinhood Trading MCP connection and execution parameters.

    Authentication is performed by Robinhood's browser-based MCP connection in
    Codex. Do not put Robinhood credentials, MFA secrets, or bearer tokens in
    this project or its .env file.
    """
    mcp_server_url: str = os.getenv("ROBINHOOD_MCP_URL", "https://agent.robinhood.com/mcp/trading")
    use_mock: bool = os.getenv("ROBINHOOD_USE_MOCK", "true").lower() in ("1", "true", "yes")
    slippage_bps: float = float(os.getenv("SLIPPAGE_BPS", "5.0"))
    est_sec_fee_rate: float = 0.0000278


@dataclass
class SystemConfig:
    """Root configuration object."""
    workspace_dir: str = str(Path(__file__).parent.resolve())
    initial_capital: float = 100000.0  # $100k standard Rallies arena starting balance
    compliance: ComplianceConfig = field(default_factory=ComplianceConfig)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    notifier: NotifierConfig = field(default_factory=NotifierConfig)
    robinhood: RobinhoodMCPConfig = field(default_factory=RobinhoodMCPConfig)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def save_to_file(self, file_path: str) -> None:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load_from_file(cls, file_path: str) -> SystemConfig:
        if not os.path.exists(file_path):
            config = cls()
            config.save_to_file(file_path)
            return config

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        compliance = ComplianceConfig(**data.get("compliance", {}))
        strategy = StrategyConfig(**data.get("strategy", {}))
        notifier = NotifierConfig(**data.get("notifier", {}))
        robinhood = RobinhoodMCPConfig(**data.get("robinhood", {}))

        return cls(
            workspace_dir=data.get("workspace_dir", str(Path(__file__).parent.resolve())),
            initial_capital=data.get("initial_capital", 100000.0),
            compliance=compliance,
            strategy=strategy,
            notifier=notifier,
            robinhood=robinhood,
        )


# Global default configuration instance
DEFAULT_CONFIG = SystemConfig()
