"""Shared typed domain models (the language agents, orchestrator and server speak)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

CRIT_CPK = 1.0  # capability floor on the critical optical spec

Pos = Literal["ACCEPT", "CONCEDE", "OBJECT"]
Outcome = Literal["COMMIT", "ESCALATE", "REJECT"]


class Order(BaseModel):
    id: str
    part: str                   # fiber type key, e.g. SMF-G652D
    op: str                     # draw | spool | test | split | respool
    qty: int                    # km
    due: int                    # days until commitment
    cust: str
    tier: str = "T2"


class BoardBlock(BaseModel):
    order_id: str
    asset_id: str
    start: float                # hours from plant t0
    dur: float
    status: str = "committed"


class Proposal(BaseModel):
    """One concrete dispatch proposal: order X on asset Y at hour Z."""
    order: Order
    part_key: str
    asset_id: str
    start_hr: float
    dur_h: float
    board: list[BoardBlock] = Field(default_factory=list)
    fam_spread: float = 1.0     # client's learned familiarity spread (CHECK/ACT)


class AgentPosition(BaseModel):
    pos: Pos
    veto: bool = False          # hard, non-negotiable stop
    sev: int = 0                # 0 accept · 1 concede · 2 object · 3 veto
    why: str
    tool: str                   # the tool-call trail shown in the UI


class Familiarity(BaseModel):
    z: float
    zone: Literal["familiar", "marginal", "outlier"]
    pct: float


class Verdict(BaseModel):
    outcome: Outcome
    acc: int
    con: int
    obj: int
    note: str
    confidence: float
    familiarity: Familiarity
    suggested_fix: str | None = None
    positions: dict[str, AgentPosition]
