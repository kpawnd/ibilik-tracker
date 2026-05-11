"""
Database module for the electricity meter monitoring system.

This module handles SQLite database initialization, schema creation,
and data persistence in an append-only fashion suitable for evidence collection.
"""

import sqlite3
import json
import logging
import os
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
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
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
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
                vendor_meter_id INTEGER,
                local_timestamp TEXT NOT NULL,
                api_timestamp TEXT,
                last_connected_at TEXT,
                raw_data TEXT NOT NULL,  -- JSON string of all raw API data
                current_reading REAL,
                balance_unit REAL,
                current_reading_delta REAL,
                balance_unit_delta REAL,
                currency TEXT,
                unit_price REAL,
                minimum_topup_unit INTEGER,
                minimum_topup_price REAL,
                free_unit REAL,
                free_unit_refresh_at TEXT,
                warning_at_unit INTEGER,
                is_low_balance_notification_sent BOOLEAN,
                poll_successful BOOLEAN NOT NULL DEFAULT 1,
                error_message TEXT,
                is_online BOOLEAN,
                is_connected BOOLEAN,
                is_active BOOLEAN,
                anomalies TEXT,
                reconciliation TEXT,
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

        self._ensure_columns()

        self._connection.commit()

    def _ensure_columns(self) -> None:
        """Add new columns when upgrading existing databases."""
        cursor = self._connection.cursor()

        cursor.execute("PRAGMA table_info(meter_snapshots)")
        existing_columns = {row[1] for row in cursor.fetchall()}

        columns_to_add = {
            "vendor_meter_id": "INTEGER",
            "last_connected_at": "TEXT",
            "current_reading": "REAL",
            "balance_unit": "REAL",
            "currency": "TEXT",
            "unit_price": "REAL",
            "minimum_topup_unit": "INTEGER",
            "minimum_topup_price": "REAL",
            "free_unit": "REAL",
            "free_unit_refresh_at": "TEXT",
            "warning_at_unit": "INTEGER",
            "is_low_balance_notification_sent": "BOOLEAN",
            "is_connected": "BOOLEAN",
            "is_active": "BOOLEAN",
            "anomalies": "TEXT",
            "reconciliation": "TEXT"
        }

        for name, col_type in columns_to_add.items():
            if name not in existing_columns:
                cursor.execute(f"ALTER TABLE meter_snapshots ADD COLUMN {name} {col_type}")

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
                meter_id, meter_name, vendor_meter_id, local_timestamp, api_timestamp,
                last_connected_at, raw_data, current_reading, balance_unit,
                current_reading_delta, balance_unit_delta, currency, unit_price,
                minimum_topup_unit, minimum_topup_price, free_unit, free_unit_refresh_at,
                warning_at_unit, is_low_balance_notification_sent, poll_successful,
                error_message, is_online, is_connected, is_active, anomalies, reconciliation
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data["meter_id"],
            data["meter_name"],
            data["vendor_meter_id"],
            data["local_timestamp"],
            data["api_timestamp"],
            data["last_connected_at"],
            json.dumps(data["raw_data"]),  # Store raw data as JSON
            data["current_reading"],
            data["balance_unit"],
            data["current_reading_delta"],
            data["balance_unit_delta"],
            data["currency"],
            data["unit_price"],
            data["minimum_topup_unit"],
            data["minimum_topup_price"],
            data["free_unit"],
            data["free_unit_refresh_at"],
            data["warning_at_unit"],
            data["is_low_balance_notification_sent"],
            data["poll_successful"],
            data["error_message"],
            data["is_online"],
            data["is_connected"],
            data["is_active"],
            json.dumps(data["anomalies"]) if data["anomalies"] else None,
            json.dumps(data["reconciliation"]) if data["reconciliation"] else None
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
             SELECT id, meter_id, meter_name, vendor_meter_id, local_timestamp, api_timestamp,
                 last_connected_at, raw_data, current_reading, balance_unit,
                 current_reading_delta, balance_unit_delta, currency, unit_price,
                 warning_at_unit, poll_successful, error_message, is_online,
                 is_connected, is_active, anomalies, reconciliation
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
                "vendor_meter_id": row[3],
                "local_timestamp": row[4],
                "api_timestamp": row[5],
                "last_connected_at": row[6],
                "raw_data": json.loads(row[7]) if row[7] else {},
                "current_reading": row[8],
                "balance_unit": row[9],
                "current_reading_delta": row[10],
                "balance_unit_delta": row[11],
                "currency": row[12],
                "unit_price": row[13],
                "warning_at_unit": row[14],
                "poll_successful": row[15],
                "error_message": row[16],
                "is_online": row[17],
                "is_connected": row[18],
                "is_active": row[19],
                "anomalies": json.loads(row[20]) if row[20] else None,
                "reconciliation": json.loads(row[21]) if row[21] else None
            }
            snapshots.append(snapshot)

        return snapshots

    def get_latest_snapshots(self) -> List[Dict[str, Any]]:
        """Get the latest successful snapshot for each meter."""
        cursor = self._connection.cursor()

        cursor.execute('''
            SELECT ms.id, ms.meter_id, ms.meter_name, ms.vendor_meter_id,
                   ms.local_timestamp, ms.api_timestamp, ms.last_connected_at,
                   ms.raw_data, ms.current_reading, ms.balance_unit,
                   ms.current_reading_delta, ms.balance_unit_delta, ms.currency,
                   ms.unit_price, ms.warning_at_unit, ms.poll_successful,
                   ms.error_message, ms.is_online, ms.is_connected, ms.is_active,
                   ms.anomalies, ms.reconciliation
            FROM meter_snapshots ms
            INNER JOIN (
                SELECT meter_id, MAX(local_timestamp) AS max_ts
                FROM meter_snapshots
                WHERE poll_successful = 1
                GROUP BY meter_id
            ) latest
            ON ms.meter_id = latest.meter_id AND ms.local_timestamp = latest.max_ts
            ORDER BY ms.meter_id
        ''')

        rows = cursor.fetchall()
        snapshots = []

        for row in rows:
            snapshots.append({
                "id": row[0],
                "meter_id": row[1],
                "meter_name": row[2],
                "vendor_meter_id": row[3],
                "local_timestamp": row[4],
                "api_timestamp": row[5],
                "last_connected_at": row[6],
                "raw_data": json.loads(row[7]) if row[7] else {},
                "current_reading": row[8],
                "balance_unit": row[9],
                "current_reading_delta": row[10],
                "balance_unit_delta": row[11],
                "currency": row[12],
                "unit_price": row[13],
                "warning_at_unit": row[14],
                "poll_successful": row[15],
                "error_message": row[16],
                "is_online": row[17],
                "is_connected": row[18],
                "is_active": row[19],
                "anomalies": json.loads(row[20]) if row[20] else None,
                "reconciliation": json.loads(row[21]) if row[21] else None
            })

        return snapshots

    def get_daily_usage(self, meter_id: str, days: int = 7) -> List[Dict[str, Any]]:
        """Get daily usage totals for a meter."""
        cursor = self._connection.cursor()

        end_date = datetime.utcnow().date()
        start_date = end_date - timedelta(days=max(days - 1, 0))

        cursor.execute('''
            SELECT date(local_timestamp) AS usage_day,
                   SUM(CASE WHEN current_reading_delta > 0 THEN current_reading_delta ELSE 0 END) AS usage
            FROM meter_snapshots
            WHERE meter_id = ?
              AND poll_successful = 1
              AND local_timestamp >= ?
            GROUP BY date(local_timestamp)
            ORDER BY usage_day
        ''', (meter_id, start_date.isoformat()))

        rows = cursor.fetchall()
        return [{"day": row[0], "usage": row[1] or 0} for row in rows]

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

    def get_meter_ids(self) -> List[str]:
        """
        Get all distinct meter IDs in the database.

        Returns:
            List of meter IDs
        """
        cursor = self._connection.cursor()
        cursor.execute('''
            SELECT DISTINCT meter_id
            FROM meter_snapshots
            ORDER BY meter_id
        ''')
        return [row[0] for row in cursor.fetchall()]

    def get_anomaly_events(
        self,
        meter_id: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 200
    ) -> List[Dict[str, Any]]:
        """
        Retrieve anomaly events for reporting.
        """
        cursor = self._connection.cursor()

        query = [
            "SELECT meter_id, meter_name, local_timestamp, api_timestamp,",
            "current_reading, balance_unit, unit_price, currency,",
            "current_reading_delta, balance_unit_delta, anomalies, reconciliation",
            "FROM meter_snapshots",
            "WHERE poll_successful = 1",
            "AND anomalies IS NOT NULL",
            "AND anomalies != '{}'"
        ]
        params: List[Any] = []

        if meter_id:
            query.append("AND meter_id = ?")
            params.append(meter_id)

        if start_time:
            query.append("AND local_timestamp >= ?")
            params.append(start_time)

        if end_time:
            query.append("AND local_timestamp <= ?")
            params.append(end_time)

        query.append("ORDER BY local_timestamp DESC")
        query.append("LIMIT ?")
        params.append(limit)

        cursor.execute(" ".join(query), params)
        rows = cursor.fetchall()
        events = []

        for row in rows:
            events.append({
                "meter_id": row[0],
                "meter_name": row[1],
                "local_timestamp": row[2],
                "api_timestamp": row[3],
                "current_reading": row[4],
                "balance_unit": row[5],
                "unit_price": row[6],
                "currency": row[7],
                "current_reading_delta": row[8],
                "balance_unit_delta": row[9],
                "anomalies": json.loads(row[10]) if row[10] else None,
                "reconciliation": json.loads(row[11]) if row[11] else None
            })

        return events

    def store_system_metadata(self, key: str, value: Any) -> None:
        """
        Store system metadata in the database.
        """
        cursor = self._connection.cursor()

        cursor.execute('''
            INSERT OR REPLACE INTO system_metadata (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
        ''', (key, json.dumps(value)))

        self._connection.commit()

    def get_runtime_settings(self) -> Dict[str, Any]:
        """Get persisted runtime settings overrides."""
        value = self.get_system_metadata("runtime_settings")
        return value if isinstance(value, dict) else {}

    def set_runtime_settings(self, settings: Dict[str, Any]) -> None:
        """Persist runtime settings overrides."""
        self.store_system_metadata("runtime_settings", settings)

    def get_system_metadata(self, key: str) -> Any:
        """
        Retrieve system metadata from the database.
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