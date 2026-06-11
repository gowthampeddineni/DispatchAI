"""MCP-style tool layer. Importing the package registers every tool."""
from . import cmms, erp, mes, qmms  # noqa: F401  (registration side effect)
from .registry import call_tool, list_tools, mcp_tool

__all__ = ["call_tool", "list_tools", "mcp_tool"]
