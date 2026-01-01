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

        Args:
            current_balance: Current balance value
            previous_balance: Previous balance value

        Returns:
            The delta value, or None if computation is not possible
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

        Args:
            value: The value to validate
            field_name: Name of the field (for logging)

        Returns:
            Float value if valid, None otherwise
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
    def detect_anomalies(snapshot: MeterSnapshot, previous_snapshot: Optional[MeterSnapshot] = None) -> Dict[str, Any]:
        """
        Detect potential anomalies in meter data without making assumptions about normal behavior.

        Args:
            snapshot: Current meter snapshot
            previous_snapshot: Previous snapshot for comparison

        Returns:
            Dictionary of detected anomalies
        """
        anomalies = {}

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

        # Check for extreme delta values (arbitrarily large changes)
        if snapshot.current_reading_delta is not None:
            # Flag if delta is more than 1000 units (arbitrary threshold)
            if abs(snapshot.current_reading_delta) > 1000:
                anomalies["extreme_reading_delta"] = {
                    "delta": snapshot.current_reading_delta,
                    "threshold": 1000
                }

        if snapshot.balance_unit_delta is not None:
            # Flag if balance changes by more than 1000 units
            if abs(snapshot.balance_unit_delta) > 1000:
                anomalies["extreme_balance_delta"] = {
                    "delta": snapshot.balance_unit_delta,
                    "threshold": 1000
                }

        # Check for connectivity changes
        if previous_snapshot:
            current_online = snapshot.is_online()
            previous_online = previous_snapshot.is_online()
            if current_online != previous_online:
                anomalies["connectivity_change"] = {
                    "from": previous_online,
                    "to": current_online
                }

        return anomalies

    @staticmethod
    def compute_statistics(meter_id: str, snapshots: list[MeterSnapshot]) -> Dict[str, Any]:
        """
        Compute basic statistics for a series of snapshots.

        Args:
            meter_id: The meter identifier
            snapshots: List of snapshots to analyze

        Returns:
            Dictionary with computed statistics
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