"""
Chart rendering helpers for terminal output.
"""

from __future__ import annotations

import math


def render_usage_chart(daily_usage: list[dict], width: int = 60, height: int = 12) -> str:
    """Render a daily usage bar chart. Each row = one day."""
    if not daily_usage:
        return "No usage data available."

    labels = [entry.get("day", "") for entry in daily_usage]
    values = [entry.get("usage", 0) or 0 for entry in daily_usage]

    max_value = max(values) if values else 0
    if max_value == 0:
        return "No consumption recorded in this period."

    label_width = min(10, max(len(label) for label in labels)) if labels else 5
    # Reserve space for label, separator, trailing value: "| " + " " + "XX.XX"
    bar_width = max(10, width - label_width - 9)

    scale_line = " " * label_width + "  " + f"max {max_value:.2f}".rjust(bar_width)
    lines = [scale_line]

    for label, value in zip(labels, values):
        short_label = label[-label_width:] if label else "".rjust(label_width)
        bar_len = int((value / max_value) * bar_width)
        bar = "#" * bar_len
        lines.append(f"{short_label:>{label_width}} | {bar:<{bar_width}} {value:.2f}")

    if height and len(lines) > height:
        lines = lines[-height:]

    return "\n".join(lines)


def render_balance_chart(balance_history: list[dict], width: int = 60, height: int = 12) -> str:
    """
    Render a balance-over-time chart. Each column = one time bucket.
    Bars grow upward: full column = max balance, empty = zero.
    """
    if not balance_history:
        return "No balance data available."

    # Reserve label column (8 chars) + separator
    inner_width = max(10, width - 10)
    n = len(balance_history)

    # Bucket n data points into inner_width columns
    bucket_size = max(1, math.ceil(n / inner_width))
    buckets: list[float] = []
    for i in range(0, n, bucket_size):
        chunk = [balance_history[j]["balance"] for j in range(i, min(i + bucket_size, n))]
        buckets.append(sum(chunk) / len(chunk))

    buckets = buckets[:inner_width]

    max_val = max(buckets) if buckets else 0
    min_val = min(buckets) if buckets else 0

    if max_val == min_val:
        return f"Balance stable at {max_val:.2f} units."

    # Build vertical chart: height rows, each row is a threshold level
    # Row 0 = top (max), row height-1 = bottom (min)
    chart_rows = height - 2  # leave 1 for top label, 1 for X-axis
    lines: list[str] = []

    for row in range(chart_rows):
        # threshold: what balance level this row represents
        threshold = max_val - (row / max(chart_rows - 1, 1)) * (max_val - min_val)
        label = f"{threshold:>7.1f} "
        bar_chars = ""
        for val in buckets:
            bar_chars += "#" if val >= threshold else " "
        lines.append(label + bar_chars)

    # X-axis: first and last timestamp (trimmed)
    first_ts = balance_history[0]["ts"][:16]
    last_ts = balance_history[-1]["ts"][:16]
    axis = " " * 8 + first_ts.ljust(inner_width - len(last_ts)) + last_ts
    lines.append(axis)

    return "\n".join(lines)
