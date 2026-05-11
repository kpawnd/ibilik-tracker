"""
Background monitoring service for polling meters and storing snapshots.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from api import APIClient
from alerts import AlertManager
from calculations import MeterCalculations
from config import Config
from data_model import MeterSnapshot
from database import MeterDatabase
from tracker import MeterTracker
from transactions import TransactionHistoryManager

logger = logging.getLogger(__name__)


class MonitoringService:
    """Headless monitoring service for polling meters and sending reminders."""

    def __init__(self, config: Config, database: Optional[MeterDatabase] = None):
        self.config = config
        self.database = database or MeterDatabase(config)
        self.tracker = MeterTracker()
        self.tx_manager = TransactionHistoryManager(config)
        self.alerts = AlertManager()
        self.running = False
        self.monitoring_tasks: List[asyncio.Task] = []
        self.last_reconciliation_at: Dict[str, datetime] = {}
        self.last_reconciliation_result: Dict[str, Dict[str, Any]] = {}
        self._settings_cache: Dict[str, Any] = {}
        self._settings_loaded_at: Optional[datetime] = None

    async def run(self, meters: Optional[List[Dict[str, Any]]] = None) -> None:
        """Start monitoring tasks for the provided meters (or discover them)."""
        if meters is None:
            meters = await self._load_meters()

        if not meters:
            logger.warning("No meters available to monitor")
            return

        self.running = True
        self.database.store_system_metadata("monitoring_start", {
            "timestamp": datetime.now().isoformat(),
            "meters": [m.get("id") for m in meters]
        })

        self.monitoring_tasks = [asyncio.create_task(self.monitor_meter(m)) for m in meters]

        try:
            await asyncio.gather(*self.monitoring_tasks, return_exceptions=True)
        finally:
            self.database.store_system_metadata("monitoring_end", {
                "timestamp": datetime.now().isoformat(),
                "reason": "shutdown"
            })

    async def stop(self) -> None:
        """Stop all monitoring tasks."""
        self.running = False
        for task in self.monitoring_tasks:
            task.cancel()
        if self.monitoring_tasks:
            await asyncio.gather(*self.monitoring_tasks, return_exceptions=True)
        self.database.close()

    async def _load_meters(self) -> List[Dict[str, Any]]:
        """Load meters from config overrides or API discovery."""
        manual_ids = self.config.manual_meter_ids
        if manual_ids:
            return [{"id": meter_id, "name": meter_id} for meter_id in manual_ids]

        async with APIClient(self.config) as api_client:
            meters = await api_client.get_meters()
            return meters or []

    async def monitor_meter(self, meter: Dict[str, Any]) -> None:
        """Monitor a single meter by polling its status periodically."""
        meter_id = meter.get("id")
        meter_name = meter.get("name", f"Meter {meter_id}")

        if not meter_id:
            logger.warning("Skipping meter without an ID: %s", meter)
            return

        async with APIClient(self.config) as api_client:
            while self.running:
                try:
                    meter_data = await api_client.get_meter_status(meter_id)
                    previous_snapshot = self.tracker.get_previous_snapshot(meter_id)

                    snapshot = MeterSnapshot.from_api_response(
                        meter_id,
                        meter_data,
                        previous_snapshot
                    )

                    self.tracker.update_meter_state(snapshot)

                    reconciliation = await self._maybe_reconcile(
                        api_client,
                        meter_id,
                        snapshot,
                        previous_snapshot
                    )
                    if reconciliation:
                        snapshot.reconciliation = reconciliation

                    anomalies = MeterCalculations.detect_anomalies(
                        snapshot,
                        previous_snapshot=previous_snapshot,
                        thresholds=self._get_anomaly_thresholds(),
                        reconciliation=reconciliation
                    )
                    if anomalies:
                        snapshot.anomalies = anomalies

                    self.database.store_snapshot(snapshot)
                    await self._maybe_send_low_balance_reminder(meter, snapshot)

                    logger.info(
                        "%s: reading=%s balance=%s",
                        meter_name,
                        snapshot.get_current_reading(),
                        snapshot.get_balance_unit()
                    )

                except asyncio.CancelledError:
                    break
                except Exception as exc:
                    error_snapshot = MeterSnapshot.create_error_snapshot(meter_id, str(exc))
                    self.database.store_snapshot(error_snapshot)
                    logger.warning("%s: poll failed (%s)", meter_name, exc)

                try:
                    await asyncio.sleep(self._get_poll_interval(meter_id))
                except asyncio.CancelledError:
                    break

        logger.info("Stopped monitoring for %s", meter_name)

    async def _maybe_send_low_balance_reminder(self, meter: Dict[str, Any], snapshot: MeterSnapshot) -> None:
        """Send low-balance reminders when balance falls below threshold."""
        if not snapshot.poll_successful:
            return

        reminders = self._get_reminder_settings()
        if not reminders["enabled"]:
            return

        balance = snapshot.get_balance_unit()
        if balance is None:
            return

        threshold = reminders["threshold"]
        if balance > threshold:
            return

        webhooks = reminders["webhooks"]
        if not webhooks:
            return

        cooldown = reminders["cooldown_minutes"]
        metadata_key = f"reminder_low_balance_{snapshot.meter_id}"
        last_sent = self.database.get_system_metadata(metadata_key)

        if last_sent and isinstance(last_sent, dict):
            try:
                last_ts = datetime.fromisoformat(last_sent.get("timestamp"))
                if (datetime.now() - last_ts) < timedelta(minutes=cooldown):
                    return
            except Exception:
                pass

        message = self.alerts.format_low_balance(snapshot, threshold)
        await self.alerts.send_webhooks(message, webhooks)
        self.database.store_system_metadata(metadata_key, {
            "timestamp": datetime.now().isoformat(),
            "balance": balance,
            "meter_name": snapshot.meter_name or snapshot.meter_id
        })

    def _get_anomaly_thresholds(self) -> Dict[str, Any]:
        """Build the anomaly threshold configuration dictionary."""
        return {
            "max_reading_delta": self.config.anomaly_max_reading_delta,
            "max_balance_delta": self.config.anomaly_max_balance_delta,
            "price_change_tolerance": self.config.anomaly_price_change_tolerance,
            "balance_reconciliation_tolerance": self.config.anomaly_balance_reconciliation_tolerance,
            "price_reconciliation_tolerance": self.config.anomaly_price_reconciliation_tolerance
        }

    def _get_poll_interval(self, meter_id: str) -> int:
        """Resolve the poll interval for a meter based on runtime overrides."""
        runtime = self._get_runtime_settings()
        polling = runtime.get("polling", {})

        interval = polling.get("interval_seconds", self.config.polling_interval)
        overrides = polling.get("per_meter_overrides", {})
        override_value = overrides.get(meter_id)

        if override_value is not None:
            try:
                return max(1, int(override_value))
            except (ValueError, TypeError):
                return max(1, int(interval))

        try:
            return max(1, int(interval))
        except (ValueError, TypeError):
            return max(1, int(self.config.polling_interval))

    def _get_reminder_settings(self) -> Dict[str, Any]:
        """Resolve reminder settings from runtime overrides or config."""
        runtime = self._get_runtime_settings()
        reminders = runtime.get("reminders", {})

        enabled = reminders.get("enabled", self.config.reminders_enabled)
        threshold = reminders.get("low_balance_threshold", self.config.reminders_low_balance_threshold)
        cooldown = reminders.get("cooldown_minutes", self.config.reminders_cooldown_minutes)
        webhooks = reminders.get("webhooks", self.config.reminders_webhooks)

        try:
            threshold_value = float(threshold)
        except (ValueError, TypeError):
            threshold_value = float(self.config.reminders_low_balance_threshold)

        try:
            cooldown_value = int(cooldown)
        except (ValueError, TypeError):
            cooldown_value = int(self.config.reminders_cooldown_minutes)

        return {
            "enabled": bool(enabled),
            "threshold": threshold_value,
            "cooldown_minutes": cooldown_value,
            "webhooks": list(webhooks) if isinstance(webhooks, list) else self.config.reminders_webhooks
        }

    def _get_runtime_settings(self) -> Dict[str, Any]:
        """Load runtime settings from the database with a short cache window."""
        now = datetime.now()
        if not self._settings_loaded_at or (now - self._settings_loaded_at).total_seconds() > 5:
            self._settings_cache = self.database.get_runtime_settings()
            self._settings_loaded_at = now
        return self._settings_cache

    async def _maybe_reconcile(
        self,
        api_client: APIClient,
        meter_id: str,
        snapshot: MeterSnapshot,
        previous_snapshot: Optional[MeterSnapshot]
    ) -> Optional[Dict[str, Any]]:
        """Run reconciliation on a schedule to limit API calls."""
        if not self.config.reconciliation_enabled:
            return None

        now = datetime.now()
        last_recon = self.last_reconciliation_at.get(meter_id)
        interval_seconds = self.config.reconciliation_interval_minutes * 60

        if last_recon and (now - last_recon).total_seconds() < interval_seconds:
            return None

        window_floor = now - timedelta(days=self.config.reconciliation_lookback_days)
        window_start = last_recon if last_recon and last_recon > window_floor else window_floor
        window_end = now

        try:
            date_from = window_start.strftime("%Y-%m-%d")
            date_to = window_end.strftime("%Y-%m-%d")
            tx_result = await self.tx_manager.fetch_all_transactions(api_client, meter_id, date_from, date_to)
            tx_summary = self.tx_manager.summarize_transactions_window(
                tx_result.get("transactions", {}),
                window_start,
                window_end
            )

            reconciliation = MeterCalculations.compute_reconciliation(
                snapshot,
                previous_snapshot,
                tx_summary,
                self._get_anomaly_thresholds()
            )

            self.last_reconciliation_at[meter_id] = now
            self.last_reconciliation_result[meter_id] = reconciliation
            return reconciliation
        except Exception as exc:
            logger.warning("Reconciliation failed for meter %s: %s", meter_id, exc)
            return None
