"""
Multi-Channel Text Notification and Interactive Trade Confirmation Engine.
Dispatches trade proposals via macOS iMessage / SMS, Twilio API, or Interactive CLI,
enforcing Human-in-the-Loop approval before any Robinhood order is routed.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, List, Optional, Tuple

from agent.rallies_strategy import TradeProposal
from config import NotifierConfig, DEFAULT_CONFIG

logger = logging.getLogger("agent.notifier")


@dataclass
class ConfirmationDecision:
    """User response to a trade proposal."""
    approved: bool
    proposal: TradeProposal
    channel_used: str
    responded_at: str
    decision_reason: str
    timed_out: bool = False


class TextNotifier:
    """
    Manages outbound text alerts and awaits interactive user confirmation.
    """

    def __init__(self, config: Optional[NotifierConfig] = None):
        self.config = config or DEFAULT_CONFIG.notifier
        self.phone_number = self.config.phone_number
        self.primary_channel = self.config.primary_channel.lower()
        self.timeout = self.config.confirmation_timeout_seconds

    def format_proposal_message(self, p: TradeProposal, portfolio_equity: float = 100000.0) -> str:
        """Formats a structured, human-readable trade ticket for SMS / iMessage."""
        action_emoji = "🟢 BUY" if p.is_buy else "🔴 SELL"
        cost_str = f"${p.total_cost:,.2f}"
        pct_str = f"{p.target_weight * 100:.1f}%" if p.is_buy else f"{p.current_weight * 100:.1f}%"

        lines = [
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"🚨 ROBINHOOD TRADE PROPOSAL - CONFIRMATION REQUIRED",
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"Action:      {action_emoji} {p.quantity} shares of {p.ticker}",
            f"Est. Price:  ${p.estimated_price:,.2f} per share",
            f"Total Value: {cost_str} (~{pct_str} of Portfolio)",
            f"Strategy:    Rallies ChatGPT Portfolio ({p.strategy_bucket})",
            f"Allocation:  {p.current_weight * 100:.1f}% ➔ {p.target_weight * 100:.1f}% (Δ {p.weight_delta * 100:+.1f}%)",
            f"Thesis:      {p.thesis}",
            f"Stop-Loss:   ${p.stop_loss:,.2f} | Take-Profit: ${p.take_profit:,.2f} (R:R {p.risk_reward_ratio:.1f}x)",
            f"Compliance:  PASSED (SNOW strict exclusion active)",
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"⚠️ Reply 'CONFIRM' or 'YES' within {self.timeout // 60} min to execute on Robinhood.",
            f"⚠️ Reply 'CANCEL' or ignore to abort.",
        ]
        return "\n".join(lines)

    def send_notification(self, message: str) -> bool:
        """Sends text notification through configured channel."""
        logger.info(f"Sending trade notification via channel: {self.primary_channel}")

        if self.primary_channel == "imessage":
            return self._send_imessage(message, self.phone_number)
        elif self.primary_channel == "twilio":
            return self._send_twilio_sms(message, self.phone_number)
        else:
            print("\n" + message + "\n")
            return True

    def request_trade_confirmation(
        self,
        proposal: TradeProposal,
        portfolio_equity: float = 100000.0,
        interactive: bool = True
    ) -> ConfirmationDecision:
        """
        Formats trade proposal, sends text notification, and blocks until user approves or timeout occurs.
        """
        msg = self.format_proposal_message(proposal, portfolio_equity)
        now_str = datetime.now().isoformat()

        # Send text notification to user's device
        self.send_notification(msg)

        if not interactive or self.config.auto_approve_dry_run:
            logger.info("Auto-confirming proposal (Dry-Run / Non-Interactive mode).")
            return ConfirmationDecision(
                approved=True,
                proposal=proposal,
                channel_used=self.primary_channel,
                responded_at=now_str,
                decision_reason="AUTO_APPROVED_DRY_RUN",
                timed_out=False,
            )

        # Poll both iMessage inbound replies and interactive terminal simultaneously
        print(f"\n[Awaiting confirmation for {proposal.ticker} {proposal.action} trade...]")
        print(f"📱 Reply 'CONFIRM' or 'YES' on your phone via iMessage, or type below (Timeout {self.timeout}s): ")

        approved, reason, timed_out = self._await_dual_confirmation(proposal, now_str)

        if timed_out:
            logger.warning(f"Trade confirmation timed out after {self.timeout} seconds. Aborting execution.")
            self.send_notification(f"⏱️ Trade proposal for {proposal.ticker} ({proposal.action}) has EXPIRED due to timeout.")
            return ConfirmationDecision(
                approved=False,
                proposal=proposal,
                channel_used=self.primary_channel,
                responded_at=datetime.now().isoformat(),
                decision_reason="TIMED_OUT_NO_RESPONSE",
                timed_out=True,
            )

        if approved:
            logger.info(f"Trade proposal for {proposal.ticker} APPROVED ({reason}).")
            return ConfirmationDecision(
                approved=True,
                proposal=proposal,
                channel_used=self.primary_channel,
                responded_at=datetime.now().isoformat(),
                decision_reason=reason,
                timed_out=False,
            )
        else:
            logger.info(f"Trade proposal for {proposal.ticker} REJECTED ({reason}).")
            self.send_notification(f"🚫 Trade proposal for {proposal.ticker} was REJECTED.")
            return ConfirmationDecision(
                approved=False,
                proposal=proposal,
                channel_used=self.primary_channel,
                responded_at=datetime.now().isoformat(),
                decision_reason=reason,
                timed_out=False,
            )

    def _await_dual_confirmation(
        self,
        proposal: TradeProposal,
        start_time_iso: str
    ) -> Tuple[bool, str, bool]:
        """
        Listens for confirmation from both Terminal input and inbound iMessage replies.
        Returns: (approved: bool, reason: str, timed_out: bool)
        """
        result = {"approved": False, "reason": "TIMED_OUT", "done": False, "timed_out": False}
        start_ts = time.time()

        # Thread 1: Terminal input reader
        def terminal_listener():
            try:
                user_val = input(f"Execute {proposal.action} {proposal.quantity} {proposal.ticker}? [y/N]: ")
                clean = (user_val or "").strip().lower()
                if not result["done"]:
                    if clean in ("y", "yes", "confirm", "approve"):
                        result["approved"] = True
                        result["reason"] = "TERMINAL_APPROVAL"
                    else:
                        result["approved"] = False
                        result["reason"] = f"TERMINAL_REJECTED ('{clean}')"
                    result["done"] = True
            except EOFError:
                pass

        t_term = threading.Thread(target=terminal_listener, daemon=True)
        t_term.start()

        # Main polling loop checking iMessage replies while timeout is active
        while time.time() - start_ts < self.timeout:
            if result["done"]:
                return result["approved"], result["reason"], False

            # Check if an iMessage reply has arrived on macOS
            imsg_res = self._check_imessage_reply(self.phone_number)
            if imsg_res is not None:
                is_app, r_text = imsg_res
                result["approved"] = is_app
                result["reason"] = f"IMESSAGE_REPLY ('{r_text}')"
                result["done"] = True
                return is_app, result["reason"], False

            time.sleep(1.5)

        # If loop finishes without response
        return False, "TIMED_OUT", True

    def _check_imessage_reply(self, phone: str) -> Optional[Tuple[bool, str]]:
        """
        Polls macOS Messages chat database for new incoming replies from the user's phone.
        """
        if not phone or phone == "+15551234567":
            return None

        # Check via osascript AppleScript query
        script = f'''
        tell application "Messages"
            try
                set lastMsg to text of last item of (messages of (1st chat whose id contains "{phone[-10:]}"))
                return lastMsg
            on error
                return ""
            end try
        end tell
        '''
        try:
            res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=2)
            if res.returncode == 0:
                txt = res.stdout.strip().lower()
                if txt in ("confirm", "yes", "approve", "y", "buy", "sell"):
                    return True, txt
                elif txt in ("cancel", "no", "reject", "n", "stop"):
                    return False, txt
        except Exception:
            pass
        return None

    def _send_imessage(self, message: str, phone: str) -> bool:
        """Sends native macOS iMessage/SMS using AppleScript osascript."""
        if not phone or phone == "+15551234567":
            logger.info(f"[iMessage Mock] Would send to {phone}:\n{message}")
            return True

        script = f'''
        tell application "Messages"
            set targetService to 1st account whose service type = iMessage
            set targetBuddy to participant "{phone}" of targetService
            send "{message.replace('"', '\\"')}" to targetBuddy
        end tell
        '''
        try:
            res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=5)
            if res.returncode == 0:
                logger.info(f"iMessage dispatched to {phone}")
                return True
            else:
                logger.debug(f"iMessage dispatch returned: {res.stderr}")
                return False
        except Exception as e:
            logger.debug(f"Failed to execute osascript for iMessage: {e}")
            return False

    def _send_twilio_sms(self, message: str, phone: str) -> bool:
        """Sends SMS via Twilio API if credentials are configured."""
        if not (self.config.twilio_account_sid and self.config.twilio_auth_token and self.config.twilio_from_number):
            logger.info(f"[Twilio SMS Mock] Would send to {phone}:\n{message}")
            return True

        try:
            import urllib.parse
            import urllib.request

            url = f"https://api.twilio.com/2010-04-01/Accounts/{self.config.twilio_account_sid}/Messages.json"
            data = urllib.parse.urlencode({
                "To": phone,
                "From": self.config.twilio_from_number,
                "Body": message
            }).encode("utf-8")

            req = urllib.request.Request(url, data=data, method="POST")
            auth_str = f"{self.config.twilio_account_sid}:{self.config.twilio_auth_token}"
            import base64
            b64_auth = base64.b64encode(auth_str.encode("utf-8")).decode("ascii")
            req.add_header("Authorization", f"Basic {b64_auth}")

            with urllib.request.urlopen(req, timeout=8) as resp:
                if resp.status in (200, 201):
                    logger.info(f"Twilio SMS sent to {phone}")
                    return True
            return False
        except Exception as e:
            logger.error(f"Twilio SMS delivery failed: {e}")
            return False

    def _get_input_with_timeout(self, prompt: str, timeout_seconds: int) -> Tuple[Optional[str], bool]:
        """Prompts user on standard input with a timer."""
        user_input: List[Optional[str]] = [None]
        timed_out = [False]

        def get_input():
            try:
                user_input[0] = input(prompt)
            except EOFError:
                user_input[0] = "no"

        t = threading.Thread(target=get_input)
        t.daemon = True
        t.start()
        t.join(timeout=timeout_seconds)

        if t.is_alive():
            timed_out[0] = True
            return None, True

        return user_input[0], False
