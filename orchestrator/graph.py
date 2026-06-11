"""LangGraph orchestrator.

    plan ──▶ maint ─┐
        ├──▶ prod ──┼──▶ verdict
        ├──▶ qual ──┤
        └──▶ supp ──┘

The plan node decides which subagents to invoke; the conditional edge fans
them out **concurrently** (one LangGraph super-step). Each agent streams its
position the moment it lands via the `emit` callback in the run config, so the
WebSocket never waits for the slowest agent. The verdict node aggregates the
vote, applies the familiarity safety net and emits the terminal verdict."""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from agents import AGENT_META, AGENTS, Subagent
from config import settings
from domain import AgentPosition, Proposal, Verdict

from .state import NegotiationState
from .verdict import build_verdict

log = logging.getLogger("dispatchai.orchestrator")

# emit(event_type, agent_id, payload) — provided by the server per run
Emit = Callable[[str, str | None, dict[str, Any]], Awaitable[None]]


def _emitter(config: RunnableConfig) -> Emit | None:
    return (config.get("configurable") or {}).get("emit")


async def plan_node(state: NegotiationState, config: RunnableConfig) -> dict:
    """Route the request: every dispatch decision needs all four sign-offs.
    (Conditional routing point — trim the plan here for cheaper requests.)"""
    return {"plan": list(AGENTS.keys()), "positions": {}, "errors": {}}


def route_plan(state: NegotiationState) -> list[str]:
    return state["plan"]


def make_agent_node(agent: Subagent):
    async def node(state: NegotiationState, config: RunnableConfig) -> dict:
        emit = _emitter(config)
        if emit:
            await emit("agent_started", agent.id, {"agent": AGENT_META[agent.id]})

        position: AgentPosition | None = None
        error: str | None = None
        for attempt in (1, 2):  # one retry, then degrade
            try:
                position = await agent.assess(state["proposal"])
                break
            except Exception as exc:
                error = str(exc)
                log.warning("%s agent attempt %d failed: %s", agent.id, attempt, exc)

        if position is None:  # graceful degradation: don't kill the run
            if emit:
                await emit("agent_degraded", agent.id, {"error": error or "unknown"})
            position = AgentPosition(
                pos="CONCEDE", sev=1,
                why=f"{agent.name} agent unavailable — degraded response, treat with caution.",
                tool=f"({agent.source} unreachable)",
            )

        if emit:
            await emit("agent_position", agent.id, position.model_dump())
        out: dict = {"positions": {agent.id: position}}
        if error and position.tool.endswith("unreachable)"):
            out["errors"] = {agent.id: error}
        return out

    return node


async def _synthesize_note(proposal: Proposal, verdict: Verdict) -> str:
    """Large-model synthesis of the orchestrator note (complex reasoning tier).
    Deterministic note is the grounding and the fallback; outcome/confidence
    never change here."""
    from langchain_core.messages import HumanMessage, SystemMessage
    from agents.llm import chat_model

    positions = {
        k: ("HARD VETO — " if v.veto else "") + f"{v.pos}: {v.why}"
        for k, v in verdict.positions.items()
    }
    llm = chat_model("synthesis")
    msg = await llm.ainvoke([
        SystemMessage(content=(
            "You are the Orchestrator of a multi-agent factory scheduler. "
            "In <=2 sentences, name the decisive conflicts behind this verdict, "
            "plant-floor tone. Do not change or restate the verdict word itself."
        )),
        HumanMessage(content=(
            f"Order {proposal.order.id} ({proposal.order.qty} km {proposal.order.op}) "
            f"on {proposal.asset_id}. Outcome {verdict.outcome}. "
            f"Votes: {verdict.acc} accept / {verdict.con} concede / {verdict.obj} object. "
            f"Positions: {positions} "
            f"Deterministic note: {verdict.note}"
        )),
    ])
    text = (msg.content or "").strip()
    return text or verdict.note


async def verdict_node(state: NegotiationState, config: RunnableConfig) -> dict:
    emit = _emitter(config)
    proposal = state["proposal"]
    verdict = await build_verdict(proposal, state["positions"])

    if settings.llm_enabled:
        try:
            verdict = verdict.model_copy(update={"note": await _synthesize_note(proposal, verdict)})
        except Exception as exc:
            log.warning("synthesis LLM failed (%s) — keeping deterministic note", exc)

    if emit:
        await emit("orchestrator_note", "orchestrator", {
            "note": verdict.note,
            "confidence": verdict.confidence,
            "familiarity": verdict.familiarity.model_dump(),
        })
        await emit("verdict", "orchestrator", {
            "outcome": verdict.outcome,
            "acc": verdict.acc, "con": verdict.con, "obj": verdict.obj,
            "note": verdict.note,
            "confidence": verdict.confidence,
            "familiarity": verdict.familiarity.model_dump(),
            "suggested_fix": verdict.suggested_fix,
            "positions": {k: v.model_dump() for k, v in verdict.positions.items()},
            "schedule": {
                "order": proposal.order.model_dump(),
                "part_key": proposal.part_key,
                "asset_id": proposal.asset_id,
                "start_hr": proposal.start_hr,
                "dur_h": proposal.dur_h,
            },
        })
    return {"verdict": verdict}


def build_graph():
    g = StateGraph(NegotiationState)
    g.add_node("plan", plan_node)
    for aid, agent in AGENTS.items():
        g.add_node(aid, make_agent_node(agent))
        g.add_edge(aid, "verdict")
    g.add_node("verdict", verdict_node)
    g.add_edge(START, "plan")
    g.add_conditional_edges("plan", route_plan, list(AGENTS.keys()))
    g.add_edge("verdict", END)
    return g.compile()


GRAPH = build_graph()


async def run_negotiation(
    proposal: Proposal, emit: Emit | None = None, run_id: str | None = None
) -> Verdict:
    """One end-to-end dispatch negotiation. The run_id tag makes the whole
    request (orchestrator + 4 agents + every tool call) one LangSmith trace."""
    config: RunnableConfig = {
        "configurable": {"emit": emit},
        "run_name": f"dispatch:{proposal.order.id}",
        "tags": [t for t in ("dispatchai", run_id) if t],
        "metadata": {"run_id": run_id, "order_id": proposal.order.id,
                     "asset_id": proposal.asset_id},
    }
    result = await GRAPH.ainvoke({"proposal": proposal}, config=config)
    return result["verdict"]
