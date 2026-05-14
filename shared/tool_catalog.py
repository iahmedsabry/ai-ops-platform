"""Load tool catalog from shared/tools.yaml (same file in controller and sandbox images)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_SHARED_DIR = Path(__file__).resolve().parent
_TOOLS_PATH = _SHARED_DIR / "tools.yaml"


def load_tool_entries() -> list[dict[str, Any]]:
    raw = yaml.safe_load(_TOOLS_PATH.read_text(encoding="utf-8"))
    tools = raw.get("tools") or []
    catalog = []
    for entry in tools:
        catalog.append(
            {
                "name": entry["name"],
                "arguments": entry.get("arguments") or {},
                "detail": entry.get("detail") or "",
            }
        )
    return catalog


def allowed_tool_names(entries: list[dict[str, Any]] | None = None) -> frozenset[str]:
    rows = entries if entries is not None else load_tool_entries()
    return frozenset(r["name"] for r in rows)
