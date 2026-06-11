"""Slot planning — mirrors the demo's planSlot()/firstFreeSlot() exactly.

The 5-day, 24/7 Gantt horizon is measured in hours from plant t0 (today's
local midnight, same anchor as the demo)."""
from __future__ import annotations

from datetime import datetime, timedelta

from tools import call_tool
from domain import BoardBlock, Order

HORIZON_DAYS = 5
G_START, G_END = 0.0, HORIZON_DAYS * 24.0
CHANGEOVER_H = 0.5


def round15(h: float) -> float:
    """Round to the 15-minute grid."""
    return round(h * 4) / 4


def fmt_t(hr: float) -> str:
    """'Tue 14:00' — same label format the demo renders."""
    t0 = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    d = t0 + timedelta(hours=hr)
    return f"{d.strftime('%a')} {d.hour:02d}:{d.minute:02d}"


def duration_h(qty_km: int, rate_kmh: float) -> float:
    return round15(qty_km / rate_kmh + CHANGEOVER_H)


def first_free_slot(board: list[BoardBlock], asset_id: str, dur: float) -> float:
    """Earliest window on the line that fits the run (board = client snapshot)."""
    t = G_START
    blocks = sorted(
        (b for b in board if b.asset_id == asset_id and b.status != "done"),
        key=lambda b: b.start,
    )
    for b in blocks:
        if t + dur <= b.start:
            return t
        t = max(t, b.start + b.dur)
    return min(t, G_END - dur)


async def plan_slot(order: Order, board: list[BoardBlock]) -> tuple[str, float, float]:
    """Pick the eligible line with the earliest opening (load balance).
    If no eligible line is up, route anyway so the veto is visible."""
    assets = await call_tool("list_assets")
    eligible = [a for a in assets if order.op in a["ops"]]
    if not eligible:
        eligible = assets
    up = [a for a in eligible if a["run"] != "down" and not a["lockout"]]
    pool = up or eligible

    best: tuple[str, float, float] | None = None
    for a in pool:
        dur = duration_h(order.qty, a["rate"])
        start = first_free_slot(board, a["id"], dur)
        if best is None or start < best[1]:
            best = (a["id"], start, dur)
    return best  # pool is never empty
