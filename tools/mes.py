"""MES / ERP line tools (Production agent's source system)."""
from __future__ import annotations

from . import sqlite_backend as db
from .registry import mcp_tool
from .types import LineStatus, OEEHistory, QueueState


@mcp_tool("get_line_status", "Live run state and capability (ops, rate, run window) of a line", "MES")
async def get_line_status(asset_id: str) -> LineStatus:
    row = await db.fetch_one(
        "SELECT asset_id, asset_name, run_state, ops, rate_kmh, cap_h FROM assets WHERE asset_id = ?",
        (asset_id,),
    )
    if row is None:
        raise KeyError(f"Unknown asset: {asset_id}")
    return LineStatus(**{**row, "ops": row["ops"].split(",")})


@mcp_tool("get_run_window", "Max continuous-run window (h) before mandatory PM/changeover", "MES")
async def get_run_window(asset_id: str) -> float:
    row = await db.fetch_one("SELECT cap_h FROM assets WHERE asset_id = ?", (asset_id,))
    if row is None:
        raise KeyError(f"Unknown asset: {asset_id}")
    return row["cap_h"]


@mcp_tool("get_oee_history", "Nominal and recent OEE for a line", "MES")
async def get_oee_history(asset_id: str) -> OEEHistory:
    asset = await db.fetch_one("SELECT oee FROM assets WHERE asset_id = ?", (asset_id,))
    if asset is None:
        raise KeyError(f"Unknown asset: {asset_id}")
    rows = await db.fetch_all("SELECT oee FROM oee_history WHERE asset_id = ?", (asset_id,))
    vals = [r["oee"] for r in rows]
    return OEEHistory(
        asset_id=asset_id,
        oee=asset["oee"],
        recent_avg=round(sum(vals) / len(vals), 3) if vals else asset["oee"],
        samples=len(vals),
    )


@mcp_tool("get_queue_state", "Booked blocks on a line and whether a slot collides (from the live board)", "MES")
async def get_queue_state(
    asset_id: str,
    start_hr: float,
    dur_h: float,
    board: list[dict] | None = None,
    exclude_order_id: str | None = None,
) -> QueueState:
    """The Gantt board is live UI state owned by the client; the snapshot is
    passed in so this tool stays pure (input -> output, no hidden state)."""
    blocks = [
        b for b in (board or [])
        if b.get("asset_id") == asset_id
        and b.get("status") != "done"
        and b.get("order_id") != exclude_order_id
    ]
    overlap = any(
        start_hr < b["start"] + b["dur"] and start_hr + dur_h > b["start"]
        for b in blocks
    )
    return QueueState(asset_id=asset_id, blocks=len(blocks), overlap=overlap)
