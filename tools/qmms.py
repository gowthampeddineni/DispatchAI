"""QMMS tools (Quality agent's source system)."""
from __future__ import annotations

from . import sqlite_backend as db
from .registry import mcp_tool
from .types import CpkTrend, NCRStatus, ScrapHistory, SPCAlerts


async def _quality_row(part_key: str) -> dict:
    row = await db.fetch_one(
        """SELECT p.part_key, p.part_family, q.cpk, q.spc_alerts, q.open_ncrs,
                  q.scrap_pct, q.reg_hold
           FROM parts p JOIN quality_status q USING (part_key)
           WHERE p.part_key = ?""",
        (part_key,),
    )
    if row is None:
        raise KeyError(f"Unknown part: {part_key}")
    return row


@mcp_tool("get_cpk_trend", "Process capability (Cpk) on the critical optical spec for a fiber type", "QMMS")
async def get_cpk_trend(part_key: str) -> CpkTrend:
    row = await _quality_row(part_key)
    return CpkTrend(part_key=row["part_key"], part_family=row["part_family"], cpk=row["cpk"])


@mcp_tool("get_active_spc_alerts", "Active SPC excursions for a fiber type", "QMMS")
async def get_active_spc_alerts(part_key: str) -> SPCAlerts:
    row = await _quality_row(part_key)
    return SPCAlerts(part_key=part_key, active_alerts=row["spc_alerts"])


@mcp_tool("get_scrap_history", "Recent scrap percentage for a fiber type", "QMMS")
async def get_scrap_history(part_key: str) -> ScrapHistory:
    row = await _quality_row(part_key)
    return ScrapHistory(part_key=part_key, scrap_pct=row["scrap_pct"])


@mcp_tool("get_open_ncrs", "Open NCRs and customer qualification holds for a fiber type", "QMMS")
async def get_open_ncrs(part_key: str) -> NCRStatus:
    row = await _quality_row(part_key)
    return NCRStatus(
        part_key=part_key,
        part_family=row["part_family"],
        open_ncrs=row["open_ncrs"],
        reg_hold=bool(row["reg_hold"]),
    )
