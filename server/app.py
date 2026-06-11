"""FastAPI server: WebSocket endpoint streaming multi-agent negotiations to
the demo, plus static serving of the live frontend."""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import ValidationError

import tools
from config import settings
from domain import Order, Proposal
from orchestrator import duration_h, fmt_t, plan_slot, run_negotiation
from server.schema import Envelope, ScheduleOrder, TERMINAL_TYPES

log = logging.getLogger("dispatchai.server")
FRONTEND = Path(__file__).resolve().parent.parent / "frontend" / "dispatchai-demo-live.html"

app = FastAPI(title="DispatchAI multi-agent backend", version="0.1.0")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(FRONTEND, media_type="text/html")


@app.get("/healthz")
async def healthz() -> dict:
    return {"ok": True, "llm": settings.llm_enabled,
            "tools": len(tools.list_tools()), "db": str(settings.db_path)}


async def _state_payload() -> dict:
    return {
        "assets": await tools.call_tool("list_assets"),
        "parts": await tools.call_tool("list_parts"),
        "orders": await tools.call_tool("list_work_orders"),
    }


class RunStream:
    """Per-negotiation envelope writer with a monotonic seq."""

    def __init__(self, ws: WebSocket, run_id: str):
        self.ws, self.run_id, self.seq = ws, run_id, 0
        self.lock = asyncio.Lock()

    async def send(self, etype: str, agent_id: str | None, payload: dict,
                   terminal: bool | None = None) -> None:
        async with self.lock:  # agents emit concurrently — keep seq consistent
            frame = Envelope(
                type=etype, run_id=self.run_id, seq=self.seq, agent_id=agent_id,
                terminal=(etype in TERMINAL_TYPES) if terminal is None else terminal,
                payload=payload,
            )
            self.seq += 1
            await self.ws.send_text(frame.model_dump_json())


async def _resolve_order(msg: ScheduleOrder) -> Order:
    if msg.order is not None:
        return msg.order
    queue = await tools.call_tool("list_work_orders")
    row = next((o for o in queue if o["id"] == msg.order_id), None)
    if row is None:
        raise ValueError(f"Unknown order: {msg.order_id}")
    return Order(**row)


async def handle_schedule_order(ws: WebSocket, msg: ScheduleOrder) -> None:
    run_id = uuid.uuid4().hex[:12]
    stream = RunStream(ws, run_id)
    try:
        order = await _resolve_order(msg)

        if msg.asset_id is None or msg.start_hr is None:
            asset_id, start_hr, dur_h = await plan_slot(order, msg.board)
        else:
            assets = await tools.call_tool("list_assets")
            asset = next((a for a in assets if a["id"] == msg.asset_id), None)
            if asset is None:
                raise ValueError(f"Unknown asset: {msg.asset_id}")
            asset_id, start_hr = msg.asset_id, msg.start_hr
            dur_h = duration_h(order.qty, asset["rate"])

        assets = await tools.call_tool("list_assets")
        asset = next(a for a in assets if a["id"] == asset_id)
        parts = await tools.call_tool("list_parts")

        proposal = Proposal(
            order=order, part_key=order.part, asset_id=asset_id,
            start_hr=start_hr, dur_h=dur_h, board=msg.board,
            fam_spread=msg.fam_spread,
        )

        await stream.send("run_started", None, {
            "order": order.model_dump(),
            "part_key": order.part,
            "part_family": parts.get(order.part, {}).get("family", order.part),
            "asset_id": asset_id,
            "asset_name": asset["name"],
            "start_hr": start_hr,
            "start_label": fmt_t(start_hr),
            "dur_h": dur_h,
            "qty_km": order.qty,
            "customer": order.cust,
        })

        await run_negotiation(proposal, stream.send, run_id)

    except Exception as exc:
        log.exception("negotiation failed")
        await stream.send("error", None, {"message": str(exc)}, terminal=True)


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    log.info("demo connected")
    try:
        while True:
            raw = await ws.receive_text()
            try:
                data = json.loads(raw)
                mtype = data.get("type")
            except json.JSONDecodeError:
                await ws.send_text(Envelope(type="error", payload={"message": "invalid JSON"}).model_dump_json())
                continue

            if mtype == "ping":
                await ws.send_text(Envelope(type="pong").model_dump_json())
            elif mtype == "get_state":
                await ws.send_text(Envelope(type="state", payload=await _state_payload()).model_dump_json())
            elif mtype == "schedule_order":
                try:
                    msg = ScheduleOrder(**data)
                except ValidationError as exc:
                    await ws.send_text(Envelope(
                        type="error", terminal=True,
                        payload={"message": f"bad schedule_order: {exc.errors()[:2]}"},
                    ).model_dump_json())
                    continue
                await handle_schedule_order(ws, msg)
            else:
                await ws.send_text(Envelope(
                    type="error", payload={"message": f"unknown message type: {mtype}"}
                ).model_dump_json())
    except WebSocketDisconnect:
        log.info("demo disconnected")
