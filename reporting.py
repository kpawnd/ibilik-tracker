"""
Reporting module for generating investigation summaries.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional
from config import Config
from database import MeterDatabase

logger = logging.getLogger(__name__)


class ReportGenerator:
    """Generates investigation reports from stored anomaly data."""

    def __init__(self, config: Config, database: MeterDatabase):
        self.config = config
        self.database = database

    def generate_report(self, meter_id: Optional[str] = None, days: Optional[int] = None,
                        limit: Optional[int] = None) -> str:
        """
        Generate a text report of anomalies within a time window.
        """
        days = days if days is not None else self.config.report_default_days
        limit = limit if limit is not None else self.config.report_max_events

        end_time = datetime.now()
        start_time = end_time - timedelta(days=days)

        events = self.database.get_anomaly_events(
            meter_id=meter_id,
            start_time=start_time.isoformat(),
            end_time=end_time.isoformat(),
            limit=limit
        )

        header = f"INVESTIGATION REPORT - {end_time.isoformat()}"
        lines = [header, "=" * len(header)]

        if meter_id:
            lines.append(f"Meter ID: {meter_id}")

        lines.append(f"Window: {start_time.isoformat()} to {end_time.isoformat()}")
        lines.append(f"Anomaly events: {len(events)} (max {limit})")
        lines.append("")

        if not events:
            lines.append("No anomalies found in this window.")
            return "\n".join(lines)

        for index, event in enumerate(events, 1):
            anomalies = event.get("anomalies") or {}
            anomaly_keys = ", ".join(sorted(anomalies.keys())) if anomalies else "None"

            lines.append(f"{index}. Meter {event.get('meter_id')} | {event.get('local_timestamp')}")
            lines.append(f"   Anomalies: {anomaly_keys}")
            lines.append(
                f"   Reading: {event.get('current_reading')} | Balance: {event.get('balance_unit')}"
            )

            unit_price = event.get("unit_price")
            if unit_price is not None:
                currency = event.get("currency") or ""
                lines.append(f"   Unit price: {unit_price}{currency}")

            if event.get("current_reading_delta") is not None or event.get("balance_unit_delta") is not None:
                lines.append(
                    f"   Deltas: reading={event.get('current_reading_delta')} "
                    f"balance={event.get('balance_unit_delta')}"
                )

            reconciliation = event.get("reconciliation") or {}
            balance_info = reconciliation.get("balance") or {}
            price_info = reconciliation.get("price") or {}

            if balance_info.get("within_tolerance") is False:
                lines.append(
                    f"   Balance mismatch: {balance_info.get('mismatch')} "
                    f"(expected {balance_info.get('expected_delta')}, "
                    f"actual {balance_info.get('actual_delta')})"
                )

            if price_info.get("within_tolerance") is False:
                lines.append(
                    f"   Price mismatch: avg_tx={price_info.get('avg_transaction_unit_price')} "
                    f"unit_price={price_info.get('unit_price')}"
                )

            lines.append("")

        return "\n".join(lines)
