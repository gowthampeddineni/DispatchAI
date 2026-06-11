"""CMMS tools (Maintenance agent's source system)."""
from __future__ import annotations

from . import sqlite_backend as db
from .registry import mcp_tool
from .types import AssetHealth, PMSchedule, VibrationHistory


@mcp_tool("get_asset_health", "Condition score, vibration trend, PM status and lockout for an asset", "CMMS")
async def get_asset_health(asset_id: str) -> AssetHealth:
    row = await db.fetch_one(
        """SELECT a.asset_id, a.asset_name, a.lockout, h.health_score,
                  h.vibration_trend, h.pm_due_days, h.open_wo_count
           FROM assets a JOIN asset_health h USING (asset_id)
           WHERE a.asset_id = ?""",
        (asset_id,),
    )
    if row is None:
        raise KeyError(f"Unknown asset: {asset_id}")
    return AssetHealth(**{**row, "lockout": bool(row["lockout"])})


@mcp_tool("get_vibration_history", "Recent vibration readings (mm/s) for an asset", "CMMS")
async def get_vibration_history(asset_id: str, days: int = 30) -> VibrationHistory:
    rows = await db.fetch_all(
        """SELECT value_mm_s, threshold FROM vibration_readings
           WHERE asset_id = ? AND day_offset <= ? ORDER BY day_offset DESC""",
        (asset_id, days),
    )
    health = await db.fetch_one("SELECT vibration_trend FROM asset_health WHERE asset_id = ?", (asset_id,))
    return VibrationHistory(
        asset_id=asset_id,
        days=days,
        readings=[r["value_mm_s"] for r in rows],
        threshold=rows[0]["threshold"] if rows else 4.5,
        trend=health["vibration_trend"] if health else "stable",
    )


@mcp_tool("get_pm_schedule", "Preventive-maintenance due date for an asset", "CMMS")
async def get_pm_schedule(asset_id: str) -> PMSchedule:
    row = await db.fetch_one("SELECT pm_due_days FROM asset_health WHERE asset_id = ?", (asset_id,))
    if row is None:
        raise KeyError(f"Unknown asset: {asset_id}")
    return PMSchedule(asset_id=asset_id, pm_due_days=row["pm_due_days"], overdue=row["pm_due_days"] < 0)
