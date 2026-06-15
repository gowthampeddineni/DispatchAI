"""Typed results for the MCP-style tool layer. Stable signatures from Phase 1:
swapping SQLite for real MCP servers must not change these shapes."""
from __future__ import annotations

from pydantic import BaseModel


class AssetHealth(BaseModel):
    asset_id: str
    asset_name: str
    health_score: int          # 0-100 condition
    vibration_trend: str       # stable | rising
    pm_due_days: int           # negative = overdue
    open_wo_count: int
    lockout: bool


class VibrationHistory(BaseModel):
    asset_id: str
    days: int
    readings: list[float]
    threshold: float
    trend: str


class PMSchedule(BaseModel):
    asset_id: str
    pm_due_days: int
    overdue: bool


class LineStatus(BaseModel):
    asset_id: str
    asset_name: str
    run_state: str             # running | idle | down
    ops: list[str]             # operations the line can run
    rate_kmh: float
    cap_h: float               # continuous-run window before mandatory PM


class OEEHistory(BaseModel):
    asset_id: str
    oee: float                 # nominal
    recent_avg: float
    samples: int


class QueueState(BaseModel):
    asset_id: str
    blocks: int                # active blocks on this line (client board snapshot)
    overlap: bool              # requested slot collides with an existing run


class CpkTrend(BaseModel):
    part_key: str
    part_family: str
    cpk: float


class SPCAlerts(BaseModel):
    part_key: str
    active_alerts: int


class ScrapHistory(BaseModel):
    part_key: str
    scrap_pct: float


class NCRStatus(BaseModel):
    part_key: str
    part_family: str
    open_ncrs: int
    reg_hold: bool


class MaterialAvailability(BaseModel):
    part_key: str
    on_hand_km: float


class SupplierLeadTime(BaseModel):
    part_key: str
    lead_days: int


class DeliveryCommitment(BaseModel):
    order_id: str
    due_days: int
    customer: str


class CustomerTier(BaseModel):
    customer: str
    tier: str                  # T1 | T2 | T3
