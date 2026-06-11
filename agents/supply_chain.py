"""Supply Chain agent — consults the ERP. Worries about material on hand and
lead time vs. the committed due date."""
from __future__ import annotations

from typing import Any

from tools import call_tool
from domain import AgentPosition, Proposal

from .base import Subagent


def _material_name(op: str) -> str:
    return "qualified preform" if op == "draw" else "master spool stock"


class SupplyChainAgent(Subagent):
    id = "supp"
    name = "Supply Chain"
    source = "ERP"

    async def gather_facts(self, proposal: Proposal) -> dict[str, Any]:
        mat = await call_tool("get_material_availability", part_key=proposal.part_key)
        lead = await call_tool("get_supplier_lead_time", part_key=proposal.part_key)
        tier = await call_tool("get_customer_tier", customer=proposal.order.cust)
        ncr = await call_tool("get_open_ncrs", part_key=proposal.part_key)  # for family label
        return {
            "material": mat.model_dump(),
            "lead_days": lead.lead_days,
            "tier": tier.tier,
            "part_family": ncr.part_family,
        }

    def hard_veto(self, facts: dict[str, Any], proposal: Proposal) -> AgentPosition | None:
        o = proposal.order
        avail = facts["material"]["on_hand_km"]
        if avail < o.qty:
            return AgentPosition(
                pos="OBJECT", veto=True, sev=3,
                why=(f"Only {avail:g} km of {_material_name(o.op)} for a {o.qty} km run. "
                     "Can't draw what isn't there."),
                tool=f'get_material_availability("{facts["part_family"]}") → {avail:g} km',
            )
        return None

    def policy(self, facts: dict[str, Any], proposal: Proposal) -> AgentPosition:
        o = proposal.order
        lead, tier = facts["lead_days"], facts["tier"]
        mat_name = _material_name(o.op)
        if lead > o.due:
            return AgentPosition(
                pos="OBJECT", sev=2,
                why=f"{mat_name} lead time {lead}d but commitment due in {o.due}d. Can't make the date.",
                tool=f'get_supplier_lead_time → {lead}d · get_delivery_commitments',
            )
        if lead >= o.due - 1 or (tier == "T1" and lead >= o.due - 2):
            return AgentPosition(
                pos="CONCEDE", sev=1,
                why=(f"{o.cust} ({tier}) {mat_name} buffer is tight against the "
                     f"{o.due}d date. Acceptable with priority."),
                tool=f'get_customer_tier("{o.cust}") → {tier}',
            )
        return AgentPosition(
            pos="ACCEPT", sev=0,
            why=f"{mat_name} on hand, lead {lead}d clears the {o.due}d commitment for {o.cust}.",
            tool=f'get_delivery_commitments("{o.id}") → on time',
        )

    def policy_prompt(self) -> str:
        return (
            "OBJECT (sev 2) if material lead time exceeds the due date. "
            "CONCEDE (sev 1) if lead time >= due-1 days, or the customer is T1 and "
            "lead time >= due-2 days (tight buffer). Otherwise ACCEPT (sev 0). "
            "Missing material is handled upstream — never veto yourself."
        )
