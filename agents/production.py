"""Production agent — consults the MES / ERP. Worries about line status,
capability, capacity windows, OEE and double-booking."""
from __future__ import annotations

from typing import Any

from tools import call_tool
from domain import AgentPosition, Proposal

from .base import Subagent


class ProductionAgent(Subagent):
    id = "prod"
    name = "Production"
    source = "MES / ERP"

    async def gather_facts(self, proposal: Proposal) -> dict[str, Any]:
        line = await call_tool("get_line_status", asset_id=proposal.asset_id)
        oee = await call_tool("get_oee_history", asset_id=proposal.asset_id)
        cap_h = await call_tool("get_run_window", asset_id=proposal.asset_id)
        queue = await call_tool(
            "get_queue_state",
            asset_id=proposal.asset_id,
            start_hr=proposal.start_hr,
            dur_h=proposal.dur_h,
            board=[b.model_dump() for b in proposal.board],
            exclude_order_id=proposal.order.id,
        )
        return {"line": line.model_dump(), "oee": oee.model_dump(),
                "cap_h": cap_h, "queue": queue.model_dump()}

    def hard_veto(self, facts: dict[str, Any], proposal: Proposal) -> AgentPosition | None:
        line = facts["line"]
        if line["run_state"] == "down":
            return AgentPosition(
                pos="OBJECT", veto=True, sev=3,
                why=f"{line['asset_name']} is DOWN per live status. The line isn't running — nothing can be dispatched to it.",
                tool=f'get_line_status("{line["asset_id"]}") → DOWN (live)',
            )
        return None

    def policy(self, facts: dict[str, Any], proposal: Proposal) -> AgentPosition:
        line, queue = facts["line"], facts["queue"]
        o = proposal.order
        aid = line["asset_id"]
        cap_h = facts["cap_h"]
        if o.op not in line["ops"]:
            return AgentPosition(
                pos="OBJECT", sev=2,
                why=(f"{line['asset_name']} runs {'/'.join(line['ops'])} operations — "
                     f"not a {o.op.upper()} run. Wrong equipment for this step."),
                tool=f'get_queue_state("{aid}") → op mismatch',
            )
        need = o.qty / line["rate_kmh"]
        if queue["overlap"]:
            return AgentPosition(
                pos="OBJECT", sev=2,
                why=f"Slot collides with another run on {line['asset_name']}. Line double-booked.",
                tool=f'get_queue_state("{aid}") → overlap',
            )
        if need > cap_h:
            return AgentPosition(
                pos="OBJECT", sev=2,
                why=(f"{o.qty} km at {line['rate_kmh']:g} km/h needs {need:.1f}h — exceeds the "
                     f"{cap_h:g}h continuous-run window before mandatory PM. Won't fit in one campaign."),
                tool=f'get_run_window("{aid}") → {cap_h:g}h',
            )
        oee = facts["oee"]["oee"]
        if oee < 0.6 or need > cap_h * 0.75:
            return AgentPosition(
                pos="CONCEDE", sev=1,
                why=(f"OEE {int(oee * 100)}%, {need:.1f}h run consumes most of the "
                     f"{cap_h:g}h campaign window. Tight but runnable."),
                tool=f'get_oee_history("{aid}") → {int(oee * 100)}%',
            )
        return AgentPosition(
            pos="ACCEPT", sev=0,
            why=(f"Line {line['run_state'].upper()}, OEE {int(oee * 100)}%, {o.qty} km = "
                 f"{need:.1f}h sits inside the {cap_h:g}h run window."),
            tool=f'get_line_status("{aid}") → {line["run_state"].upper()} · get_queue_state',
        )

    def policy_prompt(self) -> str:
        return (
            "OBJECT (sev 2) if the operation isn't in the line's ops, the slot overlaps an "
            "existing run, or required hours (qty/rate) exceed the continuous-run window. "
            "CONCEDE (sev 1) if OEE < 60% or the run consumes > 75% of the window. "
            "Otherwise ACCEPT (sev 0). A DOWN line is handled upstream — never veto yourself."
        )
