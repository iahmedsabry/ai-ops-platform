"""agent-sandbox FastAPI entry (read-only kubectl + Prom tools)."""

from __future__ import annotations

from fastapi import FastAPI

from shared.tool_catalog import allowed_tool_names

from agent_sandbox.models import ToolRequest
from agent_sandbox.registry import HANDLERS

ALLOWED_TOOLS = allowed_tool_names()

app = FastAPI()


@app.get("/")
def root():
    return {"status": "sandbox running"}


@app.post("/execute")
def execute(request: ToolRequest):
    if request.tool not in ALLOWED_TOOLS:
        return {
            "error": f"Tool not allowed: {request.tool}",
        }
    handler = HANDLERS.get(request.tool)
    if handler is None:
        return {"error": f"No handler for tool: {request.tool}"}
    return handler(request.arguments)
