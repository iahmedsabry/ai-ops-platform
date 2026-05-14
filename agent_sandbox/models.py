"""Pydantic models for sandbox HTTP API."""

from pydantic import BaseModel


class ToolRequest(BaseModel):
    tool: str
    arguments: dict = {}
