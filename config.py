"""
Configuration module for the electricity meter monitoring system.

This module is responsible for loading configuration from config.json,
validating required fields, and providing a centralized configuration object.
"""

import json
import os
from typing import Dict, Any


class Config:
    """Configuration class that loads and validates settings from config.json."""

    def __init__(self, config_path: str = "config.json"):
        self.config_path = config_path
        self._config: Dict[str, Any] = {}
        self.load_config()

    def load_config(self) -> None:
        """Load configuration from JSON file and validate required fields."""
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")

        with open(self.config_path, 'r', encoding='utf-8') as f:
            self._config = json.load(f)

        self.validate_config()

    def validate_config(self) -> None:
        """Validate that all required configuration fields are present."""
        required_fields = [
            "api.base_url",
            "api.merchant_token",
            "api.user_agent",
            "api.origin",
            "api.referer",
            "polling.interval_seconds",
            "database.path",
            "logging.level"
        ]

        for field in required_fields:
            keys = field.split('.')
            value = self._config
            try:
                for key in keys:
                    value = value[key]
                if value is None or (isinstance(value, str) and not value.strip()):
                    raise ValueError(f"Required field '{field}' is empty or null")
            except (KeyError, TypeError):
                raise ValueError(f"Required field '{field}' is missing from configuration")

    @property
    def api_base_url(self) -> str:
        """Get the API base URL."""
        return self._config["api"]["base_url"]

    @property
    def merchant_token(self) -> str:
        """Get the merchant authentication token."""
        return self._config["api"]["merchant_token"]

    @property
    def user_agent(self) -> str:
        """Get the user agent string."""
        return self._config["api"]["user_agent"]

    @property
    def origin(self) -> str:
        """Get the origin header value."""
        return self._config["api"]["origin"]

    @property
    def referer(self) -> str:
        """Get the referer header value."""
        return self._config["api"]["referer"]

    @property
    def discovery_endpoint(self) -> str:
        """Get the API endpoint for meter discovery."""
        return self._config["api"].get("discovery_endpoint", "/merchant/meters")

    @property
    def status_method(self) -> str:
        """Get the HTTP method for meter status requests."""
        return self._config["api"].get("status_method", "GET")

    @property
    def polling_interval(self) -> int:
        """Get the polling interval in seconds."""
        return self._config["polling"]["interval_seconds"]

    @property
    def polling_overrides(self) -> Dict[str, int]:
        """Get per-meter polling interval overrides."""
        return self._config.get("polling", {}).get("per_meter_overrides", {})

    @property
    def database_path(self) -> str:
        """Get the database file path."""
        return self._config["database"]["path"]

    @property
    def log_level(self) -> str:
        """Get the logging level."""
        return self._config["logging"]["level"]

    @property
    def log_file(self) -> str:
        """Get the log file path (optional)."""
        return self._config.get("logging", {}).get("file")

    @property
    def manual_meter_ids(self) -> list[str]:
        """Get manually configured meter IDs."""
        return self._config.get("meters", {}).get("manual_ids", [])

    @property
    def anomaly_max_reading_delta(self) -> float:
        """Get the maximum allowed reading delta before flagging."""
        return float(self._config.get("anomalies", {}).get("max_reading_delta", 1000))

    @property
    def anomaly_max_balance_delta(self) -> float:
        """Get the maximum allowed balance delta before flagging."""
        return float(self._config.get("anomalies", {}).get("max_balance_delta", 1000))

    @property
    def anomaly_price_change_tolerance(self) -> float:
        """Get the tolerance for unit price changes between polls."""
        return float(self._config.get("anomalies", {}).get("price_change_tolerance", 0.05))

    @property
    def anomaly_balance_reconciliation_tolerance(self) -> float:
        """Get the tolerance for balance reconciliation mismatches."""
        return float(self._config.get("anomalies", {}).get("balance_reconciliation_tolerance", 0.5))

    @property
    def anomaly_price_reconciliation_tolerance(self) -> float:
        """Get the tolerance for transaction price mismatches."""
        return float(self._config.get("anomalies", {}).get("price_reconciliation_tolerance", 0.05))

    @property
    def reconciliation_enabled(self) -> bool:
        """Return whether reconciliation checks are enabled."""
        return bool(self._config.get("reconciliation", {}).get("enabled", False))

    @property
    def reconciliation_interval_minutes(self) -> int:
        """Get reconciliation interval in minutes."""
        return int(self._config.get("reconciliation", {}).get("interval_minutes", 60))

    @property
    def reconciliation_lookback_days(self) -> int:
        """Get reconciliation lookback period in days."""
        return int(self._config.get("reconciliation", {}).get("lookback_days", 7))

    @property
    def report_default_days(self) -> int:
        """Get default reporting window in days."""
        return int(self._config.get("reporting", {}).get("default_days", 7))

    @property
    def report_max_events(self) -> int:
        """Get maximum number of report events to display."""
        return int(self._config.get("reporting", {}).get("max_events", 200))

    @property
    def reminders_enabled(self) -> bool:
        """Return whether low-balance reminders are enabled."""
        return bool(self._config.get("reminders", {}).get("enabled", True))

    @property
    def reminders_low_balance_threshold(self) -> float:
        """Get low-balance threshold for reminders."""
        return float(self._config.get("reminders", {}).get("low_balance_threshold", 40))

    @property
    def reminders_cooldown_minutes(self) -> int:
        """Get reminder cooldown in minutes."""
        return int(self._config.get("reminders", {}).get("cooldown_minutes", 120))

    @property
    def reminders_webhooks(self) -> list[str]:
        """Get webhook endpoints to deliver reminders."""
        return list(self._config.get("reminders", {}).get("webhooks", []))

    @property
    def usage_window_days(self) -> int:
        """Get the number of days to include in usage charts."""
        return int(self._config.get("usage", {}).get("window_days", 7))

    @property
    def usage_spike_multiplier(self) -> float:
        """Get the multiplier for usage spike detection."""
        return float(self._config.get("usage", {}).get("spike_multiplier", 2.0))

    @property
    def tui_refresh_seconds(self) -> int:
        """Get the refresh interval for the TUI."""
        return int(self._config.get("tui", {}).get("refresh_seconds", 5))

    def get_raw_config(self) -> Dict[str, Any]:
        """Get the raw configuration dictionary."""
        return self._config.copy()