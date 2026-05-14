"""Maps allowed tool names to callables (thin wrappers over dispatch_tool)."""

from __future__ import annotations

from typing import Any, Callable

from shared.tool_catalog import allowed_tool_names

from agent_sandbox.tool_dispatch import dispatch_tool


def _make_handler(tool_name: str) -> Callable[[dict[str, Any]], Any]:
    def _run(arguments: dict[str, Any]) -> Any:
        return dispatch_tool(tool_name, arguments)

    return _run


HANDLERS: dict[str, Callable[[dict[str, Any]], Any]] = {
    name: _make_handler(name) for name in sorted(allowed_tool_names())
}
