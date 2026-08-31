#!/usr/bin/env python3
"""
Interactive Setup Wizard for deploying the Agentic Trading System
with your real mobile phone number and Robinhood portfolio connection.
"""

import os
import re
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from agent.notifier import TextNotifier
from config import DEFAULT_CONFIG, NotifierConfig


def prompt_user(text: str, default: str = "") -> str:
    if default:
        res = input(f"{text} [{default}]: ").strip()
        return res if res else default
    return input(f"{text}: ").strip()


def normalize_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 10:
        return f"+1{digits}"
    elif len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    elif phone.startswith("+"):
        return phone
    return f"+{digits}"


def main():
    print("\n" + "=" * 80)
    print("🚀 AGENTIC TRADING SYSTEM - LIVE DEPLOYMENT SETUP WIZARD")
    print("=" * 80)
    print("This wizard will configure your real mobile phone number and Robinhood connection.\n")

    env_file = Path(__file__).parent.parent / ".env"
    existing_env = {}
    if env_file.exists():
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    existing_env[k.strip()] = v.strip().strip("'").strip('"')

    # 1. Phone Number Setup
    print("--- 📱 STEP 1: MOBILE NOTIFICATION & CONFIRMATION ---")
    current_phone = existing_env.get("PHONE_NUMBER", "+15551234567")
    raw_phone = prompt_user("Enter your mobile phone number (for trade approval texts)", current_phone)
    phone_number = normalize_phone(raw_phone)

    print("\nSelect notification channel:")
    print("  1. Native macOS iMessage (Recommended for Mac - Free, direct to iPhone)")
    print("  2. Twilio SMS (For cloud servers / cross-platform)")
    chan_choice = prompt_user("Select channel [1 or 2]", "1")
    channel = "imessage" if chan_choice == "1" else "twilio"

    twilio_sid = existing_env.get("TWILIO_ACCOUNT_SID", "")
    twilio_token = existing_env.get("TWILIO_AUTH_TOKEN", "")
    twilio_from = existing_env.get("TWILIO_FROM_NUMBER", "")

    if channel == "twilio":
        twilio_sid = prompt_user("Twilio Account SID", twilio_sid)
        twilio_token = prompt_user("Twilio Auth Token", twilio_token)
        twilio_from = prompt_user("Twilio From Number (+1...)", twilio_from)

    # 2. Robinhood Brokerage Mode
    print("\n--- 💼 STEP 2: ROBINHOOD PORTFOLIO CONNECTION ---")
    print("Live trading is available only through the authenticated official Robinhood Trading MCP in Codex.")
    print("This local runner remains in paper-simulation mode and will never ask for Robinhood credentials.")
    use_mock = "true"
    rh_mcp_url = "https://agent.robinhood.com/mcp/trading"

    # 3. Test Notification
    print(f"\n--- 🧪 STEP 3: TESTING NOTIFICATION TO {phone_number} ---")
    test_notifier = TextNotifier(NotifierConfig(
        primary_channel=channel,
        phone_number=phone_number,
        twilio_account_sid=twilio_sid,
        twilio_auth_token=twilio_token,
        twilio_from_number=twilio_from,
    ))

    test_msg = (
        "🤖 [Agentic Trading] Setup successful! This number is verified to receive trade confirmation alerts "
        "for your Robinhood portfolio (Rallies ChatGPT strategy with strict SNOW exclusion)."
    )
    print(f"Dispatching test message via {channel.upper()} to {phone_number}...")
    success = test_notifier.send_notification(test_msg)
    if success:
        print("✅ Test message dispatched successfully! Please check your phone.")
    else:
        print("⚠️ Notice: Test dispatch finished. If using iMessage, ensure Messages app has signed in.")

    # 4. Save Configuration to .env
    env_content = f"""# ==============================================================================
# Agentic Trading System - Configuration (.env)
# ==============================================================================

# Mobile Notification & Confirmation Gate
NOTIFICATION_CHANNEL={channel}
PHONE_NUMBER={phone_number}
CONFIRMATION_TIMEOUT_SECONDS=600

# Robinhood Brokerage & MCP Settings
ROBINHOOD_USE_MOCK={use_mock}
ROBINHOOD_MCP_URL={rh_mcp_url}

# Twilio Credentials (if applicable)
TWILIO_ACCOUNT_SID={twilio_sid}
TWILIO_AUTH_TOKEN={twilio_token}
TWILIO_FROM_NUMBER={twilio_from}
"""
    with open(env_file, "w", encoding="utf-8") as f:
        f.write(env_content)

    print(f"\n🎉 Configuration saved to: {env_file.resolve()}")
    print("=" * 80)
    print("To run a paper-trading scan:")
    print("  python3 scripts/run_agent.py --dry-run")
    print("For live broker reads or orders, use the authenticated Robinhood MCP in Codex.")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
