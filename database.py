"""
Database module for the electricity meter monitoring system.

This module handles SQLite database initialization, schema creation,
and data persistence in an append-only fashion suitable for evidence collection.
"""

import sqlite3
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from data_model import MeterSnapshot
from config import Config

logger = logging.getLogger(__name__)


class MeterDatabase:
    """
    SQLite database handler for meter monitoring data.

    Uses append-only design for auditability and evidence collection.
    """

    def __init__(self, config: Config):
        self.config = config
        self.db_path = config.database_path
        self._connection: Optional[sqlite3.Connection] = None
        self._initialize_database()

    def _initialize_database(self) -> None:
        """Initialize the database and create tables if they don't exist."""
        self._connection = sqlite3.connect(self.db_path)
        self._create_tables()
        logger.info(f"Database initialized at {self.db_path}")

    def _create_tables(self) -> None:
        """Create the necessary database tables."""
        cursor = self._connection.cursor()

        # Main snapshots table - stores all meter data
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS meter_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                meter_id TEXT NOT NULL,
                meter_name TEXT,
                local_timestamp TEXT NOT NULL,
                api_timestamp TEXT,
                raw_data TEXT NOT NULL,  -- JSON string of all raw API data
                current_reading_delta REAL,
                balance_unit_delta REAL,
                poll_successful BOOLEAN NOT NULL DEFAULT 1,
                error_message TEXT,
                is_online BOOLEAN,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Index for efficient queries by meter and time
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_meter_timestamp
            ON meter_snapshots (meter_id, local_timestamp)
        ''')

        # Metadata table for system information
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS system_metadata (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        self._connection.commit()

    def store_snapshot(self, snapshot: MeterSnapshot) -> int:
        """
        Store a meter snapshot in the database.

        Args:
            snapshot: The meter snapshot to store

        Returns:
            The database row ID of the inserted record
        """
        cursor = self._connection.cursor()

        data = snapshot.to_dict()

        cursor.execute('''
            INSERT INTO meter_snapshots (
                meter_id, meter_name, local_timestamp, api_timestamp,
                raw_data, current_reading_delta, balance_unit_delta,
                poll_successful, error_message, is_online
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data["meter_id"],
            data["meter_name"],
            data["local_timestamp"],
            data["api_timestamp"],
            json.dumps(data["raw_data"]),  # Store raw data as JSON
            data["current_reading_delta"],
            data["balance_unit_delta"],
            data["poll_successful"],
            data["error_message"],
            data["is_online"]
        ))

        self._connection.commit()
        row_id = cursor.lastrowid
        logger.debug(f"Stored snapshot for meter {snapshot.meter_id} (row {row_id})")
        return row_id

    def get_recent_snapshots(self, meter_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent snapshots for a specific meter.

        Args:
            meter_id: The meter identifier
            limit: Maximum number of snapshots to return

        Returns:
            List of snapshot dictionaries, most recent first
        """
        cursor = self._connection.cursor()

        cursor.execute('''
            SELECT id, meter_id, meter_name, local_timestamp, api_timestamp,
                   raw_data, current_reading_delta, balance_unit_delta,
                   poll_successful, error_message, is_online
            FROM meter_snapshots
            WHERE meter_id = ?
            ORDER BY local_timestamp DESC
            LIMIT ?
        ''', (meter_id, limit))

        rows = cursor.fetchall()
        snapshots = []

        for row in rows:
            snapshot = {
                "id": row[0],
                "meter_id": row[1],
                "meter_name": row[2],
                "local_timestamp": row[3],
                "api_timestamp": row[4],
                "raw_data": json.loads(row[5]) if row[5] else {},
                "current_reading_delta": row[6],
                "balance_unit_delta": row[7],
                "poll_successful": row[8],
                "error_message": row[9],
                "is_online": row[10]
            }
            snapshots.append(snapshot)

        return snapshots

    def get_meter_summary(self, meter_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a summary of data for a specific meter.

        Args:
            meter_id: The meter identifier

        Returns:
            Summary dictionary or None if no data exists
        """
        cursor = self._connection.cursor()

        # Get basic stats
        cursor.execute('''
            SELECT COUNT(*), MIN(local_timestamp), MAX(local_timestamp)
            FROM meter_snapshots
            WHERE meter_id = ? AND poll_successful = 1
        ''', (meter_id,))

        row = cursor.fetchone()
        if not row or row[0] == 0:
            return None

        total_snapshots, first_poll, last_poll = row

        # Get latest values
        cursor.execute('''
            SELECT raw_data, current_reading_delta, balance_unit_delta
            FROM meter_snapshots
            WHERE meter_id = ? AND poll_successful = 1
            ORDER BY local_timestamp DESC
            LIMIT 1
        ''', (meter_id,))

        latest_row = cursor.fetchone()
        latest_data = json.loads(latest_row[0]) if latest_row else {}

        return {
            "meter_id": meter_id,
            "total_snapshots": total_snapshots,
            "first_poll": first_poll,
            "last_poll": last_poll,
            "latest_reading": latest_data.get("current_reading"),
            "latest_balance": latest_data.get("balance_unit"),
            "latest_reading_delta": latest_row[1] if latest_row else None,
            "latest_balance_delta": latest_row[2] if latest_row else None
        }

    def store_system_metadata(self, key: str, value: Any) -> None:
        """
        Store system metadata in the database.

        Args:
            key: Metadata key
            value: Metadata value (will be JSON serialized)
        """
        cursor = self._connection.cursor()

        cursor.execute('''
            INSERT OR REPLACE INTO system_metadata (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
        ''', (key, json.dumps(value)))

        self._connection.commit()

    def get_system_metadata(self, key: str) -> Any:
        """
        Retrieve system metadata from the database.

        Args:
            key: Metadata key

        Returns:
            Deserialized metadata value, or None if not found
        """
        cursor = self._connection.cursor()

        cursor.execute('SELECT value FROM system_metadata WHERE key = ?', (key,))
        row = cursor.fetchone()

        return json.loads(row[0]) if row else None

    def close(self) -> None:
        """Close the database connection."""
        if self._connection:
            self._connection.close()
            self._connection = None
            logger.info("Database connection closed")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()