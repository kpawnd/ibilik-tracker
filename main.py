"""
Main entry point for the electricity meter monitoring system.

This module coordinates startup, meter selection, concurrent polling,
error handling, and console output.
"""

import asyncio
import logging
import signal
import sys
from typing import List, Dict, Any
from datetime import datetime

from config import Config
from api import APIClient
from discovery import MeterDiscovery
from data_model import MeterSnapshot
from tracker import MeterTracker
from database import MeterDatabase
from transactions import TransactionHistoryManager


class MeterMonitor:
    """Main monitoring system coordinator."""

    def __init__(self):
        self.config = Config()
        self.setup_logging()
        self.tracker = MeterTracker()
        self.database: MeterDatabase = None
        self.running = False
        self.monitoring_tasks: List[asyncio.Task] = []

    def setup_logging(self) -> None:
        """Configure logging based on configuration."""
        log_level = getattr(logging, self.config.log_level.upper(), logging.INFO)
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(sys.stdout),
                logging.FileHandler(self.config.log_file) if self.config.log_file else logging.NullHandler()
            ]
        )

    async def initialize(self) -> None:
        """Initialize the monitoring system."""
        logger = logging.getLogger(__name__)

        try:
            # Test API connection and authentication
            async with APIClient(self.config) as api_client:
                # Test with meter discovery to validate token
                try:
                    await api_client.get_meters()
                except Exception as auth_test_error:
                    # If it's an auth error, re-raise
                    if "401" in str(auth_test_error) or "403" in str(auth_test_error):
                        raise ValueError("Authentication failed - invalid merchant token") from auth_test_error
                    # For other errors (like 404 for discovery), auth is probably OK

            # Initialize database
            self.database = MeterDatabase(self.config)

        except Exception as e:
            logger.error(f"Initialization failed: {e}")
            raise

    async def select_meters(self) -> List[Dict[str, Any]]:
        """Handle meter discovery and selection."""
        logger = logging.getLogger(__name__)

        async with APIClient(self.config) as api_client:
            discovery = MeterDiscovery(self.config, api_client)
            selected_meters = await discovery.discover_and_select_meters()

            if not selected_meters:
                return []

            return selected_meters

    async def monitor_meter(self, meter: Dict[str, Any]) -> None:
        """
        Monitor a single meter by polling its status periodically.

        Args:
            meter: Meter information dictionary
        """
        logger = logging.getLogger(__name__)
        meter_id = meter.get("id")
        meter_name = meter.get("name", f"Meter {meter_id}")

        async with APIClient(self.config) as api_client:
            while self.running:
                try:
                    # Poll meter status
                    start_time = datetime.now()
                    meter_data = await api_client.get_meter_status(meter_id)

                    # Create snapshot
                    snapshot = MeterSnapshot.from_api_response(
                        meter_id,
                        meter_data,
                        self.tracker.get_previous_snapshot(meter_id)
                    )

                    # Update tracker (computes deltas)
                    self.tracker.update_meter_state(snapshot)

                    # Store in database
                    self.database.store_snapshot(snapshot)

                    # Log status
                    poll_time = (datetime.now() - start_time).total_seconds()
                    
                    # Build comprehensive status message
                    status = snapshot.get_connectivity_status()

                    # Build detailed status message
                    status_parts = [
                        f"{meter_name}",
                        f"Status: {status}",
                        f"Poll time: {poll_time:.2f}s",
                    ]

                    # Add meter identifier
                    if snapshot.vendor_meter_id:
                        status_parts.append(f"HW ID: {snapshot.vendor_meter_id}")

                    # Add energy reading and consumption cost
                    current_reading = snapshot.get_current_reading()
                    if current_reading is not None:
                        status_parts.append(f"Reading: {current_reading:.2f}")
                        cost_estimate = snapshot.get_cost_estimate()
                        if cost_estimate is not None and snapshot.currency:
                            status_parts.append(f"Cost: {cost_estimate:.2f}{snapshot.currency}")

                    # Add balance and cost of balance
                    balance_unit = snapshot.get_balance_unit()
                    if balance_unit is not None:
                        status_parts.append(f"Balance: {balance_unit:.2f}")
                        balance_cost = snapshot.get_balance_cost()
                        if balance_cost is not None and snapshot.currency:
                            status_parts.append(f"Balance $: {balance_cost:.2f}{snapshot.currency}")

                    # Add balance warning info if low
                    if snapshot.warning_at_unit and balance_unit is not None:
                        if balance_unit <= snapshot.warning_at_unit:
                            status_parts.append(f"⚠ LOW BALANCE (warn at {snapshot.warning_at_unit})")

                    # Add pricing information
                    if snapshot.unit_price and snapshot.currency:
                        status_parts.append(f"Price: {snapshot.unit_price}{snapshot.currency}/unit")

                    # Add delta information
                    delta_parts = []
                    if snapshot.current_reading_delta is not None and snapshot.current_reading_delta != 0:
                        delta_parts.append(f"ΔReading: {snapshot.current_reading_delta:+.2f}")
                    if snapshot.balance_unit_delta is not None and snapshot.balance_unit_delta != 0:
                        delta_parts.append(f"ΔBalance: {snapshot.balance_unit_delta:+.2f}")

                    if delta_parts:
                        status_parts.append(f"Changes: {' | '.join(delta_parts)}")

                    # Add last connection info
                    if snapshot.last_connected_at:
                        status_parts.append(f"Last conn: {snapshot.last_connected_at}")

                    # Print the comprehensive status
                    print(" | ".join(status_parts))

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    # Create error snapshot
                    error_snapshot = MeterSnapshot.create_error_snapshot(meter_id, str(e))
                    self.database.store_snapshot(error_snapshot)
                    print(f"{meter_name}: ERROR - {e}")

                # Wait for next poll
                try:
                    await asyncio.sleep(self.config.polling_interval)
                except asyncio.CancelledError:
                    break

        logger.info(f"Stopped monitoring for {meter_name}")

    async def start_monitoring(self, selected_meters: List[Dict[str, Any]]) -> None:
        """
        Start concurrent monitoring of selected meters.

        Args:
            selected_meters: List of meters to monitor
        """
        logger = logging.getLogger(__name__)

        if not selected_meters:
            logger.warning("No meters to monitor")
            return

        self.running = True

        # Store monitoring start metadata
        self.database.store_system_metadata("monitoring_start", {
            "timestamp": datetime.now().isoformat(),
            "meters": [m.get("id") for m in selected_meters]
        })

        # Create monitoring tasks
        self.monitoring_tasks = []
        for meter in selected_meters:
            task = asyncio.create_task(self.monitor_meter(meter))
            self.monitoring_tasks.append(task)

        # Set up signal handlers for graceful shutdown
        def signal_handler(signum, frame):
            self.running = False
            for task in self.monitoring_tasks:
                task.cancel()

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        try:
            # Wait for all monitoring tasks
            await asyncio.gather(*self.monitoring_tasks, return_exceptions=True)
        except asyncio.CancelledError:
            pass
        finally:
            # Store monitoring end metadata
            self.database.store_system_metadata("monitoring_end", {
                "timestamp": datetime.now().isoformat(),
                "reason": "shutdown"
            })

    async def run(self) -> None:
        """Main execution flow."""
        logger = logging.getLogger(__name__)

        try:
            print("Electricity Meter Monitoring System")
            print("=" * 40)

            # Initialize system
            await self.initialize()

            # Display main menu
            while True:
                print("\nMAIN MENU:")
                print("1. Start monitoring meters")
                print("2. View transaction history for a meter")
                print("3. Exit")

                choice = input("\nEnter your choice (1-3): ").strip()

                if choice == "1":
                    await self._run_monitoring()
                    break
                elif choice == "2":
                    await self._view_transaction_history()
                elif choice == "3":
                    print("Exiting...")
                    return
                else:
                    print("Invalid choice. Please enter 1-3")

        except KeyboardInterrupt:
            pass
        except Exception as e:
            print(f"Fatal error: {e}")
            raise
        finally:
            if self.database:
                self.database.close()

    async def _run_monitoring(self) -> None:
        """Run the meter monitoring."""
        logger = logging.getLogger(__name__)

        # Select meters to monitor
        selected_meters = await self.select_meters()

        if not selected_meters:
            print("No meters selected. Returning to menu.")
            return

        # Start monitoring
        await self.start_monitoring(selected_meters)

    async def _view_transaction_history(self) -> None:
        """View transaction history for a selected meter."""
        logger = logging.getLogger(__name__)

        try:
            async with APIClient(self.config) as api_client:
                # Get available meters
                meters = await api_client.get_meters()
                if not meters:
                    print("No meters found")
                    return

                # Display meter options
                print("\nAvailable meters:")
                for i, meter in enumerate(meters, 1):
                    meter_id = meter.get("id")
                    name = meter.get("name", "Unknown")
                    balance = meter.get("balance_unit", 0)
                    reading = meter.get("current_reading", 0)
                    print(f"{i}. {name} (ID: {meter_id})")
                    print(f"   Reading: {reading:.2f} | Balance: {balance:.2f}")

                # Let user select a meter
                while True:
                    choice = input("\nEnter meter number (or 'cancel' to return): ").strip()

                    if choice.lower() == "cancel":
                        return

                    try:
                        meter_idx = int(choice) - 1
                        if 0 <= meter_idx < len(meters):
                            selected_meter = meters[meter_idx]
                            break
                        else:
                            print("Invalid meter number")
                    except ValueError:
                        print("Please enter a valid number or 'cancel'")

                meter_id = selected_meter.get("id")
                meter_name = selected_meter.get("name", f"Meter {meter_id}")

                # Get date range from user
                tx_manager = TransactionHistoryManager(self.config)
                date_from, date_to = tx_manager.display_date_range_options()

                if date_from is None or date_to is None:
                    print("Cancelled")
                    return

                # Fetch and display transaction history
                print(f"\nFetching transaction history for {meter_name}...")
                result = await tx_manager.fetch_all_transactions(api_client, meter_id, date_from, date_to)
                tx_manager.display_transaction_history(result)

        except Exception as e:
            logger.error(f"Error viewing transaction history: {e}")
            print(f"Error: {e}")


async def main():
    """Entry point for the application."""
    monitor = MeterMonitor()
    await monitor.run()


if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())