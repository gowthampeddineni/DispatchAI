"""Shared LangGraph state for one dispatch negotiation."""
from __future__ import annotations

from typing import Annotated, TypedDict

from domain import AgentPosition, Proposal, Verdict


def merge_dicts(a: dict, b: dict) -> dict:
    """Reducer: parallel agent nodes each contribute their own key."""
    return {**a, **b}


class NegotiationState(TypedDict, total=False):
    proposal: Proposal
    plan: list[str]                                        # subagent ids to invoke
    positions: Annotated[dict[str, AgentPosition], merge_dicts]
    errors: Annotated[dict[str, str], merge_dicts]         # agent_id -> error (degraded)
    verdict: Verdict
