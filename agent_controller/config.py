"""Runtime configuration for agent-controller.

PER-ENVIRONMENT: In production, set these via Kubernetes ConfigMap (see GitOps
`manifests/agent-controller/app-config.env`). Defaults here are local/dev fallbacks only;
see `ENVIRONMENT_VALUES.md` at the workspace root.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from agent_controller import variables


def _to_int(name: str, default_value: str) -> int:
    raw = os.getenv(name, default_value)
    try:
        return int(raw)
    except Exception:
        return int(default_value)


def _to_status_code_list(name: str, default_value: str) -> list[int]:
    raw = os.getenv(name, default_value)
    parsed: list[int] = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            parsed.append(int(token))
        except Exception:
            continue
    if parsed:
        return parsed
    return [429, 500, 502, 503, 504]


@dataclass(frozen=True)
class Settings:
    llm_provider: str = os.getenv("LLM_PROVIDER", variables.LLM_PROVIDER)
    llm_api_style: str = os.getenv(
        "LLM_API_STYLE", variables.LLM_API_STYLE
    ).strip()
    llm_api_key: str = os.getenv("LLM_API_KEY", variables.LLM_API_KEY)
    llm_model: str = os.getenv("LLM_MODEL", variables.LLM_MODEL)
    llm_base_url: str = os.getenv("LLM_BASE_URL", variables.LLM_BASE_URL)
    llm_endpoint_path: str = os.getenv(
        "LLM_ENDPOINT_PATH", variables.LLM_ENDPOINT_PATH
    )
    llm_display_api: str = os.getenv(
        "LLM_DISPLAY_API", variables.LLM_DISPLAY_API
    ).strip()
    llm_timeout: int = _to_int("LLM_TIMEOUT", variables.LLM_TIMEOUT)
    llm_max_retries: int = _to_int(
        "LLM_MAX_RETRIES", variables.LLM_MAX_RETRIES
    )
    llm_retryable_status_codes: list[int] = field(
        default_factory=lambda: _to_status_code_list(
            "LLM_RETRYABLE_STATUS_CODES",
            variables.LLM_RETRYABLE_STATUS_CODES,
        )
    )
    llm_auth_header: str = os.getenv(
        "LLM_AUTH_HEADER", variables.LLM_AUTH_HEADER
    )
    llm_auth_scheme: str = os.getenv(
        "LLM_AUTH_SCHEME", variables.LLM_AUTH_SCHEME
    )

    sandbox_timeout: int = _to_int(
        "SANDBOX_TIMEOUT", variables.SANDBOX_TIMEOUT
    )
    max_tool_context_chars: int = _to_int(
        "MAX_TOOL_CONTEXT_CHARS",
        variables.MAX_TOOL_CONTEXT_CHARS,
    )
    max_chat_images: int = _to_int(
        "MAX_CHAT_IMAGES", variables.MAX_CHAT_IMAGES
    )
    max_image_bytes: int = _to_int(
        "MAX_IMAGE_BYTES", variables.MAX_IMAGE_BYTES
    )
    # PER-ENVIRONMENT: must be a URL that resolves inside the cluster (service DNS / port).
    sandbox_execute_url: str = os.getenv(
        "SANDBOX_EXECUTE_URL",
        variables.SANDBOX_EXECUTE_URL,
    )
