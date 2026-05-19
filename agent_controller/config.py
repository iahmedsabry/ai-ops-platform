"""Runtime configuration for agent-controller.

PER-ENVIRONMENT: In production, set these via Kubernetes ConfigMap (see GitOps
`manifests/agent-controller/app-config.env`). Defaults here are local/dev fallbacks only;
see `ENVIRONMENT_VALUES.md` at the workspace root.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    gemini_timeout: int = int(os.getenv("GEMINI_TIMEOUT", "90"))
    sandbox_timeout: int = int(os.getenv("SANDBOX_TIMEOUT", "90"))
    max_tool_context_chars: int = int(
        os.getenv("MAX_TOOL_CONTEXT_CHARS", "120000")
    )
    max_chat_images: int = int(os.getenv("MAX_CHAT_IMAGES", "6"))
    max_image_bytes: int = int(
        os.getenv("MAX_IMAGE_BYTES", str(4 * 1024 * 1024))
    )
    # PER-ENVIRONMENT: must be a URL that resolves inside the cluster (service DNS / port).
    sandbox_execute_url: str = os.getenv(
        "SANDBOX_EXECUTE_URL",
        "http://agent-sandbox/execute",
    )
    # PER-ENVIRONMENT: override only if you use a Google API proxy or non-default endpoint.
    gemini_display_api: str = os.getenv(
        "GEMINI_DISPLAY_API",
        "https://generativelanguage.googleapis.com/v1beta",
    ).strip()
