"""Plant copilot: a tool-calling chat agent over the same MCP tool layer.

Every question is answered from live source-system data — the LLM decides
which CMMS / MES / QMMS / ERP tools to call, each call is streamed to the
frontend as a `chat_tool_call` event (so the user can SEE the backend at
work), and the final answer arrives as a terminal `chat_response`.

It can also run a real dry-run negotiation (`negotiate_order`) — the full
LangGraph fan-out across all four agents — and explain the verdict.

Without an OPENAI_API_KEY the copilot degrades to a deterministic lookup
mode (order / asset / fiber-type questions still work, fully tool-backed).
"""
from __future__ import annotations

import inspect
import json
import logging
import re
from typing import Any, Awaitable, Callable

from pydantic import BaseModel

import tools
from config import settings
from domain import BoardBlock, Order, Proposal
from orchestrator import fmt_t, plan_slot, run_negotiation
from server.schema import ChatMessage

log = logging.getLogger("dispatchai.chat")

Send = Callable[..., Awaitable[None]]  # RunStream.send(etype, agent_id, payload)

MAX_TOOL_ROUNDS = 5
_JSON_TYPES = {str: "string", int: "integer", float: "number", bool: "boolean",
               "str": "string", "int": "integer", "float": "number", "bool": "boolean"}
_CHAT_EXCLUDED = {"get_queue_state"}   # takes a board snapshot — not chat-friendly


def _dump(obj: Any) -> Any:
    if isinstance(obj, BaseModel):
        return obj.model_dump()
    if isinstance(obj, list):
        return [_dump(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _dump(v) for k, v in obj.items()}
    return obj


def _tool_schemas() -> list[dict]:
    """OpenAI tool schemas straight from the MCP registry signatures, so the
    chat agent always offers exactly what the registry serves."""
    schemas = []
    for spec in tools.list_tools():
        if spec.name in _CHAT_EXCLUDED:
            continue
        sig = inspect.signature(inspect.unwrap(spec.fn))
        props: dict[str, dict] = {}
        required: list[str] = []
        for pname, p in sig.parameters.items():
            props[pname] = {"type": _JSON_TYPES.get(p.annotation, "string")}
            if p.default is inspect.Parameter.empty:
                required.append(pname)
        schemas.append({
            "type": "function",
            "function": {
                "name": spec.name,
                "description": f"[{spec.source_system}] {spec.description}",
                "parameters": {"type": "object", "properties": props, "required": required},
            },
        })
    schemas.append({
        "type": "function",
        "function": {
            "name": "negotiate_order",
            "description": (
                "[ORCHESTRATOR] Dry-run the full four-agent negotiation "
                "(Maintenance, Production, Quality, Supply Chain in parallel) for a "
                "queued work order and return the verdict, every agent position and "
                "the suggested fix. Use for 'what would happen if…' / 'why does WO-x "
                "fail' questions. Nothing is scheduled."
            ),
            "parameters": {
                "type": "object",
                "properties": {"order_id": {"type": "string", "description": "e.g. WO-4480"}},
                "required": ["order_id"],
            },
        },
    })
    return schemas


async def _negotiate(order_id: str, board: list[BoardBlock]) -> dict:
    """Chat-only tool: a real (but side-effect-free) negotiation dry run."""
    queue = await tools.call_tool("list_work_orders")
    row = next((o for o in queue if o["id"].upper() == order_id.upper()), None)
    if row is None:
        return {"error": f"{order_id} is not in the work-order queue"}
    order = Order(**row)
    asset_id, start_hr, dur_h = await plan_slot(order, board)
    verdict = await run_negotiation(Proposal(
        order=order, part_key=order.part, asset_id=asset_id,
        start_hr=start_hr, dur_h=dur_h, board=board,
    ))
    return {
        "order": row,
        "planned_slot": {"asset_id": asset_id, "start": fmt_t(start_hr), "dur_h": dur_h},
        "outcome": verdict.outcome,
        "confidence": verdict.confidence,
        "note": verdict.note,
        "familiarity": verdict.familiarity.model_dump(),
        "suggested_fix": verdict.suggested_fix,
        "positions": {k: v.model_dump() for k, v in verdict.positions.items()},
    }


async def _call(name: str, args: dict, board: list[BoardBlock]) -> Any:
    if name == "negotiate_order":
        return await _negotiate(args.get("order_id", ""), board)
    return await tools.call_tool(name, **args)


def _source_of(name: str) -> str:
    if name == "negotiate_order":
        return "ORCHESTRATOR"
    spec = next((s for s in tools.list_tools() if s.name == name), None)
    return spec.source_system if spec else "?"


async def _system_prompt() -> str:
    assets = await tools.call_tool("list_assets")
    parts = await tools.call_tool("list_parts")
    queue = await tools.call_tool("list_work_orders")
    asset_lines = "\n".join(
        f"- {a['id']} · {a['name']} ({a['type']}, ops {'/'.join(a['ops'])}) — "
        f"run:{a['run']} health:{a['health']} OEE:{a['oee']}"
        + (" · LOCKOUT" if a["lockout"] else "")
        for a in assets
    )
    part_lines = "\n".join(
        f"- {k} ({p['family']}) — Cpk {p['cpk']}, stock {p['matAvail']} km, lead {p['lead']}d"
        + (" · REG HOLD" if p["regHold"] else "")
        for k, p in parts.items()
    )
    return f"""You are the DispatchAI plant copilot for an optical-fiber plant scheduler.
A LangGraph orchestrator dispatches work orders by fanning out four LangChain agents in
parallel — Maintenance (CMMS), Production (MES/ERP), Quality (QMMS), Supply Chain (ERP).
Each answers ACCEPT / CONCEDE / OBJECT or raises a hard VETO; the orchestrator then rules
COMMIT / ESCALATE / REJECT.

Decision rules you can explain:
- Hard vetoes (never overridable): maintenance lockout · line down · regulatory hold ·
  Cpk < 1.00 · insufficient qualified material.
- Maintenance: health<45 or (vibration rising + PM overdue + ≥2 open WOs) → OBJECT;
  health<65 or PM overdue or vibration rising → CONCEDE.
- Production: wrong equipment / double-booked / run exceeds continuous-run window → OBJECT;
  OEE<0.60 or run needs >75% of the window → CONCEDE.
- Quality: Cpk<1.15 → OBJECT; Cpk<1.33 or open SPC alerts or open NCRs → CONCEDE.
- Supply Chain: replenishment lead > due date → OBJECT; lead ≥ due−1 (T1 customers: due−2) → CONCEDE.
- Verdict: any veto → REJECT; ≥3 objections → REJECT; ≥1 objection → ESCALATE to a human;
  all four concede → ESCALATE; otherwise COMMIT (confidence 0.6 + 0.1·accepts, cap 0.95).
  An unfamiliar/outlier proposal (familiarity z-score) downgrades COMMIT to ESCALATE.

Plant snapshot (live — re-check with tools when asked about specifics):
{asset_lines}

Fiber types:
{part_lines}

Order queue: {len(queue)} pending (first: {', '.join(o['id'] for o in queue[:6])}…).
Use list_work_orders for the full queue.

Always ground answers in tool data — call tools rather than guessing, and cite the numbers
you used. For "what if I schedule X" questions call negotiate_order. Keep answers tight
(usually under 150 words), plant-floor tone, light markdown (bold, bullets). You cannot
modify the schedule yourself — the planner does that on the board."""


# ---------------------------------------------------------------- LLM path

async def _llm_chat(msg: ChatMessage, send: Send) -> str:
    from langchain_core.messages import (AIMessage, HumanMessage, SystemMessage,
                                         ToolMessage)

    from agents.llm import chat_model

    history = [
        HumanMessage(content=t.content) if t.role == "user" else AIMessage(content=t.content)
        for t in msg.history[-16:]
    ]
    board_note = (
        "Currently scheduled blocks (client board): "
        + json.dumps([b.model_dump() for b in msg.board])
    ) if msg.board else "The schedule board is currently empty."

    messages: list = [
        SystemMessage(content=await _system_prompt()),
        SystemMessage(content=board_note),
        *history,
        HumanMessage(content=msg.text),
    ]

    llm = chat_model("chat").bind_tools(_tool_schemas())
    for _ in range(MAX_TOOL_ROUNDS):
        ai = await llm.ainvoke(messages)
        messages.append(ai)
        if not ai.tool_calls:
            return ai.content if isinstance(ai.content, str) else str(ai.content)
        for tc in ai.tool_calls:
            await send("chat_tool_call", None, {
                "tool": tc["name"], "source": _source_of(tc["name"]), "args": tc["args"],
            })
            try:
                result = _dump(await _call(tc["name"], tc["args"], msg.board))
            except Exception as exc:
                result = {"error": str(exc)}
            messages.append(ToolMessage(
                content=json.dumps(result, default=str), tool_call_id=tc["id"],
            ))

    final = await chat_model("chat").ainvoke(messages)   # tool budget spent — answer now
    return final.content if isinstance(final.content, str) else str(final.content)


# -------------------------------------------------------------- rules path

_WO_RE = re.compile(r"\bWO-\d+\b", re.IGNORECASE)


async def _rules_chat(msg: ChatMessage, send: Send) -> str:
    """No-LLM fallback: deterministic, still fully tool-backed."""
    text = msg.text.lower()

    if m := _WO_RE.search(msg.text):
        await send("chat_tool_call", None,
                   {"tool": "negotiate_order", "source": "ORCHESTRATOR",
                    "args": {"order_id": m.group().upper()}})
        r = await _negotiate(m.group().upper(), msg.board)
        if "error" in r:
            return r["error"] + ". Try an id from the queue panel."
        pos = "\n".join(
            f"- **{k}**: {v['pos']}{' · VETO' if v['veto'] else ''} — {v['why']}"
            for k, v in r["positions"].items()
        )
        fix = f"\n\n💡 {r['suggested_fix']}" if r.get("suggested_fix") else ""
        return (f"Dry-run for **{r['order']['id']}** → {r['planned_slot']['asset_id']} "
                f"@ {r['planned_slot']['start']} ({r['planned_slot']['dur_h']}h):\n\n"
                f"**{r['outcome']}** (confidence {r['confidence']:.2f}) — {r['note']}\n{pos}{fix}")

    assets = await tools.call_tool("list_assets")
    if a := next((a for a in assets
                  if a["id"].lower() in text or a["name"].lower() in text), None):
        await send("chat_tool_call", None,
                   {"tool": "get_asset_health", "source": "CMMS", "args": {"asset_id": a["id"]}})
        health = _dump(await tools.call_tool("get_asset_health", asset_id=a["id"]))
        await send("chat_tool_call", None,
                   {"tool": "get_line_status", "source": "MES", "args": {"asset_id": a["id"]}})
        line = _dump(await tools.call_tool("get_line_status", asset_id=a["id"]))
        return (f"**{a['name']}** ({a['id']}): health **{health['health_score']}**, vibration "
                f"{health['vibration_trend']}, PM due in {health['pm_due_days']}d, "
                f"{health['open_wo_count']} open WOs"
                + (", **LOCKOUT active**" if health["lockout"] else "")
                + f". Line is **{line['run_state']}**, rate {line['rate_kmh']} km/h, "
                f"window {line['cap_h']}h, OEE {a['oee']}.")

    parts = await tools.call_tool("list_parts")
    if k := next((k for k, p in parts.items()
                  if k.lower() in text or p["family"].lower() in text), None):
        await send("chat_tool_call", None,
                   {"tool": "get_cpk_trend", "source": "QMMS", "args": {"part_key": k}})
        p = parts[k]
        return (f"**{k}** ({p['family']}): Cpk **{p['cpk']}**, {p['spc']} SPC alerts, "
                f"{p['ncr']} open NCRs, scrap {p['scrap']}%"
                + (", **regulatory hold**" if p["regHold"] else "")
                + f". Material: {p['matAvail']} km on hand, {p['lead']}d lead time.")

    return ("I can answer from live plant systems — try:\n"
            "- *“Why would **WO-4480** fail?”* (runs the real 4-agent negotiation)\n"
            "- *“How is **Draw Tower 2** doing?”* (CMMS + MES)\n"
            "- *“Status of **MMF-OM4**?”* (QMMS + ERP)\n\n"
            "Set `OPENAI_API_KEY` to unlock free-form questions.")


# ----------------------------------------------------------------- entry

async def handle_chat(msg: ChatMessage, send: Send) -> None:
    await send("chat_started", None, {"llm": settings.llm_enabled})
    try:
        if settings.llm_enabled:
            answer = await _llm_chat(msg, send)
        else:
            answer = await _rules_chat(msg, send)
    except Exception as exc:
        log.exception("chat failed")
        answer = f"Something went wrong answering that: {exc}"
    await send("chat_response", None, {"text": answer})
