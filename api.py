"""
API client module for the electricity meter monitoring system.

This module handles all authenticated HTTP communication with the iBilik API,
including proper headers, error handling, and response parsing.
"""

import asyncio
import aiohttp
import logging
from typing import Dict, Any, Optional, List
from config import Config

logger = logging.getLogger(__name__)


class APIClient:
    """Client for communicating with the iBilik API."""

    def __init__(self, config: Config):
        self.config = config
        self.session: Optional[aiohttp.ClientSession] = None
        self._headers = self._build_headers()

    def _build_headers(self, method: str = "GET") -> Dict[str, str]:
        """Build the standard headers for API requests."""
        headers = {
            "x-merchant-token": self.config.merchant_token,
            "accept": "application/json",
            "origin": self.config.origin,
            "referer": self.config.referer,
            "user-agent": self.config.user_agent
        }
        
        # Only include content-type for methods that send body data
        if method.upper() in ["POST", "PUT", "PATCH"]:
            headers["content-type"] = "application/json"
            
        return headers

    async def __aenter__(self):
        """Async context manager entry."""
        # Create session without default headers since we'll set them per request
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()

    async def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make an HTTP request to the API."""
        if not self.session:
            raise RuntimeError("API client session not initialized. Use as async context manager.")

        url = f"{self.config.api_base_url}{endpoint}"
        headers = self._build_headers(method)

        try:
            async with self.session.request(method, url, headers=headers, **kwargs) as response:
                if response.status == 401:
                    logger.error("Authentication failed - invalid merchant token")
                    raise ValueError("Authentication failed")
                elif response.status == 403:
                    logger.error("Authorization failed - access denied")
                    raise ValueError("Authorization failed")
                elif response.status >= 400:
                    logger.error(f"API request failed with status {response.status}: {response.reason}")
                    response.raise_for_status()

                return await response.json()

        except aiohttp.ClientError as e:
            logger.error(f"Network error during API request: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error during API request: {e}")
            raise

    async def get_meters(self) -> List[Dict[str, Any]]:
        """
        Fetch all meters associated with the authenticated user.

        Returns:
            List of meter objects from the API
        """
        logger.info("Fetching available meters from API")
        response = await self._make_request("GET", self.config.discovery_endpoint)

        # Debug: log the raw response structure
        logger.debug(f"Discovery response keys: {list(response.keys()) if isinstance(response, dict) else type(response)}")

        # Parse the response: data array contains meter objects
        if "data" in response and isinstance(response["data"], list):
            meters = []
            for item in response["data"]:
                if "meter" in item and isinstance(item["meter"], dict):
                    meter = item["meter"]
                    # Ensure we have the required fields
                    if "id" in meter and "name" in meter:
                        meters.append(meter)
                        logger.debug(f"Found meter: ID={meter['id']}, Name={meter['name']}")
            
            logger.info(f"Successfully discovered {len(meters)} meters")
            return meters
        else:
            logger.warning(f"Unexpected discovery response structure: {response}")
            return []

    async def get_meter_status(self, meter_id: str) -> Dict[str, Any]:
        """
        Fetch the current status of a specific meter.

        Args:
            meter_id: The ID of the meter to query

        Returns:
            Meter status data from the API
        """
        logger.debug(f"Fetching status for meter {meter_id}")
        response = await self._make_request(self.config.status_method, f"/merchant/meter/{meter_id}/sync-status")

        # Handle nested response structure: data -> meter data
        if "data" in response and isinstance(response["data"], dict):
            return response["data"]

        # Fallback for direct response
        return response

    async def get_meter_transactions(self, meter_id: str, date_from: str, date_to: str) -> Dict[str, Any]:
        """
        Fetch transaction history for a meter within a date range.

        Args:
            meter_id: The ID of the meter to query
            date_from: Start date in YYYY-MM-DD format
            date_to: End date in YYYY-MM-DD format

        Returns:
            Dictionary of transactions (keyed by transaction ID)
        """
        logger.debug(f"Fetching transactions for meter {meter_id} from {date_from} to {date_to}")
        response = await self._make_request(
            "GET",
            f"/merchant/meter/{meter_id}/transactions",
            params={
                "date_from": date_from,
                "date_to": date_to
            }
        )

        # Handle nested response structure: data -> transactions dict
        if "data" in response:
            data = response["data"]
            # Convert list to dict if needed
            if isinstance(data, list):
                return {str(i): tx for i, tx in enumerate(data)}
            return data if isinstance(data, dict) else {}

        return {}