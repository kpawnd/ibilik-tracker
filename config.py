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

    def get_raw_config(self) -> Dict[str, Any]:
        """Get the raw configuration dictionary."""
        return self._config.copy()