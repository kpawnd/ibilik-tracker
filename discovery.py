"""
Discovery module for the electricity meter monitoring system.

This module is responsible for fetching and presenting available meters
to the user for selection.
"""

import logging
from typing import List, Dict, Any, Optional
from api import APIClient
from config import Config

logger = logging.getLogger(__name__)


class MeterDiscovery:
    """Handles discovery and selection of meters to monitor."""

    def __init__(self, config: Config, api_client: APIClient):
        self.config = config
        self.api_client = api_client

    async def get_available_meters(self) -> List[Dict[str, Any]]:
        """
        Fetch all available meters for the authenticated user.

        Returns:
            List of meter dictionaries with their metadata, or empty list if discovery fails
        """
        try:
            meters = await self.api_client.get_meters()
            logger.info(f"Discovered {len(meters)} meters")
            return meters
        except Exception as e:
            logger.warning(f"Failed to discover meters via API: {e}")
            logger.info("Meter discovery failed - will allow manual meter ID entry")
            return []

    def display_meter_options(self, meters: List[Dict[str, Any]]) -> None:
        """
        Display available meters in a user-friendly format.

        Args:
            meters: List of meter dictionaries
        """
        if not meters:
            print("No meters found for this account.")
            return

        print(f"\nFound {len(meters)} meter(s):")
        print("-" * 50)

        for i, meter in enumerate(meters, 1):
            meter_id = meter.get("id", "Unknown")
            name = meter.get("name", "Unnamed Meter")

            print(f"{i}. Meter ID: {meter_id}")
            print(f"   Name: {name}")
            print()

    def select_meters_interactive(self, meters: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Present an interactive prompt for meter selection.

        Args:
            meters: List of available meters

        Returns:
            List of selected meter dictionaries
        """
        if not meters:
            return []

        self.display_meter_options(meters)

        while True:
            print("Selection options:")
            print("• Enter a number (1-{}) to monitor a specific meter".format(len(meters)))
            print("• Enter 'all' to monitor all meters")
            print("• Enter 'quit' to exit")
            print()

            choice = input("Your choice: ").strip().lower()

            if choice == 'quit':
                logger.info("User chose to quit")
                return []
            elif choice == 'all':
                logger.info(f"User selected all {len(meters)} meters for monitoring")
                return meters
            elif choice.isdigit():
                index = int(choice) - 1
                if 0 <= index < len(meters):
                    selected_meter = meters[index]
                    logger.info(f"User selected meter: ID={selected_meter.get('id')}, Name={selected_meter.get('name')}")
                    return [selected_meter]
                else:
                    print(f"Invalid number. Please enter 1-{len(meters)} or 'all'")
            else:
                print("Invalid choice. Please enter a number, 'all', or 'quit'")
            
            print()

    async def discover_and_select_meters(self) -> List[Dict[str, Any]]:
        """
        Complete workflow: discover meters and let user select which ones to monitor.

        Returns:
            List of selected meters
        """
        # First check if meter IDs are configured
        configured_ids = self.config.manual_meter_ids
        if configured_ids:
            print(f"Using configured meter IDs: {', '.join(configured_ids)}")
            meters = []
            for meter_id in configured_ids:
                meters.append({
                    "id": meter_id,
                    "name": f"Configured - {meter_id}",
                    "location": "Configured",
                    "status": "Unknown"
                })
            return meters

        # Try API discovery
        meters = await self.get_available_meters()

        if meters:
            return self.select_meters_interactive(meters)
        else:
            # No meters discovered - allow manual entry
            return self.manual_meter_entry()

    def manual_meter_entry(self) -> List[Dict[str, Any]]:
        """
        Allow manual entry of meter IDs when automatic discovery fails.

        Returns:
            List of meter dictionaries with manually entered IDs
        """
        print("\nAutomatic meter discovery failed.")
        print("You can manually enter meter IDs to monitor.")
        print("Note: Meter IDs are numeric values (e.g., 12345, 67890).")
        print("You can find these IDs in your iBilik account or from the API responses.")
        print()

        while True:
            print("Options:")
            print("  - Enter meter ID(s) separated by commas (e.g., '12345,67890,54321')")
            print("  - Enter 'q' to quit")

            choice = input("\nEnter meter ID(s): ").strip()

            if choice.lower() == 'q':
                return []

            if not choice:
                print("Please enter at least one meter ID.")
                continue

            # Parse meter IDs - clean up any extra characters that might be in the input
            raw_ids = [mid.strip().strip("'\"") for mid in choice.split(',') if mid.strip()]

            # Filter out any IDs that look like they contain the prompt text
            meter_ids = []
            for mid in raw_ids:
                # Skip if it contains common prompt words
                if any(word in mid.lower() for word in ['enter', 'meter', 'separated', 'commas', 'e.g.']):
                    continue
                # Try to convert to int to validate it's numeric
                try:
                    int(mid)
                    meter_ids.append(mid)
                except ValueError:
                    print(f"Skipping invalid meter ID '{mid}' - must be numeric")
                    continue

            if not meter_ids:
                print("No valid meter IDs entered. Please enter numeric meter IDs like '12345,67890'.")
                continue

            # Create meter dictionaries for manual entry
            meters = []
            for meter_id in meter_ids:
                meters.append({
                    "id": meter_id,
                    "name": f"Manual Entry - {meter_id}",
                    "location": "Unknown",
                    "status": "Unknown"
                })

            print(f"\nSelected {len(meters)} meter(s) for monitoring:")
            for meter in meters:
                print(f"  - {meter['name']} (ID: {meter['id']})")

            # Confirm selection
            confirm = input("\nProceed with monitoring these meters? (y/n): ").strip().lower()
            if confirm == 'y' or confirm == 'yes':
                return meters
            else:
                print("Selection cancelled. Try again.")
                continue