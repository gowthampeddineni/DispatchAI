"""Quality agent — consults the QMMS. Worries about Cpk, SPC alerts, NCRs and
regulatory / customer-qualification holds."""
from __future__ import annotations

from typing import Any

from tools import call_tool
from domain import CRIT_CPK, AgentPosition, Proposal

from .base import Subagent


class QualityAgent(Subagent):
    id = "qual"
    name = "Quality"
    source = "QMMS"

    async def gather_facts(self, proposal: Proposal) -> dict[str, Any]:
        cpk = await call_tool("get_cpk_trend", part_key=proposal.part_key)
        spc = await call_tool("get_active_spc_alerts", part_key=proposal.part_key)
        scrap = await call_tool("get_scrap_history", part_key=proposal.part_key)
        ncr = await call_tool("get_open_ncrs", part_key=proposal.part_key)
        return {"cpk": cpk.model_dump(), "spc": spc.model_dump(),
                "scrap": scrap.model_dump(), "ncr": ncr.model_dump()}

    def hard_veto(self, facts: dict[str, Any], proposal: Proposal) -> AgentPosition | None:
        family = facts["cpk"]["part_family"]
        cpk = facts["cpk"]["cpk"]
        if facts["ncr"]["reg_hold"]:
            return AgentPosition(
                pos="OBJECT", veto=True, sev=3,
                why=f"Customer qualification hold on {family} pending OTDR sign-off. Cannot release to draw.",
                tool=f'get_open_ncrs("{family}") → QUAL_HOLD',
            )
        if cpk < CRIT_CPK:
            return AgentPosition(
                pos="OBJECT", veto=True, sev=3,
                why=(f"Attenuation/geometry Cpk {cpk} below capable floor {CRIT_CPK}. "
                     "Process can't hold spec — producing scrap km by definition."),
                tool=f'get_cpk_trend("{family}") → {cpk}',
            )
        return None

    def policy(self, facts: dict[str, Any], proposal: Proposal) -> AgentPosition:
        family = facts["cpk"]["part_family"]
        cpk = facts["cpk"]["cpk"]
        spc = facts["spc"]["active_alerts"]
        ncr = facts["ncr"]["open_ncrs"]
        scrap = facts["scrap"]["scrap_pct"]
        if cpk < 1.15:
            return AgentPosition(
                pos="OBJECT", sev=2,
                why=(f"Cpk {cpk} marginal"
                     + (f", {spc} SPC excursion(s) on cladding geometry" if spc else "")
                     + ". High attenuation-failure risk — recommend a process review before drawing."),
                tool=f'get_active_spc_alerts → {spc} · get_scrap_history → {scrap}%',
            )
        if cpk < 1.33 or spc > 0 or ncr > 0:
            return AgentPosition(
                pos="CONCEDE", sev=1,
                why=(f"Cpk {cpk}"
                     + (f", {spc} SPC alert(s)" if spc else "")
                     + (f", {ncr} open NCR" if ncr else "")
                     + ". Will run under elevated screening."),
                tool=f'get_active_spc_alerts → {spc} · get_scrap_history → {scrap}%',
            )
        return AgentPosition(
            pos="ACCEPT", sev=0,
            why=f"Cpk {cpk}, no SPC alerts, scrap {scrap}%. Attenuation + geometry in control.",
            tool=f'get_cpk_trend("{family}") → {cpk}',
        )

    def policy_prompt(self) -> str:
        return (
            "OBJECT (sev 2) if Cpk < 1.15. "
            "CONCEDE (sev 1) if Cpk < 1.33 or there are SPC alerts or open NCRs. "
            "Otherwise ACCEPT (sev 0). Reg holds and Cpk below 1.0 are handled "
            "upstream — never veto yourself."
        )
