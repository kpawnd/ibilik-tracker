"""
Logging utilities for the monitoring service and TUI.
"""

from __future__ import annotations

import logging
import os
from config import Config


def setup_logging(config: Config, console: bool = True) -> None:
    """Configure logging with optional file output."""
    level = getattr(logging, config.log_level.upper(), logging.INFO)
    handlers: list[logging.Handler] = []

    if console:
        handlers.append(logging.StreamHandler())

    log_file = config.log_file
    if log_file:
        log_dir = os.path.dirname(log_file)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    if not handlers:
        handlers = [logging.NullHandler()]

    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=handlers,
        force=True
    )
