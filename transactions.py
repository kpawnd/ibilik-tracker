"""
Transaction history module for retrieving and displaying transaction data.

This module handles fetching transaction history for meters and provides
analysis and display functionality.
"""

import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta, timezone
from api import APIClient
from config import Config

logger = logging.getLogger(__name__)


class TransactionHistoryManager:
    """Manages retrieval and analysis of meter transactions."""

    def __init__(self, config: Config):
        self.config = config

    async def fetch_all_transactions(self, api_client: APIClient, meter_id: str,
                                     date_from: Optional[str] = None,
                                     date_to: Optional[str] = None) -> Dict[str, Any]:
        """
        Fetch all transactions for a meter within a date range.
        """
        # Set default date range (last year if not specified)
        if not date_to:
            date_to = datetime.now().strftime("%Y-%m-%d")
        if not date_from:
            date_from = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")

        logger.info(f"Fetching transactions for meter {meter_id} from {date_from} to {date_to}")

        transactions = await api_client.get_meter_transactions(meter_id, date_from, date_to)

        # Analyze the transactions
        analysis = self._analyze_transactions(transactions)

        return {
            "meter_id": meter_id,
            "date_from": date_from,
            "date_to": date_to,
            "transactions": transactions,
            "analysis": analysis
        }

    def _analyze_transactions(self, transactions: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze transactions to extract summary statistics.
        """
        if not transactions:
            return {
                "total_transactions": 0,
                "total_amount": 0,
                "total_units": 0,
                "by_type": {}
            }

        # Initialize counters
        by_type = {}
        total_amount = 0
        total_units = 0
        transactions_list = []
        unit_prices = []

        for key, tx in transactions.items():
            if not isinstance(tx, dict):
                continue

            if tx.get("deleted_at") is not None:
                continue

            tx_type = tx.get("type", "UNKNOWN")
            if tx_type not in by_type:
                by_type[tx_type] = {
                    "count": 0,
                    "total_amount": 0,
                    "total_units": 0,
                    "avg_amount": 0,
                    "avg_units": 0,
                }

            amount = self._safe_float(tx.get("total_price", 0))
            units = self._safe_float(tx.get("unit", 0))

            # Reject negative values — they indicate data corruption or an
            # unexpected transaction type and would silently skew reconciliation.
            if amount < 0 or units < 0:
                logger.warning(
                    "Ignoring transaction %s with negative amount/units: amount=%s units=%s",
                    key, amount, units
                )
                continue

            by_type[tx_type]["count"] += 1
            by_type[tx_type]["total_amount"] += amount
            by_type[tx_type]["total_units"] += units

            total_amount += amount
            total_units += units
            transactions_list.append(tx)

            if units > 0 and amount > 0:
                unit_prices.append(amount / units)

        # Calculate averages
        for tx_type in by_type:
            count = by_type[tx_type]["count"]
            if count > 0:
                by_type[tx_type]["avg_amount"] = by_type[tx_type]["total_amount"] / count
                by_type[tx_type]["avg_units"] = by_type[tx_type]["total_units"] / count

        # Sort by date
        transactions_list.sort(
            key=lambda x: x.get("created_at", ""),
            reverse=True
        )

        unit_price_stats = {}
        if unit_prices:
            unit_price_stats = {
                "count_priced": len(unit_prices),
                "avg_unit_price": sum(unit_prices) / len(unit_prices),
                "min_unit_price": min(unit_prices),
                "max_unit_price": max(unit_prices)
            }

        return {
            "total_transactions": len(transactions_list),
            "total_amount": total_amount,
            "total_units": total_units,
            "by_type": by_type,
            "oldest_transaction": transactions_list[-1].get("created_at") if transactions_list else None,
            "newest_transaction": transactions_list[0].get("created_at") if transactions_list else None,
            "unit_price_stats": unit_price_stats
        }

    def summarize_transactions_window(
        self,
        transactions: Dict[str, Any],
        window_start: datetime,
        window_end: datetime
    ) -> Dict[str, Any]:
        """
        Summarize transactions within a specific time window.
        """
        filtered = self._filter_transactions_by_time(transactions, window_start, window_end)
        analysis = self._analyze_transactions(filtered)
        return {
            "window_start": window_start.isoformat(),
            "window_end": window_end.isoformat(),
            "analysis": analysis
        }

    def _filter_transactions_by_time(
        self,
        transactions: Dict[str, Any],
        window_start: datetime,
        window_end: datetime
    ) -> Dict[str, Any]:
        """
        Filter transactions by created_at timestamp.
        """
        if not transactions:
            return {}

        start_dt = self._normalize_datetime(window_start)
        end_dt = self._normalize_datetime(window_end)
        filtered = {}

        for key, tx in transactions.items():
            if not isinstance(tx, dict):
                continue

            created_at = tx.get("created_at") or tx.get("updated_at")
            created_dt = self._parse_tx_datetime(created_at)
            if not created_dt:
                continue

            if start_dt <= created_dt <= end_dt:
                filtered[key] = tx

        return filtered

    def _parse_tx_datetime(self, value: Optional[str]) -> Optional[datetime]:
        """
        Parse transaction datetime strings into normalized datetime objects.
        """
        if not value or not isinstance(value, str):
            return None

        value = value.strip()
        if not value:
            return None

        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return self._normalize_datetime(dt)
        except ValueError:
            pass

        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(value, fmt)
                return self._normalize_datetime(dt)
            except ValueError:
                continue

        return None

    def _normalize_datetime(self, dt: datetime) -> datetime:
        """
        Normalize datetime objects to naive UTC for comparison.

        Args:
            dt: Datetime object

        Returns:
            Naive UTC datetime
        """
        if dt.tzinfo is not None:
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt

    def _safe_float(self, value: Any, default: float = 0.0) -> float:
        """
        Safely convert values to float.
        """
        try:
            if value is None:
                return default
            return float(value)
        except (ValueError, TypeError):
            return default

    def display_transaction_history(self, result: Dict[str, Any]) -> None:
        """
        Display transaction history in a formatted way.
        """
        meter_id = result["meter_id"]
        date_from = result["date_from"]
        date_to = result["date_to"]
        transactions = result["transactions"]
        analysis = result["analysis"]

        print("\n" + "="*100)
        print(f"TRANSACTION HISTORY - Meter ID: {meter_id}")
        print(f"Date Range: {date_from} to {date_to}")
        print("="*100)

        # Display summary
        print(f"\nSUMMARY:")
        print(f"  Total Transactions: {analysis['total_transactions']}")
        print(f"  Total Amount:       {analysis['total_amount']:.2f} RM")
        print(f"  Total Units:        {analysis['total_units']:.2f}")

        if analysis["total_transactions"] > 0:
            print(f"  Average per Transaction: {analysis['total_amount']/analysis['total_transactions']:.2f} RM")
            print(f"  Date Range: {analysis.get('oldest_transaction', 'N/A')} to {analysis.get('newest_transaction', 'N/A')}")

        # Display breakdown by type
        if analysis["by_type"]:
            print(f"\nBREAKDOWN BY TYPE:")
            for tx_type, stats in analysis["by_type"].items():
                print(f"\n  {tx_type}:")
                print(f"    Count:        {stats['count']}")
                print(f"    Total Amount: {stats['total_amount']:.2f} RM")
                print(f"    Total Units:  {stats['total_units']:.2f}")
                print(f"    Avg Amount:   {stats['avg_amount']:.2f} RM")
                print(f"    Avg Units:    {stats['avg_units']:.2f}")

        # Display transactions
        if transactions:
            print(f"\nTRANSACTION DETAILS (most recent first):")
            print("─"*100)

            # Sort transactions by date (most recent first)
            sorted_txs = sorted(
                [(k, v) for k, v in transactions.items() if isinstance(v, dict)],
                key=lambda x: x[1].get("created_at", ""),
                reverse=True
            )

            for i, (key, tx) in enumerate(sorted_txs[:20], 1):  # Show first 20
                date = tx.get("created_at", "N/A")
                tx_type = tx.get("type", "UNKNOWN")
                amount = tx.get("total_price", 0)
                units = tx.get("unit", 0)
                status = "✓" if tx.get("status") == 2 else "○"

                print(f"{i:2}. [{status}] {date:<25} {tx_type:<15} {amount:>8.2f} RM  {units:>8.2f} units")

            if len(sorted_txs) > 20:
                print(f"\n... and {len(sorted_txs) - 20} more transactions")

        print("\n" + "="*100 + "\n")

    def display_date_range_options(self) -> Tuple[str, str]:
        """
        Display date range options and let user choose.
        """
        print("\nSelect date range for transaction history:")
        print("1. Last 30 days")
        print("2. Last 60 days")
        print("3. Last 90 days")
        print("4. Last 6 months")
        print("5. Last year (365 days)")
        print("6. All available (5 years)")
        print("7. Custom date range")
        print("8. Cancel")

        while True:
            choice = input("\nEnter your choice (1-8): ").strip()

            today = datetime.now()

            if choice == "1":
                date_to = today.strftime("%Y-%m-%d")
                date_from = (today - timedelta(days=30)).strftime("%Y-%m-%d")
                return date_from, date_to
            elif choice == "2":
                date_to = today.strftime("%Y-%m-%d")
                date_from = (today - timedelta(days=60)).strftime("%Y-%m-%d")
                return date_from, date_to
            elif choice == "3":
                date_to = today.strftime("%Y-%m-%d")
                date_from = (today - timedelta(days=90)).strftime("%Y-%m-%d")
                return date_from, date_to
            elif choice == "4":
                date_to = today.strftime("%Y-%m-%d")
                date_from = (today - timedelta(days=180)).strftime("%Y-%m-%d")
                return date_from, date_to
            elif choice == "5":
                date_to = today.strftime("%Y-%m-%d")
                date_from = (today - timedelta(days=365)).strftime("%Y-%m-%d")
                return date_from, date_to
            elif choice == "6":
                date_to = today.strftime("%Y-%m-%d")
                date_from = (today - timedelta(days=365*5)).strftime("%Y-%m-%d")
                return date_from, date_to
            elif choice == "7":
                while True:
                    date_from_input = input("Enter start date (YYYY-MM-DD): ").strip()
                    try:
                        datetime.strptime(date_from_input, "%Y-%m-%d")
                        break
                    except ValueError:
                        print("Invalid date format. Please use YYYY-MM-DD")

                while True:
                    date_to_input = input("Enter end date (YYYY-MM-DD): ").strip()
                    try:
                        datetime.strptime(date_to_input, "%Y-%m-%d")
                        if date_to_input >= date_from_input:
                            return date_from_input, date_to_input
                        else:
                            print("End date must be after start date")
                    except ValueError:
                        print("Invalid date format. Please use YYYY-MM-DD")
            elif choice == "8":
                return None, None
            else:
                print("Invalid choice. Please enter 1-8")
