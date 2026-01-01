"""
Tracker module for the electricity meter monitoring system.

This module maintains the previous state for each meter and handles
delta computation and state management.
"""

import logging
from typing import Dict, Optional, Any
from data_model import MeterSnapshot

logger = logging.getLogger(__name__)


class MeterTracker:
    """
    Tracks the state of individual meters and computes deltas between polls.

    This class maintains the most recent successful snapshot for each meter
    to enable delta calculations and state comparisons.
    """

    def __init__(self):
        # Dictionary mapping meter_id to the most recent successful snapshot
        self._previous_snapshots: Dict[str, MeterSnapshot] = {}

    def update_meter_state(self, snapshot: MeterSnapshot) -> MeterSnapshot:
        """
        Update the tracker with a new snapshot and compute deltas.

        Args:
            snapshot: The new meter snapshot

        Returns:
            The snapshot with computed deltas (modified in-place)
        """
        meter_id = snapshot.meter_id

        # Get the previous snapshot for this meter
        previous_snapshot = self._previous_snapshots.get(meter_id)

        # Compute deltas if we have a previous snapshot
        if previous_snapshot and snapshot.poll_successful:
            snapshot._compute_deltas(previous_snapshot)

            # Log significant changes
            if snapshot.current_reading_delta is not None and snapshot.current_reading_delta != 0:
                logger.info(f"Meter {meter_id}: current_reading changed by {snapshot.current_reading_delta}")

            if snapshot.balance_unit_delta is not None and snapshot.balance_unit_delta != 0:
                logger.info(f"Meter {meter_id}: balance_unit changed by {snapshot.balance_unit_delta}")

        # Update the stored previous snapshot only if this poll was successful
        if snapshot.poll_successful:
            self._previous_snapshots[meter_id] = snapshot

        return snapshot

    def get_previous_snapshot(self, meter_id: str) -> Optional[MeterSnapshot]:
        """
        Get the most recent successful snapshot for a meter.

        Args:
            meter_id: The meter identifier

        Returns:
            The previous snapshot, or None if no previous data exists
        """
        return self._previous_snapshots.get(meter_id)

    def remove_meter(self, meter_id: str) -> None:
        """
        Remove a meter from tracking (e.g., when it's no longer available).

        Args:
            meter_id: The meter identifier to remove
        """
        if meter_id in self._previous_snapshots:
            del self._previous_snapshots[meter_id]
            logger.info(f"Removed meter {meter_id} from tracking")

    def get_tracked_meters(self) -> list[str]:
        """
        Get a list of all currently tracked meter IDs.

        Returns:
            List of meter IDs being tracked
        """
        return list(self._previous_snapshots.keys())

    def get_meter_stats(self, meter_id: str) -> Optional[Dict[str, Any]]:
        """
        Get statistics for a tracked meter.

        Args:
            meter_id: The meter identifier

        Returns:
            Dictionary with meter statistics, or None if meter not tracked
        """
        previous = self.get_previous_snapshot(meter_id)
        if not previous:
            return None

        return {
            "meter_id": meter_id,
            "meter_name": previous.meter_name,
            "last_reading": previous.get_current_reading(),
            "last_balance": previous.get_balance_unit(),
            "last_poll_time": previous.local_timestamp.isoformat(),
            "is_online": previous.is_online()
        }