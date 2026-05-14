"""HTTP client for agent-sandbox /execute."""

from __future__ import annotations

from typing import Any, Optional

import requests

from agent_controller.config import Settings


class SandboxClient:
    def __init__(self, settings: Optional[Settings] = None):
        self._settings = settings or Settings()

    def execute(
        self,
        tool: str,
        arguments: dict[str, Any],
    ) -> tuple[int, str, Any]:
        """Returns (status_code, raw_text, parsed_json_or_none)."""
        r = requests.post(
            self._settings.sandbox_execute_url,
            json={"tool": tool, "arguments": arguments},
            timeout=self._settings.sandbox_timeout,
        )
        text = r.text
        try:
            parsed = r.json()
        except Exception:
            parsed = None
        return r.status_code, text, parsed
