"""
Chart rendering helpers for terminal output.
"""

from __future__ import annotations

from typing import Iterable


def render_usage_chart(daily_usage: list[dict], width: int = 60, height: int = 12) -> str:
    """Render a usage chart for the provided daily usage data."""
    if not daily_usage:
        return "No usage data available."

    labels = [entry.get("day", "") for entry in daily_usage]
    values = [entry.get("usage", 0) or 0 for entry in daily_usage]

    try:
        import plotext as plt

        plt.clear_figure()
        plt.plotsize(width, height)
        plt.canvas_color("none")
        plt.axes_color("none")
        plt.ticks_color("grey")
        plt.title("Weekly Usage")
        plt.xticks(range(len(labels)), labels)
        plt.plot(range(len(values)), values)
        return plt.build()
    except Exception:
        # Fallback to a lightweight bar chart if plotext is unavailable.
        max_value = max(values) if values else 0
        lines = []
        for label, value in zip(labels, values):
            bar_len = int((value / max_value) * 30) if max_value > 0 else 0
            lines.append(f"{label}: {'#' * bar_len} {value:.2f}")
        return "\n".join(lines)
