"""Shim for `uvicorn app:app`; implementation lives in agent_sandbox.main."""
from agent_sandbox.main import app

__all__ = ["app"]
