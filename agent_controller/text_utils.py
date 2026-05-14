"""Trim and join helpers for prompts and tool payloads."""

from __future__ import annotations

import json
from typing import Any, Optional


def safe_join(values: Optional[list], limit: int | None = None) -> str:
    if values is None:
        return ""
    cleaned = []
    for value in values:
        if value is None:
            continue
        cleaned.append(str(value))
    if limit:
        cleaned = cleaned[:limit]
    return ", ".join(cleaned)


def truncate_context_block(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    head = max_chars // 2 - 50
    tail = max_chars - head - 50
    if head < 1000:
        head = 1000
    if tail < 1000:
        tail = 1000
    return (
        text[:head]
        + "\n\n... [truncated middle to fit model context] ...\n\n"
        + text[-tail:]
    )


def pack_tool_results_payload(
    tool_results: list[dict[str, Any]],
    max_chars: int,
) -> str:
    blocks = []
    for item in tool_results:
        payload = {
            "tool": item.get("tool"),
            "result": item.get("result"),
        }
        blocks.append(json.dumps(payload, indent=2, default=str))
    combined = "\n\n--- TOOL SEPARATOR ---\n\n".join(blocks)
    return truncate_context_block(combined, max_chars)
