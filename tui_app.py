"""
Textual TUI for monitoring meter status, alerts, and settings.
"""

from __future__ import annotations

import asyncio

from textual.app import App, ComposeResult
from textual.containers import Container, VerticalScroll
from textual.widgets import Header, Footer, DataTable, Static, Input, Button, Switch, TabbedContent, TabPane

from calculations import MeterCalculations
from charts import render_usage_chart
from config import Config
from database import MeterDatabase
from service import MonitoringService


class MonitorApp(App):
    """Textual UI for the iBilik tracker."""

    CSS = """
    Screen {
        layout: vertical;
    }

    #meters-table {
        height: 12;
    }

    #usage-chart {
        height: 14;
        overflow: hidden;
    }

    #settings-form Input {
        width: 40;
    }

    #settings-actions {
        height: 3;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh")
    ]

    def __init__(self, config: Config, start_service: bool = True):
        super().__init__()
        self.config = config
        self.database = MeterDatabase(config)
        self.service = MonitoringService(config, database=self.database)
        self.start_service = start_service
        self.service_task: asyncio.Task | None = None
        self.selected_meter_id: str | None = None
        self._meters_initialized = False
        self._alerts_initialized = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent():
            with TabPane("Dashboard", id="dashboard"):
                with VerticalScroll():
                    yield DataTable(id="meters-table")
                    yield Static("Select a meter to view details.", id="meter-summary", markup=False)
                    yield Static("", id="usage-summary", markup=False)
                    yield Static("", id="usage-chart", markup=False)
            with TabPane("Alerts", id="alerts"):
                yield DataTable(id="alerts-table")
            with TabPane("Settings", id="settings"):
                with Container(id="settings-form"):
                    yield Static("Polling interval (seconds)")
                    yield Input(id="polling-interval")
                    yield Static("Low-balance reminders")
                    yield Switch(value=True, id="reminders-enabled")
                    yield Static("Low-balance threshold (units)")
                    yield Input(id="low-balance-threshold")
                    yield Static("Reminder cooldown (minutes)")
                    yield Input(id="reminder-cooldown")
                    yield Static("Webhook URLs (comma-separated)")
                    yield Input(id="reminder-webhooks")
                with Container(id="settings-actions"):
                    yield Button("Save Settings", id="save-settings")
                    yield Button("Reload", id="reload-settings")
        yield Footer()

    async def on_mount(self) -> None:
        self._load_settings_inputs()
        self.refresh_data()
        self.set_interval(self.config.tui_refresh_seconds, self.refresh_data)

        if self.start_service:
            self.service_task = asyncio.create_task(self.service.run())

    async def on_shutdown(self) -> None:
        if self.start_service:
            await self.service.stop()
        else:
            self.database.close()

    def action_refresh(self) -> None:
        self.refresh_data()

    def refresh_data(self) -> None:
        self._refresh_meter_table()
        self._refresh_alerts_table()
        self._refresh_meter_details()

    def _refresh_meter_table(self) -> None:
        table = self.query_one("#meters-table", DataTable)
        snapshots = self.database.get_latest_snapshots()

        if not self._meters_initialized:
            table.add_columns("Meter", "Reading", "Balance", "Price", "Status", "Updated")
            table.cursor_type = "row"
            self._meters_initialized = True

        table.clear()

        for snapshot in snapshots:
            meter_id = snapshot.get("meter_id")
            meter_name = snapshot.get("meter_name") or meter_id
            reading = snapshot.get("current_reading")
            balance = snapshot.get("balance_unit")
            price = snapshot.get("unit_price")
            status = "online" if snapshot.get("is_online") else "offline"
            updated = snapshot.get("local_timestamp")

            table.add_row(
                meter_name,
                f"{reading:.2f}" if isinstance(reading, (int, float)) else "-",
                f"{balance:.2f}" if isinstance(balance, (int, float)) else "-",
                f"{price:.4f}" if isinstance(price, (int, float)) else "-",
                status,
                updated,
                key=meter_id
            )

        if snapshots and (self.selected_meter_id not in {s.get("meter_id") for s in snapshots}):
            self.selected_meter_id = snapshots[0].get("meter_id")

    def _refresh_alerts_table(self) -> None:
        table = self.query_one("#alerts-table", DataTable)
        events = self.database.get_anomaly_events(limit=self.config.report_max_events)

        if not self._alerts_initialized:
            table.add_columns("Meter", "Time", "Anomalies")
            self._alerts_initialized = True

        table.clear()

        for event in events:
            anomaly_keys = ", ".join(sorted(event.get("anomalies", {}).keys()))
            table.add_row(
                event.get("meter_name") or event.get("meter_id"),
                event.get("local_timestamp"),
                anomaly_keys or "-"
            )

    def _refresh_meter_details(self) -> None:
        summary = self.query_one("#meter-summary", Static)
        usage_summary = self.query_one("#usage-summary", Static)
        chart = self.query_one("#usage-chart", Static)

        if not self.selected_meter_id:
            summary.update("No meter selected.")
            usage_summary.update("")
            chart.update("")
            return

        latest = self.database.get_recent_snapshots(self.selected_meter_id, limit=1)
        if not latest:
            summary.update("No data for selected meter.")
            usage_summary.update("")
            chart.update("")
            return

        snapshot = latest[0]
        meter_name = snapshot.get("meter_name") or snapshot.get("meter_id")
        balance = snapshot.get("balance_unit")
        reading = snapshot.get("current_reading")
        price = snapshot.get("unit_price")
        updated = snapshot.get("local_timestamp")
        status = "online" if snapshot.get("is_online") else "offline"

        summary_lines = [
            f"Meter: {meter_name} ({snapshot.get('meter_id')})",
            f"Status: {status}",
            f"Updated: {updated}",
            f"Reading: {reading:.2f}" if isinstance(reading, (int, float)) else "Reading: -",
            f"Balance: {balance:.2f}" if isinstance(balance, (int, float)) else "Balance: -",
            f"Unit price: {price:.4f}" if isinstance(price, (int, float)) else "Unit price: -"
        ]
        summary.update("\n".join(summary_lines))

        daily_usage = self.database.get_daily_usage(
            self.selected_meter_id,
            days=self.config.usage_window_days
        )
        usage_stats = MeterCalculations.summarize_daily_usage(
            daily_usage,
            spike_multiplier=self.config.usage_spike_multiplier
        )

        highest = usage_stats.get("highest")
        lowest = usage_stats.get("lowest")
        spike_days = usage_stats.get("spikes", [])

        usage_lines = [
            f"Weekly total: {usage_stats.get('total', 0):.2f} units",
            f"Average/day: {usage_stats.get('average', 0):.2f} units",
        ]

        if highest:
            usage_lines.append(f"Highest: {highest.get('day')} ({highest.get('usage', 0):.2f})")
        if lowest:
            usage_lines.append(f"Lowest: {lowest.get('day')} ({lowest.get('usage', 0):.2f})")
        if spike_days:
            spikes = ", ".join(f"{entry.get('day')} ({entry.get('usage', 0):.2f})" for entry in spike_days)
            usage_lines.append(f"Spikes: {spikes}")

        usage_summary.update("\n".join(usage_lines))
        chart.update(render_usage_chart(daily_usage))

    def _load_settings_inputs(self) -> None:
        runtime = self.database.get_runtime_settings()
        polling = runtime.get("polling", {})
        reminders = runtime.get("reminders", {})

        polling_interval = polling.get("interval_seconds", self.config.polling_interval)
        reminders_enabled = reminders.get("enabled", self.config.reminders_enabled)
        threshold = reminders.get("low_balance_threshold", self.config.reminders_low_balance_threshold)
        cooldown = reminders.get("cooldown_minutes", self.config.reminders_cooldown_minutes)
        webhooks = reminders.get("webhooks", self.config.reminders_webhooks)

        self.query_one("#polling-interval", Input).value = str(polling_interval)
        self.query_one("#reminders-enabled", Switch).value = bool(reminders_enabled)
        self.query_one("#low-balance-threshold", Input).value = str(threshold)
        self.query_one("#reminder-cooldown", Input).value = str(cooldown)
        self.query_one("#reminder-webhooks", Input).value = ",".join(webhooks)

    def _save_settings(self) -> None:
        runtime = self.database.get_runtime_settings()
        polling = runtime.get("polling", {})
        reminders = runtime.get("reminders", {})

        polling_input = self.query_one("#polling-interval", Input).value
        threshold_input = self.query_one("#low-balance-threshold", Input).value
        cooldown_input = self.query_one("#reminder-cooldown", Input).value
        webhooks_input = self.query_one("#reminder-webhooks", Input).value
        reminders_enabled = self.query_one("#reminders-enabled", Switch).value

        try:
            polling["interval_seconds"] = int(polling_input)
        except ValueError:
            polling["interval_seconds"] = self.config.polling_interval

        try:
            reminders["low_balance_threshold"] = float(threshold_input)
        except ValueError:
            reminders["low_balance_threshold"] = self.config.reminders_low_balance_threshold

        try:
            reminders["cooldown_minutes"] = int(cooldown_input)
        except ValueError:
            reminders["cooldown_minutes"] = self.config.reminders_cooldown_minutes

        reminders["enabled"] = bool(reminders_enabled)
        reminders["webhooks"] = [
            item.strip()
            for item in webhooks_input.split(",")
            if item.strip()
        ]

        runtime["polling"] = polling
        runtime["reminders"] = reminders
        self.database.set_runtime_settings(runtime)
        self.notify("Settings saved")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save-settings":
            self._save_settings()
        elif event.button.id == "reload-settings":
            self._load_settings_inputs()
            self.notify("Settings reloaded")

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.data_table.id == "meters-table":
            self.selected_meter_id = str(event.row_key)
            self._refresh_meter_details()

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.data_table.id == "meters-table":
            self.selected_meter_id = str(event.row_key)
            self._refresh_meter_details()
