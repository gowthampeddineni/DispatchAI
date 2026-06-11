"""ERP tools (Supply Chain agent's source system) + queue/state lookups.

The ERP/CRM here is a stub backed by SQLite with realistic placeholder data —
always reached through these MCP-style signatures, never queried inline."""
from __future__ import annotations

from . import sqlite_backend as db
from .registry import mcp_tool
from .types import CustomerTier, DeliveryCommitment, MaterialAvailability, SupplierLeadTime


@mcp_tool("get_material_availability", "Qualified preform / master spool stock on hand (km)", "ERP")
async def get_material_availability(part_key: str) -> MaterialAvailability:
    row = await db.fetch_one("SELECT on_hand_km FROM materials WHERE part_key = ?", (part_key,))
    if row is None:
        raise KeyError(f"Unknown part: {part_key}")
    return MaterialAvailability(part_key=part_key, on_hand_km=row["on_hand_km"])


@mcp_tool("get_supplier_lead_time", "Replenishment lead time (days) for a fiber type's material", "ERP")
async def get_supplier_lead_time(part_key: str) -> SupplierLeadTime:
    row = await db.fetch_one("SELECT lead_days FROM materials WHERE part_key = ?", (part_key,))
    if row is None:
        raise KeyError(f"Unknown part: {part_key}")
    return SupplierLeadTime(part_key=part_key, lead_days=row["lead_days"])


@mcp_tool("get_delivery_commitments", "Committed due date and customer for a work order", "ERP")
async def get_delivery_commitments(order_id: str) -> DeliveryCommitment:
    row = await db.fetch_one(
        "SELECT order_id, due_days, customer FROM work_orders WHERE order_id = ?", (order_id,)
    )
    if row is None:
        raise KeyError(f"Unknown order: {order_id}")
    return DeliveryCommitment(**row)


@mcp_tool("get_customer_tier", "CRM customer tier (T1/T2/T3)", "ERP")
async def get_customer_tier(customer: str) -> CustomerTier:
    row = await db.fetch_one("SELECT customer, tier FROM customers WHERE customer = ?", (customer,))
    if row is None:
        return CustomerTier(customer=customer, tier="T3")
    return CustomerTier(**row)


# ---- snapshot lookups used by the server to hydrate the demo frontend ----

@mcp_tool("list_assets", "All production assets with CMMS+MES signals (demo state shape)", "MES")
async def list_assets() -> list[dict]:
    rows = await db.fetch_all(
        """SELECT a.asset_id, a.asset_name, a.asset_type, a.ops, a.run_state,
                  a.lockout, a.rate_kmh, a.cap_h, a.oee, h.health_score,
                  h.vibration_trend, h.pm_due_days, h.open_wo_count
           FROM assets a JOIN asset_health h USING (asset_id)"""
    )
    # keys match the demo's ASSETS entries so the frontend hydrates 1:1
    return [
        {
            "id": r["asset_id"], "name": r["asset_name"], "type": r["asset_type"],
            "ops": r["ops"].split(","), "health": r["health_score"],
            "vib": r["vibration_trend"], "pmDays": r["pm_due_days"],
            "openWO": r["open_wo_count"], "lockout": bool(r["lockout"]),
            "run": r["run_state"], "oee": r["oee"], "rate": r["rate_kmh"],
            "capH": r["cap_h"],
        }
        for r in rows
    ]


@mcp_tool("list_parts", "All fiber types with QMMS+ERP signals (demo state shape)", "QMMS")
async def list_parts() -> dict[str, dict]:
    rows = await db.fetch_all(
        """SELECT p.part_key, p.part_family, q.cpk, q.spc_alerts, q.open_ncrs,
                  q.scrap_pct, q.reg_hold, m.on_hand_km, m.lead_days
           FROM parts p JOIN quality_status q USING (part_key)
                        JOIN materials m USING (part_key)"""
    )
    return {
        r["part_key"]: {
            "family": r["part_family"], "cpk": r["cpk"], "spc": r["spc_alerts"],
            "ncr": r["open_ncrs"], "scrap": r["scrap_pct"],
            "matAvail": r["on_hand_km"], "lead": r["lead_days"],
            "regHold": bool(r["reg_hold"]),
        }
        for r in rows
    }


@mcp_tool("list_work_orders", "The incoming order queue (demo state shape)", "ERP")
async def list_work_orders() -> list[dict]:
    rows = await db.fetch_all(
        """SELECT w.order_id, w.part_key, w.op, w.qty_km, w.due_days,
                  w.customer, c.tier
           FROM work_orders w JOIN customers c USING (customer)"""
    )
    return [
        {
            "id": r["order_id"], "part": r["part_key"], "op": r["op"],
            "qty": r["qty_km"], "due": r["due_days"], "cust": r["customer"],
            "tier": r["tier"],
        }
        for r in rows
    ]
