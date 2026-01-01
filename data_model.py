"""
Data model module for the electricity meter monitoring system.

This module defines structured representations of meter snapshots and related data.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional
from datetime import datetime


@dataclass
class MeterSnapshot:
    """
    Represents a complete snapshot of meter data at a specific point in time.

    This class stores all raw data from the API without transformation or interpretation.
    """
    # Core identifiers
    meter_id: str
    meter_name: Optional[str] = None

    # Timestamp information
    local_timestamp: datetime = field(default_factory=datetime.now)
    api_timestamp: Optional[str] = None

    # Raw meter data from API (all fields stored verbatim)
    raw_data: Dict[str, Any] = field(default_factory=dict)

    # Computed deltas for numeric fields
    current_reading_delta: Optional[float] = None
    balance_unit_delta: Optional[float] = None

    # Metadata
    poll_successful: bool = True
    error_message: Optional[str] = None

    @classmethod
    def from_api_response(cls, meter_id: str, api_response: Dict[str, Any],
                         previous_snapshot: Optional['MeterSnapshot'] = None) -> 'MeterSnapshot':
        """
        Create a MeterSnapshot from API response data.

        Args:
            meter_id: The meter identifier
            api_response: Raw response from the API
            previous_snapshot: Previous snapshot for delta calculation

        Returns:
            New MeterSnapshot instance
        """
        snapshot = cls(
            meter_id=meter_id,
            meter_name=api_response.get("name"),
            api_timestamp=api_response.get("timestamp"),
            raw_data=api_response.copy()
        )

        # Compute deltas if we have a previous snapshot
        if previous_snapshot:
            snapshot._compute_deltas(previous_snapshot)

        return snapshot

    @classmethod
    def create_error_snapshot(cls, meter_id: str, error_message: str) -> 'MeterSnapshot':
        """
        Create a snapshot representing a failed poll.

        Args:
            meter_id: The meter identifier
            error_message: Description of the error

        Returns:
            Error MeterSnapshot instance
        """
        return cls(
            meter_id=meter_id,
            poll_successful=False,
            error_message=error_message
        )

    def _compute_deltas(self, previous: 'MeterSnapshot') -> None:
        """
        Compute deltas for numeric fields compared to previous snapshot.

        Args:
            previous: The previous meter snapshot
        """
        # Compute delta for current_reading if both values are numeric
        current_reading = self.raw_data.get("current_reading")
        prev_reading = previous.raw_data.get("current_reading")

        if isinstance(current_reading, (int, float)) and isinstance(prev_reading, (int, float)):
            self.current_reading_delta = current_reading - prev_reading

        # Compute delta for balance_unit if both values are numeric
        balance_unit = self.raw_data.get("balance_unit")
        prev_balance = previous.raw_data.get("balance_unit")

        if isinstance(balance_unit, (int, float)) and isinstance(prev_balance, (int, float)):
            self.balance_unit_delta = balance_unit - prev_balance

    def get_current_reading(self) -> Optional[float]:
        """Get the current reading value."""
        value = self.raw_data.get("current_reading")
        return float(value) if isinstance(value, (int, float)) else None

    def get_balance_unit(self) -> Optional[float]:
        """Get the balance unit value."""
        value = self.raw_data.get("balance_unit")
        return float(value) if isinstance(value, (int, float)) else None

    def is_online(self) -> bool:
        """Check if the meter appears to be online based on available data."""
        # This is a simple heuristic - could be based on connectivity flags in raw_data
        connectivity = self.raw_data.get("connectivity", {}).get("online", True)
        return bool(connectivity) if self.poll_successful else False

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the snapshot to a dictionary for database storage.

        Returns:
            Dictionary representation suitable for database insertion
        """
        return {
            "meter_id": self.meter_id,
            "meter_name": self.meter_name,
            "local_timestamp": self.local_timestamp.isoformat(),
            "api_timestamp": self.api_timestamp,
            "raw_data": self.raw_data,
            "current_reading_delta": self.current_reading_delta,
            "balance_unit_delta": self.balance_unit_delta,
            "poll_successful": self.poll_successful,
            "error_message": self.error_message,
            "is_online": self.is_online()
        }