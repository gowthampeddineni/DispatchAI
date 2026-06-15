"""MCP-style tool registry.

Agents never touch a DB client: they call named tools with typed signatures
through this registry. Phase 1 backs the tools with local SQLite; Phase 7 can
re-register the same tool names against real MCP servers and no agent changes.

Every tool is wrapped with langsmith's @traceable(run_type="tool") so each
call shows up inside the end-to-end LangSmith trace.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from langsmith import traceable


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    source_system: str  # CMMS | MES | QMMS | ERP
    fn: Callable[..., Awaitable[Any]]


_REGISTRY: dict[str, ToolSpec] = {}


def mcp_tool(name: str, description: str, source_system: str):
    """Register an async function as an MCP-style tool with a stable name."""
    def deco(fn: Callable[..., Awaitable[Any]]):
        traced = traceable(run_type="tool", name=name)(fn)
        _REGISTRY[name] = ToolSpec(name, description, source_system, traced)
        return traced
    return deco


async def call_tool(name: str, **kwargs: Any) -> Any:
    """Invoke a registered tool by name (the only entry point agents use)."""
    if name not in _REGISTRY:
        raise KeyError(f"Unknown tool: {name}")
    return await _REGISTRY[name].fn(**kwargs)


def list_tools(source_system: str | None = None) -> list[ToolSpec]:
    specs = list(_REGISTRY.values())
    if source_system:
        specs = [s for s in specs if s.source_system == source_system]
    return specs
