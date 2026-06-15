"""Subagent base: gather facts via MCP tools -> hard-veto safety net ->
LLM position (small model) with deterministic-policy fallback.

Hard vetoes (lockout, line down, reg hold, sub-floor Cpk, missing material)
are ALWAYS enforced by rules — the LLM can never un-veto a safety stop."""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from langsmith import traceable

from config import settings
from domain import AgentPosition, Proposal

log = logging.getLogger("dispatchai.agents")


class Subagent(ABC):
    id: str          # maint | prod | qual | supp
    name: str        # display name
    source: str      # CMMS | MES / ERP | QMMS | ERP

    @abstractmethod
    async def gather_facts(self, proposal: Proposal) -> dict[str, Any]:
        """Query this agent's own source system through MCP-style tools."""

    @abstractmethod
    def hard_veto(self, facts: dict[str, Any], proposal: Proposal) -> AgentPosition | None:
        """Non-negotiable blocking conditions, enforced deterministically."""

    @abstractmethod
    def policy(self, facts: dict[str, Any], proposal: Proposal) -> AgentPosition:
        """Deterministic assessment (mirrors the demo's thresholds)."""

    def policy_prompt(self) -> str:
        """Role rubric handed to the LLM; defaults to a generic instruction."""
        return (
            "Apply the same thresholds as the documented policy. "
            "Pick ACCEPT when clearly fine, CONCEDE when runnable with reservations, "
            "OBJECT when a constraint is violated."
        )

    async def assess(self, proposal: Proposal) -> AgentPosition:
        @traceable(run_type="chain", name=f"{self.name} agent")
        async def _run() -> AgentPosition:
            facts = await self.gather_facts(proposal)
            veto = self.hard_veto(facts, proposal)
            if veto is not None:
                return veto
            baseline = self.policy(facts, proposal)
            if settings.llm_enabled:
                try:
                    from .llm import refine_position
                    return await refine_position(self, facts, proposal, baseline)
                except Exception as exc:  # degrade to rules, never kill the run
                    log.warning("%s LLM refinement failed (%s) — using rules", self.id, exc)
            return baseline
        return await _run()
