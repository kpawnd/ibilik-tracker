"""
Main entry point for the iBilik tracker.
"""

from __future__ import annotations

import argparse
import asyncio

from config import Config
from logging_utils import setup_logging
from service import MonitoringService
from tui_app import MonitorApp


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(description="iBilik Tracker")
    parser.add_argument(
        "--service",
        action="store_true",
        help="Run the background monitoring service"
    )
    parser.add_argument(
        "--no-service",
        action="store_true",
        help="Run the TUI without starting the background service"
    )
    return parser


async def run_service() -> None:
    """Run the monitoring service in the foreground."""
    config = Config()
    setup_logging(config)
    service = MonitoringService(config)
    try:
        await service.run()
    finally:
        await service.stop()


def run_tui(start_service: bool) -> None:
    """Run the Textual TUI."""
    config = Config()
    setup_logging(config, console=False)
    app = MonitorApp(config, start_service=start_service)
    app.run()


def main() -> None:
    """Program entry point."""
    parser = build_parser()
    args = parser.parse_args()

    if args.service:
        asyncio.run(run_service())
    else:
        run_tui(start_service=not args.no_service)


if __name__ == "__main__":
    main()
