"""
Alert delivery helpers for low-balance reminders.
"""

from __future__ import annotations

import logging
from typing import Iterable
import aiohttp
from data_model import MeterSnapshot

logger = logging.getLogger(__name__)


class AlertManager:
    """Send alert messages to configured webhook endpoints."""

    @staticmethod
    def format_low_balance(snapshot: MeterSnapshot, threshold: float) -> str:
        """Format a low-balance reminder message."""
        meter_name = snapshot.meter_name or snapshot.meter_id
        balance = snapshot.get_balance_unit()
        unit_price = snapshot.unit_price
        currency = snapshot.currency or ""
        balance_text = f"{balance:.2f}" if isinstance(balance, (int, float)) else "unknown"
        price_text = f"{unit_price:.4f}" if isinstance(unit_price, (int, float)) else "unknown"

        return (
            "Low balance alert\n"
            f"Meter: {meter_name} ({snapshot.meter_id})\n"
            f"Balance: {balance_text} units\n"
            f"Threshold: {threshold} units\n"
            f"Unit price: {price_text} {currency}".strip()
        )

    async def send_webhooks(self, message: str, webhooks: Iterable[str]) -> None:
        """Send message payloads to webhooks."""
        payload = {"content": message}
        async with aiohttp.ClientSession() as session:
            for url in webhooks:
                try:
                    async with session.post(url, json=payload, timeout=10) as response:
                        if response.status >= 400:
                            logger.warning("Webhook %s responded with %s", url, response.status)
                except Exception as exc:  # pragma: no cover - network variability
                    logger.warning("Failed to deliver webhook %s: %s", url, exc)
