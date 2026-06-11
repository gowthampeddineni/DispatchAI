"""Two-tier OpenAI LLM access.

Routing is by task complexity (config.settings.model_for), never hard-coded:
- small model: agent position formation, extraction, short summaries
- large model: orchestrator synthesis, conflict notes, fix suggestions
"""
from __future__ import annotations

import json
from typing import Any, Literal, TYPE_CHECKING

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from config import settings
from domain import AgentPosition, Proposal

if TYPE_CHECKING:
    from .base import Subagent


def chat_model(task: str):
    """Build a ChatOpenAI for the model tier mapped to this task."""
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(model=settings.model_for(task), temperature=0)


class LLMPosition(BaseModel):
    """Structured output for an agent's position (vetoes are rules-only)."""
    pos: Literal["ACCEPT", "CONCEDE", "OBJECT"]
    sev: int = Field(ge=0, le=2, description="0 accept, 1 concede, 2 object")
    why: str = Field(description="One or two factual sentences citing the data, plant-floor tone")


async def refine_position(
    agent: "Subagent", facts: dict[str, Any], proposal: Proposal, baseline: AgentPosition
) -> AgentPosition:
    """Small-model assessment of the non-veto position. The deterministic
    baseline and its tool trail are kept as grounding; on any failure the
    caller falls back to the baseline."""
    llm = chat_model("agent_position").with_structured_output(LLMPosition)
    out: LLMPosition = await llm.ainvoke([
        SystemMessage(content=(
            f"You are the {agent.name} agent of an optical-fiber plant scheduler. "
            f"You consult only your own source system ({agent.source}) and judge ONE "
            "dispatch proposal independently. Answer ACCEPT, CONCEDE or OBJECT.\n"
            f"Policy rubric:\n{agent.policy_prompt()}\n"
            "Severity: 0 for ACCEPT, 1 for CONCEDE, 2 for OBJECT."
        )),
        HumanMessage(content=json.dumps({
            "proposal": {
                "order": proposal.order.model_dump(),
                "asset_id": proposal.asset_id,
                "start_hr": proposal.start_hr,
                "duration_h": proposal.dur_h,
            },
            "source_system_facts": facts,
            "deterministic_baseline": baseline.model_dump(),
        }, default=str)),
    ])
    return AgentPosition(pos=out.pos, veto=False, sev=out.sev, why=out.why, tool=baseline.tool)
