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
    vendor_meter_id: Optional[int] = None

    # Timestamp information
    local_timestamp: datetime = field(default_factory=datetime.now)
    api_timestamp: Optional[str] = None
    last_connected_at: Optional[str] = None

    # Raw meter data from API (all fields stored verbatim)
    raw_data: Dict[str, Any] = field(default_factory=dict)

    # Energy & Balance data
    current_reading_delta: Optional[float] = None
    balance_unit_delta: Optional[float] = None

    # Financial data
    currency: Optional[str] = None
    unit_price: Optional[float] = None
    minimum_topup_unit: Optional[int] = None
    minimum_topup_price: Optional[float] = None
    free_unit: Optional[float] = None
    free_unit_refresh_at: Optional[str] = None

    # Balance alerts
    warning_at_unit: Optional[int] = None
    is_low_balance_notification_sent: Optional[bool] = None

    # Connectivity & Status
    is_online: Optional[bool] = None
    is_connected: Optional[bool] = None
    is_active: Optional[bool] = None

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
            vendor_meter_id=api_response.get("vendor_meter_id"),
            api_timestamp=api_response.get("updated_at"),
            last_connected_at=api_response.get("last_connected_at"),
            raw_data=api_response.copy(),
            # Financial data
            currency=api_response.get("currency"),
            unit_price=api_response.get("unit_price"),
            minimum_topup_unit=api_response.get("minimum_topup_unit"),
            minimum_topup_price=api_response.get("minimum_topup_price"),
            free_unit=api_response.get("free_unit"),
            free_unit_refresh_at=api_response.get("free_unit_refresh_at"),
            # Balance alerts
            warning_at_unit=api_response.get("warning_at_unit"),
            is_low_balance_notification_sent=api_response.get("is_low_balance_notification_sent"),
            # Status
            is_online=api_response.get("is_online"),
            is_connected=api_response.get("is_connected"),
            is_active=api_response.get("is_active"),
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

    def get_connectivity_status(self) -> str:
        """Get a human-readable connectivity status."""
        if not self.poll_successful:
            return "OFFLINE (poll failed)"
        
        online_status = "ONLINE" if self.is_online else "OFFLINE"
        connected_status = "CONNECTED" if self.is_connected else "DISCONNECTED"
        
        return f"{online_status} - {connected_status}"

    def get_cost_estimate(self) -> Optional[float]:
        """Calculate estimated cost for current reading based on unit price."""
        reading = self.get_current_reading()
        price = self.unit_price
        
        if reading is not None and price is not None:
            return reading * price
        return None

    def get_balance_cost(self) -> Optional[float]:
        """Calculate cost value of remaining balance."""
        balance = self.get_balance_unit()
        price = self.unit_price
        
        if balance is not None and price is not None:
            return balance * price
        return None

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the snapshot to a dictionary for database storage.

        Returns:
            Dictionary representation suitable for database insertion
        """
        return {
            "meter_id": self.meter_id,
            "meter_name": self.meter_name,
            "vendor_meter_id": self.vendor_meter_id,
            "local_timestamp": self.local_timestamp.isoformat(),
            "api_timestamp": self.api_timestamp,
            "last_connected_at": self.last_connected_at,
            "raw_data": self.raw_data,
            "current_reading_delta": self.current_reading_delta,
            "balance_unit_delta": self.balance_unit_delta,
            "currency": self.currency,
            "unit_price": self.unit_price,
            "minimum_topup_unit": self.minimum_topup_unit,
            "minimum_topup_price": self.minimum_topup_price,
            "free_unit": self.free_unit,
            "free_unit_refresh_at": self.free_unit_refresh_at,
            "warning_at_unit": self.warning_at_unit,
            "is_low_balance_notification_sent": self.is_low_balance_notification_sent,
            "is_online": self.is_online,
            "is_connected": self.is_connected,
            "is_active": self.is_active,
            "poll_successful": self.poll_successful,
            "error_message": self.error_message,
            "connectivity_status": self.get_connectivity_status() if self.poll_successful else "ERROR"
        }