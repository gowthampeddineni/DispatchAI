"""Maintenance agent — consults the CMMS. Worries about asset health,
vibration, PM schedule and lockouts."""
from __future__ import annotations

from typing import Any

from tools import call_tool
from domain import AgentPosition, Proposal

from .base import Subagent


class MaintenanceAgent(Subagent):
    id = "maint"
    name = "Maintenance"
    source = "CMMS"

    async def gather_facts(self, proposal: Proposal) -> dict[str, Any]:
        health = await call_tool("get_asset_health", asset_id=proposal.asset_id)
        vib = await call_tool("get_vibration_history", asset_id=proposal.asset_id, days=30)
        pm = await call_tool("get_pm_schedule", asset_id=proposal.asset_id)
        return {
            "asset": health.model_dump(),
            "vibration": {"trend": vib.trend, "latest": vib.readings[:5], "threshold": vib.threshold},
            "pm": pm.model_dump(),
        }

    def hard_veto(self, facts: dict[str, Any], proposal: Proposal) -> AgentPosition | None:
        a = facts["asset"]
        if a["lockout"]:
            return AgentPosition(
                pos="OBJECT", veto=True, sev=3,
                why=f"{a['asset_name']} is safety-tagged / locked out (spindle drive fault). Non-discretionary stop.",
                tool=f'get_asset_health("{a["asset_id"]}") → LOCKOUT=true',
            )
        return None

    def policy(self, facts: dict[str, Any], proposal: Proposal) -> AgentPosition:
        a = facts["asset"]
        health, vib, pm_days, open_wo = a["health_score"], a["vibration_trend"], a["pm_due_days"], a["open_wo_count"]
        if health < 45 or (vib == "rising" and pm_days < 0 and open_wo >= 2):
            return AgentPosition(
                pos="OBJECT", sev=2,
                why=(f"Condition {health}%, drive trend {vib}, "
                     f"PM {abs(pm_days)}d overdue. Failure risk too high to load."
                     if pm_days < 0 else
                     f"Condition {health}%, drive trend {vib}, PM ok. Failure risk too high to load."),
                tool=f'get_vibration_history("{a["asset_id"]}",30d) · get_pm_schedule',
            )
        if health < 65 or pm_days < 0 or vib == "rising":
            return AgentPosition(
                pos="CONCEDE", sev=1,
                why=(f"Condition {health}%, "
                     f"{'PM ' + str(abs(pm_days)) + 'd overdue' if pm_days < 0 else 'PM due soon'}. "
                     "Will run, flagging for monitoring."),
                tool=f'get_asset_health("{a["asset_id"]}") · {open_wo} open WO',
            )
        return AgentPosition(
            pos="ACCEPT", sev=0,
            why=f"Furnace/tractor condition {health}%, draw tension stable, PM in {pm_days}d. Line fit to run.",
            tool=f'get_asset_health("{a["asset_id"]}") → {health}',
        )

    def policy_prompt(self) -> str:
        return (
            "OBJECT (sev 2) if condition < 45% OR (vibration rising AND PM overdue AND >=2 open WOs). "
            "CONCEDE (sev 1) if condition < 65% OR PM overdue OR vibration rising. "
            "Otherwise ACCEPT (sev 0). Lockouts are handled upstream — never veto yourself."
        )
