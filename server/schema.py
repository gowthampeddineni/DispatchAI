"""Versioned WebSocket message schema (see docs/websocket-contract.md)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

from domain import BoardBlock, Order

CONTRACT_VERSION = 1

EventType = Literal[
    "state", "run_started", "agent_started", "agent_position", "agent_degraded",
    "orchestrator_note", "verdict", "error", "pong",
    "chat_started", "chat_tool_call", "chat_response",
]

TERMINAL_TYPES = {"verdict", "chat_response"}


class Envelope(BaseModel):
    """Every server→client frame."""
    v: int = CONTRACT_VERSION
    type: EventType
    run_id: str | None = None
    seq: int = 0
    ts: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    agent_id: str | None = None
    terminal: bool = False
    payload: dict[str, Any] = Field(default_factory=dict)


# ---- client → server ----

class GetState(BaseModel):
    type: Literal["get_state"]


class ScheduleOrder(BaseModel):
    type: Literal["schedule_order"]
    order: Order | None = None
    order_id: str | None = None          # alternative: resolve from the DB queue
    asset_id: str | None = None          # omitted -> server plans the slot
    start_hr: float | None = None
    fam_spread: float = 1.0
    board: list[BoardBlock] = Field(default_factory=list)


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatMessage(BaseModel):
    type: Literal["chat"]
    text: str
    history: list[ChatTurn] = Field(default_factory=list)   # client keeps the transcript
    board: list[BoardBlock] = Field(default_factory=list)   # current Gantt snapshot


class Ping(BaseModel):
    type: Literal["ping"]
