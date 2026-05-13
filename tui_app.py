"""
Textual TUI for monitoring meter status, alerts, and settings.
"""

from __future__ import annotations

import asyncio
import json
import re

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll
from textual.widgets import Header, Footer, DataTable, Static, Input, Button, Switch, TabbedContent, TabPane

from calculations import MeterCalculations
from charts import render_usage_chart, render_balance_chart
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

    #charts-meters-table {
        height: 8;
    }

    #usage-chart {
        height: 14;
        overflow: hidden;
    }

    #charts-chart {
        height: 16;
        overflow: hidden;
    }

    #chart-controls {
        height: 3;
        layout: horizontal;
    }

    #chart-controls Button {
        min-width: 12;
        margin-right: 1;
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
        self.service: MonitoringService | None = None
        self.start_service = start_service
        self.service_task: asyncio.Task | None = None
        self.selected_meter_id: str | None = None
        self._meters_initialized = False
        self._alerts_initialized = False
        self._charts_initialized = False
        self._chart_mode: str = "usage"   # "usage" | "balance"
        self._chart_days: int = 7

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent():
            with TabPane("Dashboard", id="dashboard"):
                with VerticalScroll():
                    yield DataTable(id="meters-table")
                    yield Static("Select a meter to view details.", id="meter-summary", markup=False)
                    yield Static("", id="usage-summary", markup=False)
                    yield Static("", id="usage-chart", markup=False)
            with TabPane("Charts", id="charts"):
                with VerticalScroll():
                    yield DataTable(id="charts-meters-table")
                    with Horizontal(id="chart-controls"):
                        yield Button("Usage",      id="chart-mode-usage",    variant="primary")
                        yield Button("Balance",    id="chart-mode-balance")
                        yield Button("7d",         id="chart-range-7",       variant="primary")
                        yield Button("14d",        id="chart-range-14")
                        yield Button("30d",        id="chart-range-30")
                        yield Button("Export CSV", id="chart-export")
                    yield Static("", id="charts-summary", markup=False)
                    yield Static("", id="charts-chart", markup=False)
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
            self.service = MonitoringService(self.config)
            self.service_task = asyncio.create_task(self.service.run())

    async def on_shutdown(self) -> None:
        if self.start_service and self.service:
            await self.service.stop()
        self.database.close()

    def action_refresh(self) -> None:
        self.refresh_data()

    def refresh_data(self) -> None:
        snapshots = self.database.get_latest_snapshots()
        self._refresh_meter_tables(snapshots)
        self._refresh_alerts_table()
        self._refresh_meter_details()
        self._refresh_chart_tab()

    def _refresh_meter_tables(self, snapshots: list[dict]) -> None:
        self._update_meter_table(
            "#meters-table",
            snapshots,
            initialized_attr="_meters_initialized"
        )
        self._update_meter_table(
            "#charts-meters-table",
            snapshots,
            initialized_attr="_charts_initialized"
        )

        if snapshots and (self.selected_meter_id not in {s.get("meter_id") for s in snapshots}):
            self.selected_meter_id = snapshots[0].get("meter_id")

    def _update_meter_table(self, table_id: str, snapshots: list[dict], initialized_attr: str) -> None:
        table = self.query_one(table_id, DataTable)

        if not getattr(self, initialized_attr):
            table.add_columns("Meter", "Reading", "Balance", "Price", "Status", "Updated")
            table.cursor_type = "row"
            setattr(self, initialized_attr, True)

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

        chart_width = chart.size.width or 60
        usage_text, chart_text = self._build_usage_view(width=chart_width)
        usage_summary.update(usage_text)
        chart.update(chart_text)

    def _refresh_chart_tab(self) -> None:
        summary = self.query_one("#charts-summary", Static)
        chart_widget = self.query_one("#charts-chart", Static)

        if not self.selected_meter_id:
            summary.update("No meter selected.")
            chart_widget.update("")
            return

        chart_width = chart_widget.size.width or 60

        if self._chart_mode == "balance":
            history = self.database.get_balance_history(
                self.selected_meter_id, hours=self._chart_days * 24
            )
            chart_text = render_balance_chart(history, width=chart_width)
            summary_text = f"Balance trend — last {self._chart_days}d"
        else:
            summary_text, chart_text = self._build_usage_view(
                days=self._chart_days, width=chart_width
            )

        summary.update(summary_text)
        chart_widget.update(chart_text)

    def _build_usage_view(self, days: int | None = None, width: int = 60) -> tuple[str, str]:
        days = days or self.config.usage_window_days
        daily_usage = self.database.get_daily_usage(self.selected_meter_id, days=days)

        if not daily_usage:
            return "No usage data available.", "No usage data available."

        usage_stats = MeterCalculations.summarize_daily_usage(
            daily_usage,
            spike_multiplier=self.config.usage_spike_multiplier
        )

        highest = usage_stats.get("highest")
        lowest = usage_stats.get("lowest")
        spike_days = usage_stats.get("spikes", [])

        period_label = f"{days}d" if days != self.config.usage_window_days else "Weekly"
        usage_lines = [
            f"{period_label} total: {usage_stats.get('total', 0):.2f} units",
            f"Average/day:  {usage_stats.get('average', 0):.2f} units",
        ]

        if highest:
            usage_lines.append(f"Highest: {highest.get('day')} ({highest.get('usage', 0):.2f})")
        if lowest:
            usage_lines.append(f"Lowest:  {lowest.get('day')} ({lowest.get('usage', 0):.2f})")
        if spike_days:
            spikes = ", ".join(f"{entry.get('day')} ({entry.get('usage', 0):.2f})" for entry in spike_days)
            usage_lines.append(f"Spikes:  {spikes}")

        return "\n".join(usage_lines), render_usage_chart(daily_usage, width=width)

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
            for item in re.split(r"[,\n]+", webhooks_input)
            if item.strip()
        ]

        runtime["polling"] = polling
        runtime["reminders"] = reminders
        self.database.set_runtime_settings(runtime)
        self._persist_settings_to_config(polling, reminders)
        self.notify("Settings saved")

    def _persist_settings_to_config(self, polling: dict, reminders: dict) -> None:
        config_path = self.config.config_path

        try:
            with open(config_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (FileNotFoundError, json.JSONDecodeError):
            self.notify("Failed to update config.json")
            return

        data.setdefault("polling", {})
        data["polling"]["interval_seconds"] = polling.get(
            "interval_seconds",
            self.config.polling_interval
        )

        data.setdefault("reminders", {})
        data["reminders"]["enabled"] = reminders.get(
            "enabled",
            self.config.reminders_enabled
        )
        data["reminders"]["low_balance_threshold"] = reminders.get(
            "low_balance_threshold",
            self.config.reminders_low_balance_threshold
        )
        data["reminders"]["cooldown_minutes"] = reminders.get(
            "cooldown_minutes",
            self.config.reminders_cooldown_minutes
        )
        data["reminders"]["webhooks"] = reminders.get(
            "webhooks",
            self.config.reminders_webhooks
        )

        with open(config_path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
            handle.write("\n")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save-settings":
            self._save_settings()
        elif event.button.id == "reload-settings":
            self._load_settings_inputs()
            self.notify("Settings reloaded")
        elif event.button.id == "chart-mode-usage":
            self._chart_mode = "usage"
            self._refresh_chart_tab()
        elif event.button.id == "chart-mode-balance":
            self._chart_mode = "balance"
            self._refresh_chart_tab()
        elif event.button.id == "chart-range-7":
            self._chart_days = 7
            self._refresh_chart_tab()
        elif event.button.id == "chart-range-14":
            self._chart_days = 14
            self._refresh_chart_tab()
        elif event.button.id == "chart-range-30":
            self._chart_days = 30
            self._refresh_chart_tab()
        elif event.button.id == "chart-export":
            if not self.selected_meter_id:
                self.notify("No meter selected", severity="warning")
                return
            path = self.database.export_daily_usage_csv(self.selected_meter_id, self._chart_days)
            self.notify(f"Exported to {path}")

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.data_table.id in {"meters-table", "charts-meters-table"}:
            key_value = event.row_key.value if hasattr(event.row_key, "value") else event.row_key
            self.selected_meter_id = str(key_value)
            self._refresh_meter_details()
            self._refresh_chart_tab()

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.data_table.id in {"meters-table", "charts-meters-table"}:
            key_value = event.row_key.value if hasattr(event.row_key, "value") else event.row_key
            self.selected_meter_id = str(key_value)
            self._refresh_meter_details()
            self._refresh_chart_tab()
