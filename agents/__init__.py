"""The four specialist subagents (roles defined by DispatchAI-Demo-Guide.md)."""
from .base import Subagent
from .maintenance import MaintenanceAgent
from .production import ProductionAgent
from .quality import QualityAgent
from .supply_chain import SupplyChainAgent

AGENTS: dict[str, Subagent] = {
    "maint": MaintenanceAgent(),
    "prod": ProductionAgent(),
    "qual": QualityAgent(),
    "supp": SupplyChainAgent(),
}

AGENT_META = {
    a.id: {"id": a.id, "name": a.name, "source": a.source} for a in AGENTS.values()
}

__all__ = ["Subagent", "AGENTS", "AGENT_META",
           "MaintenanceAgent", "ProductionAgent", "QualityAgent", "SupplyChainAgent"]
