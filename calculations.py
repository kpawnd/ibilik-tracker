"""
Calculations module for the electricity meter monitoring system.

This module handles delta computations, numeric processing, and mathematical
operations on meter data while maintaining the principle of not interpreting
units or performing conversions.
"""

import logging
from typing import Optional, Dict, Any
from data_model import MeterSnapshot

logger = logging.getLogger(__name__)


class MeterCalculations:
    """
    Handles calculations on meter data, primarily delta computations.

    This class provides methods for computing differences between meter readings
    and other numeric operations while preserving raw data integrity.
    """

    @staticmethod
    def compute_reading_delta(current_value: Any, previous_value: Any) -> Optional[float]:
        """
        Compute the delta between two reading values.

        Args:
            current_value: Current reading value
            previous_value: Previous reading value

        Returns:
            The delta value, or None if computation is not possible
        """
        try:
            # Only compute delta if both values are numeric
            if isinstance(current_value, (int, float)) and isinstance(previous_value, (int, float)):
                return float(current_value) - float(previous_value)
            return None
        except (ValueError, TypeError, OverflowError) as e:
            logger.warning(f"Could not compute reading delta: {e}")
            return None

    @staticmethod
    def compute_balance_delta(current_balance: Any, previous_balance: Any) -> Optional[float]:
        """
        Compute the delta between two balance values.
        """
        try:
            # Only compute delta if both values are numeric
            if isinstance(current_balance, (int, float)) and isinstance(previous_balance, (int, float)):
                return float(current_balance) - float(previous_balance)
            return None
        except (ValueError, TypeError, OverflowError) as e:
            logger.warning(f"Could not compute balance delta: {e}")
            return None

    @staticmethod
    def validate_numeric_field(value: Any, field_name: str) -> Optional[float]:
        """
        Validate and convert a value to float if it's numeric.
        """
        try:
            if isinstance(value, (int, float)):
                return float(value)
            elif isinstance(value, str):
                # Try to parse string as number
                return float(value.strip())
            else:
                logger.debug(f"Field '{field_name}' is not numeric: {type(value)}")
                return None
        except (ValueError, TypeError) as e:
            logger.debug(f"Could not validate numeric field '{field_name}': {e}")
            return None

    @staticmethod
    def detect_anomalies(
        snapshot: MeterSnapshot,
        previous_snapshot: Optional[MeterSnapshot] = None,
        thresholds: Optional[Dict[str, Any]] = None,
        reconciliation: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Detect potential anomalies in meter data without making assumptions about normal behavior.
        """
        anomalies: Dict[str, Any] = {}
        thresholds = thresholds or {}
        max_reading_delta = thresholds.get("max_reading_delta", 1000)
        max_balance_delta = thresholds.get("max_balance_delta", 1000)
        price_change_tolerance = thresholds.get("price_change_tolerance", 0.05)
        balance_recon_tolerance = thresholds.get("balance_reconciliation_tolerance", 0.5)

        if not snapshot.poll_successful:
            return anomalies  # Don't detect anomalies on failed polls

        # Check for non-monotonic readings (readings that go backwards)
        if previous_snapshot and snapshot.current_reading_delta is not None:
            if snapshot.current_reading_delta < 0:
                anomalies["non_monotonic_reading"] = {
                    "current": snapshot.get_current_reading(),
                    "previous": previous_snapshot.get_current_reading(),
                    "delta": snapshot.current_reading_delta
                }

        # Check for extreme delta values
        if snapshot.current_reading_delta is not None:
            if abs(snapshot.current_reading_delta) > max_reading_delta:
                anomalies["extreme_reading_delta"] = {
                    "delta": snapshot.current_reading_delta,
                    "threshold": max_reading_delta
                }

        if snapshot.balance_unit_delta is not None:
            if abs(snapshot.balance_unit_delta) > max_balance_delta:
                anomalies["extreme_balance_delta"] = {
                    "delta": snapshot.balance_unit_delta,
                    "threshold": max_balance_delta
                }

        # Check for unit price changes between polls
        if previous_snapshot and snapshot.unit_price is not None and previous_snapshot.unit_price is not None:
            previous_price = previous_snapshot.unit_price
            if previous_price != 0:
                price_change = snapshot.unit_price - previous_price
                price_change_ratio = abs(price_change) / abs(previous_price)
                if price_change_ratio > price_change_tolerance:
                    anomalies["unit_price_change"] = {
                        "current": snapshot.unit_price,
                        "previous": previous_price,
                        "delta": price_change,
                        "change_ratio": price_change_ratio,
                        "tolerance": price_change_tolerance
                    }

        # Check for connectivity changes
        if previous_snapshot:
            current_online = snapshot.is_online
            previous_online = previous_snapshot.is_online
            if current_online is not None and previous_online is not None and current_online != previous_online:
                anomalies["online_status_change"] = {
                    "from": previous_online,
                    "to": current_online
                }

            current_connected = snapshot.is_connected
            previous_connected = previous_snapshot.is_connected
            if current_connected is not None and previous_connected is not None and current_connected != previous_connected:
                anomalies["connection_status_change"] = {
                    "from": previous_connected,
                    "to": current_connected
                }

            current_active = snapshot.is_active
            previous_active = previous_snapshot.is_active
            if current_active is not None and previous_active is not None and current_active != previous_active:
                anomalies["active_status_change"] = {
                    "from": previous_active,
                    "to": current_active
                }

        # Reconciliation-based anomalies
        if reconciliation:
            balance_info = reconciliation.get("balance", {})
            if balance_info.get("within_tolerance") is False:
                anomalies["balance_reconciliation_mismatch"] = balance_info

            price_info = reconciliation.get("price", {})
            if price_info.get("within_tolerance") is False:
                anomalies["transaction_price_mismatch"] = price_info

            transactions = reconciliation.get("transactions", {})
            if snapshot.balance_unit_delta is not None and snapshot.balance_unit_delta > 0:
                if transactions.get("total_units", 0) == 0 and (snapshot.current_reading_delta is None or snapshot.current_reading_delta >= 0):
                    if snapshot.balance_unit_delta > balance_recon_tolerance:
                        anomalies["balance_increase_without_topup"] = {
                            "balance_delta": snapshot.balance_unit_delta,
                            "tolerance": balance_recon_tolerance
                        }

        return anomalies

    @staticmethod
    def compute_reconciliation(
        snapshot: MeterSnapshot,
        previous_snapshot: Optional[MeterSnapshot],
        tx_summary: Dict[str, Any],
        thresholds: Optional[Dict[str, Any]] = None,
        window_reading_start: Optional[float] = None,
        window_balance_start: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Compute reconciliation details between meter deltas and transactions.

        window_reading_start / window_balance_start are the meter values at the
        beginning of the current reconciliation window.  When provided they are
        used to compute window-level deltas so the energy-consumed estimate
        covers the same time span as the fetched transactions.  Without them the
        check falls back to the single-poll delta, which produces false anomalies
        because a 15-second consumption is compared against an hour of top-ups.
        """
        thresholds = thresholds or {}
        balance_tolerance = thresholds.get("balance_reconciliation_tolerance", 0.5)
        price_tolerance = thresholds.get("price_reconciliation_tolerance", 0.05)

        analysis = tx_summary.get("analysis", {})
        unit_price_stats = analysis.get("unit_price_stats", {})

        current_reading = snapshot.get_current_reading()
        current_balance = snapshot.get_balance_unit()

        # Prefer window-level deltas; fall back to single-poll deltas only when
        # no window baseline has been established yet (first reconciliation run).
        if window_reading_start is not None and current_reading is not None:
            window_reading_delta: Optional[float] = current_reading - window_reading_start
        else:
            window_reading_delta = snapshot.current_reading_delta

        if window_balance_start is not None and current_balance is not None:
            window_balance_delta: Optional[float] = current_balance - window_balance_start
        else:
            window_balance_delta = snapshot.balance_unit_delta

        result: Dict[str, Any] = {
            "window_start": tx_summary.get("window_start"),
            "window_end": tx_summary.get("window_end"),
            "transactions": {
                "count": analysis.get("total_transactions", 0),
                "total_units": analysis.get("total_units", 0),
                "total_amount": analysis.get("total_amount", 0),
                "unit_price_stats": unit_price_stats
            },
            "snapshot": {
                "current_reading": current_reading,
                "balance_unit": current_balance,
                "unit_price": snapshot.unit_price,
                "window_reading_delta": window_reading_delta,
                "window_balance_delta": window_balance_delta,
            }
        }

        topup_units = analysis.get("total_units", 0)

        if window_reading_delta is not None:
            expected_balance_delta = -window_reading_delta + topup_units
        else:
            expected_balance_delta = None

        if expected_balance_delta is not None and window_balance_delta is not None:
            mismatch = window_balance_delta - expected_balance_delta
            mismatch_abs = abs(mismatch)
            result["balance"] = {
                "expected_delta": expected_balance_delta,
                "actual_delta": window_balance_delta,
                "mismatch": mismatch,
                "mismatch_abs": mismatch_abs,
                "tolerance": balance_tolerance,
                "within_tolerance": mismatch_abs <= balance_tolerance
            }
        else:
            result["balance"] = {"status": "insufficient_data"}

        unit_price = snapshot.unit_price
        avg_tx_price = unit_price_stats.get("avg_unit_price")

        if unit_price is not None and avg_tx_price is not None and unit_price != 0:
            price_diff = avg_tx_price - unit_price
            price_diff_ratio = abs(price_diff) / abs(unit_price)
            result["price"] = {
                "unit_price": unit_price,
                "avg_transaction_unit_price": avg_tx_price,
                "diff": price_diff,
                "diff_ratio": price_diff_ratio,
                "tolerance": price_tolerance,
                "within_tolerance": price_diff_ratio <= price_tolerance
            }
        else:
            result["price"] = {"status": "insufficient_data"}

        return result

    @staticmethod
    def compute_statistics(meter_id: str, snapshots: list[MeterSnapshot]) -> Dict[str, Any]:
        """
        Compute basic statistics for a series of snapshots.
        """
        if not snapshots:
            return {"meter_id": meter_id, "error": "No snapshots provided"}

        successful_snapshots = [s for s in snapshots if s.poll_successful]

        if not successful_snapshots:
            return {"meter_id": meter_id, "error": "No successful snapshots"}

        stats = {
            "meter_id": meter_id,
            "total_snapshots": len(snapshots),
            "successful_snapshots": len(successful_snapshots),
            "success_rate": len(successful_snapshots) / len(snapshots),
            "time_range": {
                "start": min(s.local_timestamp for s in successful_snapshots),
                "end": max(s.local_timestamp for s in successful_snapshots)
            }
        }

        # Reading statistics
        readings = [s.get_current_reading() for s in successful_snapshots if s.get_current_reading() is not None]
        if readings:
            stats["reading_stats"] = {
                "min": min(readings),
                "max": max(readings),
                "current": readings[-1] if readings else None
            }

        # Balance statistics
        balances = [s.get_balance_unit() for s in successful_snapshots if s.get_balance_unit() is not None]
        if balances:
            stats["balance_stats"] = {
                "min": min(balances),
                "max": max(balances),
                "current": balances[-1] if balances else None
            }

        # Delta statistics
        reading_deltas = [s.current_reading_delta for s in successful_snapshots if s.current_reading_delta is not None]
        if reading_deltas:
            stats["reading_delta_stats"] = {
                "total_change": sum(reading_deltas),
                "average_change": sum(reading_deltas) / len(reading_deltas),
                "min_delta": min(reading_deltas),
                "max_delta": max(reading_deltas)
            }

        balance_deltas = [s.balance_unit_delta for s in successful_snapshots if s.balance_unit_delta is not None]
        if balance_deltas:
            stats["balance_delta_stats"] = {
                "total_change": sum(balance_deltas),
                "average_change": sum(balance_deltas) / len(balance_deltas),
                "min_delta": min(balance_deltas),
                "max_delta": max(balance_deltas)
            }

        return stats

    @staticmethod
    def summarize_daily_usage(
        daily_usage: list[Dict[str, Any]],
        spike_multiplier: float = 2.0
    ) -> Dict[str, Any]:
        """Summarize daily usage totals for a chart window."""
        if not daily_usage:
            return {
                "total": 0,
                "average": 0,
                "highest": None,
                "lowest": None,
                "spikes": []
            }

        values = [entry.get("usage", 0) or 0 for entry in daily_usage]
        total = sum(values)
        average = total / len(values) if values else 0
        highest_entry = max(daily_usage, key=lambda entry: entry.get("usage", 0) or 0)
        lowest_entry = min(daily_usage, key=lambda entry: entry.get("usage", 0) or 0)

        spikes = []
        if average > 0:
            spikes = [
                entry
                for entry in daily_usage
                if (entry.get("usage", 0) or 0) >= average * spike_multiplier
            ]

        return {
            "total": total,
            "average": average,
            "highest": highest_entry,
            "lowest": lowest_entry,
            "spikes": spikes
        }